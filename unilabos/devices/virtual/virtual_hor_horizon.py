from __future__ import annotations

import logging
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from unilabos.registry.decorators import action, device, not_action, topic_config
from unilabos.ros.nodes.base_device_node import BaseROS2DeviceNode


_JOINTS = {
    "gate": "gate_joint",
    "arm_z": "arm0_joint",
    "arm_1": "arm1_joint",
    "arm_2": "arm2_joint",
    "arm_3": "arm3_joint",
    "left_gripper": "left_joint",
    "right_gripper": "right_joint",
}
_HOME = {name: 0.0 for name in _JOINTS}
_LIMITS = {
    "gate": (0.0, 1.57),
    "arm_z": (0.0, 0.43),
    "arm_1": (-2.0, 2.0),
    "arm_2": (-2.0, 2.0),
    "arm_3": (-2.0, 2.0),
    "left_gripper": (-0.025, 0.0),
    "right_gripper": (0.0, 0.025),
}


@device(
    id="virtual_hor_horizon",
    display_name="HOR Horizon V2.1（碰撞仿真）",
    category=["virtual_device", "robot_arm"],
    description="HOR Horizon test fixture for RViz and Isaac PhysX collision development.",
    driver_runtime_kind="virtual",
    virtual_driver_kind="engine_adapter",
    sim_engine="isaac",
    model={
        "type": "device",
        "mesh": "hor_horizon_v2_1",
        "path": "",
        "joints": {
            "gate": "gate_joint",
            "arm_z": "arm0_joint",
            "arm_1": "arm1_joint",
            "arm_2": "arm2_joint",
            "arm_3": "arm3_joint",
            "left_gripper": "left_joint",
            "right_gripper": "right_joint",
        },
    },
)
class VirtualHorHorizon:
    """仅用于仿真开发的 HOR Horizon 关节驱动，不代表真实设备通信协议。"""

    _ros_node: BaseROS2DeviceNode

    def __init__(
        self,
        device_id: Optional[str] = None,
        joint_speed: float = 0.5,
        **kwargs,
    ) -> None:
        """
        Args:
            device_id[设备ID]: graph 中的设备实例 ID。
            joint_speed[关节速度]: 测试插值速度，单位 rad/s 或 m/s。
        """
        if device_id is None and "id" in kwargs:
            device_id = kwargs.pop("id")
        self.device_id = device_id or "virtual_hor_horizon"
        self.joint_speed = max(0.01, float(joint_speed))
        self.logger = logging.getLogger(f"VirtualHorHorizon.{self.device_id}")
        self.data: Dict[str, Any] = {"status": "Idle", "joint_positions": dict(_HOME)}
        self._publisher = None
        self._executor = None
        self._executor_thread = None

    @not_action
    def post_init(self, ros_node: BaseROS2DeviceNode) -> None:
        self._ros_node = ros_node

    @not_action
    def _ensure_publisher(self) -> None:
        if self._publisher is not None:
            return
        import rclpy

        from unilabos.devices.ros_dev.simple_joint_publisher_node import SimpleJointPublisher

        if not rclpy.ok():
            rclpy.init()
        device_id = getattr(getattr(self, "_ros_node", None), "device_id", None) or self.device_id
        self.device_id = device_id
        self._publisher = SimpleJointPublisher(
            device_id=device_id,
            joint_names=list(_JOINTS),
            rate=50,
            node_name=f"{device_id}_joint_pub",
            joint_map=dict(_JOINTS),
        )
        self._executor = rclpy.executors.MultiThreadedExecutor()
        self._executor.add_node(self._publisher)
        self._executor_thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._executor_thread.start()
        self._publisher.set_immediate(dict(_HOME))
        self.data["status"] = "Ready"

    @not_action
    def initialize(self) -> bool:
        self._ensure_publisher()
        self._move(dict(_HOME))
        return True

    @not_action
    def cleanup(self) -> bool:
        if self._executor and self._publisher:
            self._executor.remove_node(self._publisher)
        if self._executor:
            self._executor.shutdown()
        self.data["status"] = "Offline"
        return True

    @property
    @topic_config(period=1.0)
    def status(self) -> str:
        return str(self.data["status"])

    @action(description="回到测试零位")
    def home(self) -> dict:
        self._move(dict(_HOME))
        return {"success": True, "joint_positions": dict(self.data["joint_positions"])}

    @action(description="控制前门角度")
    def set_gate(self, position: float = 0.0) -> dict:
        """
        Args:
            position[前门角度(rad)]: 取值 0–1.57。
        """
        self._move({"gate": self._clamp("gate", position)})
        return {"success": True, "position": self.data["joint_positions"]["gate"]}

    @action(description="移动 HOR Horizon 机械臂")
    def move_arm(
        self,
        z: float = 0.0,
        joint1: float = 0.0,
        joint2: float = 0.0,
        joint3: float = 0.0,
    ) -> dict:
        """
        Args:
            z[升降位置(m)]: 取值 0–0.43。
            joint1[关节1(rad)]: 取值 -2–2。
            joint2[关节2(rad)]: 取值 -2–2。
            joint3[关节3(rad)]: 取值 -2–2。
        """
        target = {
            "arm_z": self._clamp("arm_z", z),
            "arm_1": self._clamp("arm_1", joint1),
            "arm_2": self._clamp("arm_2", joint2),
            "arm_3": self._clamp("arm_3", joint3),
        }
        self._move(target)
        return {"success": True, "joint_positions": dict(self.data["joint_positions"])}

    @action(description="设置夹爪开度")
    def set_gripper(self, opening: float = 0.0) -> dict:
        """
        Args:
            opening[单侧开度(m)]: 取值 0–0.025。
        """
        opening = max(0.0, min(0.025, float(opening)))
        self._move({"left_gripper": -opening, "right_gripper": opening})
        return {"success": True, "opening": opening}

    @action(description="运行 HOR Horizon 碰撞开发用例")
    def run_collision_demo(self, case_id: str = "safe_path") -> dict:
        """
        Args:
            case_id[测试场景]: safe_path、arm_hits_box 或 gripper_contact。
        """
        cases = {
            "safe_path": {"arm_z": 0.15, "arm_1": 0.0, "arm_2": 0.0, "arm_3": 0.0},
            "arm_hits_box": {"arm_z": 0.04, "arm_1": 1.7, "arm_2": -1.7, "arm_3": 1.7},
            "gripper_contact": {"arm_z": 0.2, "left_gripper": -0.025, "right_gripper": 0.025},
        }
        if case_id not in cases:
            return {"success": False, "error": f"unknown case_id: {case_id}"}
        self.data["status"] = f"Running:{case_id}"
        self._move(cases[case_id])
        if case_id == "arm_hits_box":
            self._inject_collision_fixture()
            # 资产导入和 PhysX contact callback 是异步的；保持 action 活跃，
            # 让 CollisionEventBridge 能关联当前 workflow job。
            time.sleep(4.0)
        self.data["status"] = "Ready"
        return {
            "success": True,
            "case_id": case_id,
            "joint_positions": dict(self.data["joint_positions"]),
        }

    @not_action
    def _move(self, target: Dict[str, float]) -> None:
        self._ensure_publisher()
        normalized = {name: self._clamp(name, value) for name, value in target.items()}
        self._publisher.move_to(normalized, self.joint_speed)
        self.data["joint_positions"].update(normalized)

    @not_action
    def _inject_collision_fixture(self) -> None:
        from unilabos.sim.isaac_gateway import get_active_gateway

        gateway = get_active_gateway()
        if gateway is None:
            self.logger.warning("Isaac gateway未启动，跳过碰撞fixture注入。")
            return
        fixture_path = Path(tempfile.gettempdir()) / "hor_workflow_collision_fixture.urdf"
        fixture_path.write_text(
            (
                '<robot name="hor_workflow_collision_fixture">'
                '<link name="fixture_link">'
                '<inertial><mass value="10"/>'
                '<inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial>'
                '<visual><geometry><box size="1.5 1.5 1.5"/></geometry></visual>'
                '<collision><geometry><box size="1.5 1.5 1.5"/></geometry></collision>'
                "</link></robot>"
            ),
            encoding="utf-8",
        )
        gateway.upsert_asset(
            {
                "asset_id": "hor_workflow_collision_fixture",
                "asset_kind": "device",
                "format": "urdf",
                "source_uri": fixture_path.as_uri(),
                "prim_path": "/World/hor_workflow_collision_fixture",
                "pose": {
                    "frame_id": "world",
                    "position_m": {"x": 0.0, "y": 0.0, "z": 0.25},
                    "orientation_xyzw": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                },
                "metadata": {"id": "hor_workflow_collision_fixture"},
                "replace_if_exists": True,
            }
        )

    @staticmethod
    def _clamp(name: str, value: float) -> float:
        lower, upper = _LIMITS[name]
        return max(lower, min(upper, float(value)))

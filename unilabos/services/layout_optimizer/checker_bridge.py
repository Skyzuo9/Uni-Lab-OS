"""CheckerBridge — MoveIt2 碰撞/可达性检测桥接层。

该模块是 layout_optimizer 与 Uni-Lab-OS ROS2 层的唯一接触点。
所有 ROS2 依赖都封装在此，其余算法代码保持 ROS-free。

工作原理：
  遍历 Uni-Lab-OS 的 registered_devices 字典，
  找到 driver_instance 是 MoveitInterface 的设备，
  提取其 moveit2 字典中的 MoveIt2 实例（key = move_group 名称）。

依赖：
  - unilabos.ros.nodes.base_device_node.registered_devices
  - unilabos.devices.ros_dev.moveit_interface.MoveitInterface
  - unilabos.devices.ros_dev.moveit2.MoveIt2（已由 MoveitInterface 初始化）

环境变量：
  LAYOUT_CHECKER_MODE: "mock" | "moveit"（由 service.py 读取，此处不直接用）
  LAYOUT_VOXEL_DIR: 预计算体素图目录（.npz 文件，Phase 4 用）
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class CheckerBridge:
    """从 Uni-Lab-OS registered_devices 中发现并桥接 MoveIt2 实例。"""

    @staticmethod
    def discover_moveit2_instances() -> dict:
        """扫描 registered_devices，返回所有可用的 MoveIt2 实例。

        Returns:
            dict[str, MoveIt2]: key = "{device_id}_{move_group_name}"，
                                value = MoveIt2 实例
        """
        from unilabos.ros.nodes.base_device_node import registered_devices
        from unilabos.devices.ros_dev.moveit_interface import MoveitInterface

        instances: dict = {}
        for device_id, device_info in registered_devices.items():
            driver = device_info.get("driver_instance")
            if not isinstance(driver, MoveitInterface):
                continue
            moveit2_dict = getattr(driver, "moveit2", {})
            for group_name, moveit2 in moveit2_dict.items():
                key = f"{device_id}_{group_name}"
                instances[key] = moveit2
                logger.debug(
                    "Discovered MoveIt2 instance: device=%s group=%s",
                    device_id, group_name,
                )

        logger.info(
            "CheckerBridge: found %d MoveIt2 instance(s): %s",
            len(instances), list(instances.keys()),
        )
        return instances

    @classmethod
    def create_checkers(cls, primary_arm_id: str | None = None) -> dict:
        """创建 MoveIt2 碰撞和可达性检测器。

        Args:
            primary_arm_id: 首选机械臂 key（格式 "{device_id}_{group_name}"）。
                            为 None 时取发现的第一个实例。

        Returns:
            {"collision": MoveItCollisionChecker, "reachability": IKFastReachabilityChecker}

        Raises:
            RuntimeError: 未找到任何 MoveIt2 实例
            ImportError: ROS2 相关模块不可导入（触发 service.py 回退 mock）
        """
        instances = cls.discover_moveit2_instances()
        if not instances:
            raise RuntimeError(
                "No MoveIt2 instances found in registered_devices. "
                "Ensure at least one device with MoveitInterface driver is loaded."
            )

        if primary_arm_id and primary_arm_id in instances:
            moveit2 = instances[primary_arm_id]
            logger.info("Using primary arm: %s", primary_arm_id)
        else:
            first_key = next(iter(instances))
            moveit2 = instances[first_key]
            if primary_arm_id:
                logger.warning(
                    "primary_arm_id '%s' not found, using '%s' instead",
                    primary_arm_id, first_key,
                )
            else:
                logger.info("Using first available arm: %s", first_key)

        from .ros_checkers import MoveItCollisionChecker, IKFastReachabilityChecker

        voxel_dir = os.getenv("LAYOUT_VOXEL_DIR")
        if voxel_dir is None:
            voxel_dir = str(Path(__file__).parent / "voxel_maps")

        # DE 优化循环中 sync_to_scene=False（避免每次迭代都发 ROS 消息）
        # 最终结果由 service.py 调用 collision_checker.sync_to_planning_scene() 同步
        collision = MoveItCollisionChecker(moveit2, sync_to_scene=False)
        reachability = IKFastReachabilityChecker(
            moveit2,
            voxel_dir=voxel_dir,
        )

        logger.info(
            "MoveIt2 checkers created (voxel_dir=%s, fcl=%s)",
            voxel_dir,
            collision._fcl_available,
        )

        return {"collision": collision, "reachability": reachability}

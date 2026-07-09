#!/usr/bin/env python3
"""
关节控制桥接节点 — Web 端通过 Foxglove Bridge 对接的核心服务

功能:
1. 关节滑块控制: 订阅 /web/joint_command (JointState) → 直接发布到 /joint_states
2. IK 求解: 订阅 /web/pose_target (PoseStamped) → compute_ik → 发布结果到 /joint_states
3. 轨迹规划执行: 订阅 /web/plan_request (PoseStamped) → plan_kinematic_path → display_planned_path

前端通过 Foxglove Bridge (ws://172.20.0.39:8765) 发布消息到以上 topic。

启动方式:
    conda activate unilab
    python3 joint_control_bridge.py
"""

import threading
import time
import rclpy
from rclpy.node import Node
from rclpy.node import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy

from sensor_msgs.msg import JointState
from geometry_msgs.msg import PoseStamped, Pose, Point, Quaternion
from std_msgs.msg import String
from moveit_msgs.srv import GetPositionIK, GetPositionFK, GetMotionPlan
from moveit_msgs.msg import (
    PositionIKRequest, RobotState, Constraints,
    PositionConstraint, OrientationConstraint,
    BoundingVolume, DisplayTrajectory, RobotTrajectory,
    MotionPlanRequest, WorkspaceParameters
)
from shape_msgs.msg import SolidPrimitive
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from builtin_interfaces.msg import Duration
from rclpy.action import ActionClient
from control_msgs.action import FollowJointTrajectory
import json

JOINT_NAMES = [
    "arm_slider_arm_base_joint", "arm_slider_arm_link_1_joint",
    "arm_slider_arm_link_2_joint", "arm_slider_arm_link_3_joint",
    "arm_slider_gripper_base_joint", "arm_slider_gripper_right_joint"
]
GROUP_NAME = "arm_slider_arm"
END_EFFECTOR_LINK = "arm_slider_gripper_base"


class JointControlBridge(Node):
    def __init__(self):
        super().__init__("joint_control_bridge")
        self.cb_group = ReentrantCallbackGroup()

        self.current_joint_state = None
        self._lock = threading.Lock()

        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10
        )

        # --- 订阅当前关节状态 ---
        self.create_subscription(
            JointState, "/joint_states",
            self._on_joint_state, qos,
            callback_group=self.cb_group
        )

        # --- 功能 1: 关节滑块控制 ---
        self.create_subscription(
            JointState, "/web/joint_command",
            self._on_joint_command, qos,
            callback_group=self.cb_group
        )

        # --- 功能 2: IK 末端拖拽 ---
        self.create_subscription(
            PoseStamped, "/web/pose_target",
            self._on_pose_target, qos,
            callback_group=self.cb_group
        )

        # --- 功能 3: 轨迹规划 ---
        self.create_subscription(
            PoseStamped, "/web/plan_request",
            self._on_plan_request, qos,
            callback_group=self.cb_group
        )

        # --- IK 结果反馈 (供前端读取) ---
        self.ik_result_pub = self.create_publisher(String, "/web/ik_result", 10)

        # --- 规划结果反馈 ---
        self.plan_result_pub = self.create_publisher(String, "/web/plan_result", 10)

        # --- 规划路径可视化 (RViz + Foxglove) ---
        self.display_traj_pub = self.create_publisher(
            DisplayTrajectory, "/display_planned_path", 10
        )

        # --- MoveIt2 服务客户端 ---
        self.ik_client = self.create_client(
            GetPositionIK, "/compute_ik",
            callback_group=self.cb_group
        )
        self.fk_client = self.create_client(
            GetPositionFK, "/compute_fk",
            callback_group=self.cb_group
        )
        self.plan_client = self.create_client(
            GetMotionPlan, "/plan_kinematic_path",
            callback_group=self.cb_group
        )

        # --- ros2_control 模式: 通过 controller action 发送指令 ---
        self._arm_action = ActionClient(
            self, FollowJointTrajectory,
            "/arm_slider_arm_controller/follow_joint_trajectory",
            callback_group=self.cb_group
        )
        self._controller_joints = [
            "arm_slider_arm_base_joint",
            "arm_slider_arm_link_1_joint",
            "arm_slider_arm_link_2_joint",
            "arm_slider_arm_link_3_joint",
            "arm_slider_gripper_base_joint",
        ]
        self._use_controller = True

        self.get_logger().info("=" * 55)
        self.get_logger().info("Joint Control Bridge 已启动")
        self.get_logger().info("=" * 55)
        self.get_logger().info(f"  关节滑块:  /web/joint_command (JointState)")
        self.get_logger().info(f"  IK 拖拽:   /web/pose_target   (PoseStamped)")
        self.get_logger().info(f"  轨迹规划:  /web/plan_request   (PoseStamped)")
        self.get_logger().info(f"  IK 结果:   /web/ik_result      (String/JSON)")
        self.get_logger().info(f"  规划结果:  /web/plan_result     (String/JSON)")
        self.get_logger().info(f"  Foxglove:  ws://172.20.0.39:8765")
        self.get_logger().info("=" * 55)

    def _on_joint_state(self, msg: JointState):
        with self._lock:
            self.current_joint_state = msg

    # ========== 功能 1: 关节滑块控制 ==========

    def _on_joint_command(self, msg: JointState):
        """收到前端关节指令 → 通过 controller 或直接发布"""
        target = dict(zip(msg.name, msg.position))

        if self._use_controller and self._arm_action.server_is_ready():
            with self._lock:
                if self.current_joint_state is None:
                    return
                current = dict(zip(
                    self.current_joint_state.name,
                    self.current_joint_state.position
                ))

            merged = {**current, **target}
            goal = FollowJointTrajectory.Goal()
            goal.trajectory.joint_names = self._controller_joints
            point = JointTrajectoryPoint()
            point.positions = [float(merged.get(j, 0.0)) for j in self._controller_joints]
            point.time_from_start = Duration(sec=0, nanosec=300_000_000)
            goal.trajectory.points = [point]
            self._arm_action.send_goal_async(goal)
            self.get_logger().debug(f"关节指令(controller): {target}")
        else:
            out = JointState()
            out.header.stamp = self.get_clock().now().to_msg()
            with self._lock:
                if self.current_joint_state is None:
                    return
                current = dict(zip(
                    self.current_joint_state.name,
                    self.current_joint_state.position
                ))
            merged = {**current, **target}
            out.name = list(merged.keys())
            out.position = list(merged.values())
            # removed: self.joint_pub.publish(out) — use controller only
            self.get_logger().debug(f"关节指令(direct): {target}")

    # ========== 功能 2: IK 末端拖拽 ==========

    def _get_current_ee_pose(self):
        """FK 获取当前末端位姿"""
        if not self.fk_client.wait_for_service(timeout_sec=2.0):
            return None
        fk_req = GetPositionFK.Request()
        fk_req.header.frame_id = "world"
        fk_req.fk_link_names = [END_EFFECTOR_LINK]
        with self._lock:
            if self.current_joint_state is None:
                return None
            fk_req.robot_state.joint_state.name = list(self.current_joint_state.name)
            fk_req.robot_state.joint_state.position = list(self.current_joint_state.position)
        try:
            fk_res = self.fk_client.call(fk_req)
            if fk_res and fk_res.error_code.val == 1:
                return fk_res.pose_stamped[0].pose
        except Exception:
            pass
        return None

    def _on_pose_target(self, msg: PoseStamped):
        """收到末端目标位姿 → IK 求解 → 发布关节值 + 返回结果
        对于 5-DOF 臂，自动使用当前 orientation 保证 IK 可解"""
        self.get_logger().info(
            f"IK 请求: pos=({msg.pose.position.x:.3f}, "
            f"{msg.pose.position.y:.3f}, {msg.pose.position.z:.3f})"
        )

        if not self.ik_client.wait_for_service(timeout_sec=2.0):
            self._pub_ik_result(False, "compute_ik service 不可用")
            return

        current_pose = self._get_current_ee_pose()

        ik_req = GetPositionIK.Request()
        ik_req.ik_request.group_name = GROUP_NAME
        if msg.header.frame_id == "":
            msg.header.frame_id = "world"

        target_pose = PoseStamped()
        target_pose.header.frame_id = msg.header.frame_id
        target_pose.pose.position = msg.pose.position
        if current_pose is not None:
            target_pose.pose.orientation = current_pose.orientation
            self.get_logger().info("IK: 使用当前 FK orientation (5-DOF 兼容)")
        else:
            target_pose.pose.orientation = msg.pose.orientation

        ik_req.ik_request.pose_stamped = target_pose
        ik_req.ik_request.avoid_collisions = False
        ik_req.ik_request.timeout.sec = 10

        with self._lock:
            if self.current_joint_state is not None:
                js = self.current_joint_state
                ik_req.ik_request.robot_state.joint_state.name = list(js.name)
                ik_req.ik_request.robot_state.joint_state.position = list(js.position)
                self.get_logger().info(f"IK seed: {len(js.name)} joints")
            else:
                self.get_logger().warn("IK: no seed state")

        try:
            result = self.ik_client.call(ik_req)
            self._handle_ik_result(result)
        except Exception as e:
            self.get_logger().error(f"IK call exception: {e}")
            self._pub_ik_result(False, f"IK 调用异常: {e}")

    def _handle_ik_result(self, result):
        if result is None:
            self._pub_ik_result(False, "IK 调用失败")
            return

        if result.error_code.val == 1:
            js = result.solution.joint_state
            joints = {n: round(p, 6) for n, p in zip(js.name, js.position) if "arm_slider" in n}
            self.get_logger().info(f"IK 成功: {joints}")

            if self._use_controller and self._arm_action.server_is_ready():
                with self._lock:
                    current = {}
                    if self.current_joint_state:
                        current = dict(zip(self.current_joint_state.name, self.current_joint_state.position))
                merged = {**current, **joints}
                goal = FollowJointTrajectory.Goal()
                goal.trajectory.joint_names = self._controller_joints
                point = JointTrajectoryPoint()
                point.positions = [float(merged.get(j, 0.0)) for j in self._controller_joints]
                point.time_from_start = Duration(sec=0, nanosec=500_000_000)
                goal.trajectory.points = [point]
                self._arm_action.send_goal_async(goal)
            else:
                out = JointState()
                out.header.stamp = self.get_clock().now().to_msg()
                out.name = list(joints.keys())
                out.position = list(joints.values())
                # removed: self.joint_pub.publish(out) — use controller only

            self._pub_ik_result(True, "IK 求解成功", joints)
        else:
            self.get_logger().warn(f"IK 失败: error_code={result.error_code.val}")
            self._pub_ik_result(False, f"IK 无解 (code={result.error_code.val})")

    def _pub_ik_result(self, success, message, joints=None):
        msg = String()
        msg.data = json.dumps({
            "success": success,
            "message": message,
            "joints": joints or {},
        })
        self.ik_result_pub.publish(msg)

    # ========== 功能 3: 轨迹规划 ==========

    def _on_plan_request(self, msg: PoseStamped):
        """收到规划请求 → 先 IK 求解目标关节值 → 关节空间规划 → 执行"""
        self.get_logger().info(
            f"规划请求: pos=({msg.pose.position.x:.3f}, "
            f"{msg.pose.position.y:.3f}, {msg.pose.position.z:.3f})"
        )

        if not self.ik_client.wait_for_service(timeout_sec=2.0):
            self._pub_plan_result(False, "compute_ik service 不可用")
            return

        current_pose = self._get_current_ee_pose()

        ik_req = GetPositionIK.Request()
        ik_req.ik_request.group_name = GROUP_NAME
        if msg.header.frame_id == "":
            msg.header.frame_id = "world"

        target_pose = PoseStamped()
        target_pose.header.frame_id = msg.header.frame_id
        target_pose.pose.position = msg.pose.position
        if current_pose is not None:
            target_pose.pose.orientation = current_pose.orientation
        else:
            target_pose.pose.orientation = msg.pose.orientation

        ik_req.ik_request.pose_stamped = target_pose
        ik_req.ik_request.avoid_collisions = False
        ik_req.ik_request.timeout.sec = 10

        with self._lock:
            if self.current_joint_state is not None:
                js = self.current_joint_state
                ik_req.ik_request.robot_state.joint_state.name = list(js.name)
                ik_req.ik_request.robot_state.joint_state.position = list(js.position)

        try:
            ik_result = self.ik_client.call(ik_req)
            self._plan_after_ik_sync(ik_result, msg)
        except Exception as e:
            self.get_logger().error(f"规划 IK 调用异常: {e}")
            self._pub_plan_result(False, f"IK 调用异常: {e}")

    def _plan_after_ik_sync(self, ik_result, original_msg):
        """IK 成功后，用关节值做关节空间规划"""
        if ik_result is None or ik_result.error_code.val != 1:
            code = ik_result.error_code.val if ik_result else "timeout"
            self._pub_plan_result(False, f"IK 求解失败 (code={code}), 无法规划")
            return

        target_joints = {}
        for n, p in zip(ik_result.solution.joint_state.name, ik_result.solution.joint_state.position):
            if "arm_slider" in n:
                target_joints[n] = p

        self.get_logger().info(f"IK 成功, 开始关节空间规划: {target_joints}")

        if not self.plan_client.wait_for_service(timeout_sec=2.0):
            self._pub_plan_result(False, "plan_kinematic_path service 不可用")
            return

        from moveit_msgs.msg import JointConstraint
        plan_req = GetMotionPlan.Request()
        mp = plan_req.motion_plan_request
        mp.group_name = GROUP_NAME
        mp.num_planning_attempts = 10
        mp.allowed_planning_time = 5.0

        with self._lock:
            if self.current_joint_state is not None:
                js = self.current_joint_state
                mp.start_state.joint_state.name = list(js.name)
                mp.start_state.joint_state.position = list(js.position)

        goal = Constraints()
        for joint_name, joint_val in target_joints.items():
            jc = JointConstraint()
            jc.joint_name = joint_name
            jc.position = joint_val
            jc.tolerance_above = 0.01
            jc.tolerance_below = 0.01
            jc.weight = 1.0
            goal.joint_constraints.append(jc)
        mp.goal_constraints.append(goal)

        try:
            result = self.plan_client.call(plan_req)
            self._handle_plan_result(result)
        except Exception as e:
            self.get_logger().error(f"规划调用异常: {e}")
            self._pub_plan_result(False, f"规划调用异常: {e}")

    def _handle_plan_result(self, result):
        if result is None:
            self._pub_plan_result(False, "规划调用失败")
            return

        resp = result.motion_plan_response
        if resp.error_code.val == 1:
            traj = resp.trajectory
            n_points = len(traj.joint_trajectory.points)
            duration = 0.0
            if n_points > 0:
                last = traj.joint_trajectory.points[-1].time_from_start
                duration = last.sec + last.nanosec / 1e9
            self.get_logger().info(f"规划成功: {n_points} 点, {duration:.2f}s")

            display = DisplayTrajectory()
            display.trajectory.append(traj)
            with self._lock:
                if self.current_joint_state is not None:
                    display.trajectory_start.joint_state = self.current_joint_state
            self.display_traj_pub.publish(display)

            self._pub_plan_result(True, "规划成功", n_points, duration)

            self.get_logger().info("开始执行轨迹 (直接发布关节值)...")
            self._execute_trajectory_sim(traj)
        else:
            self.get_logger().warn(f"规划失败: error_code={resp.error_code.val}")
            self._pub_plan_result(False, f"规划失败 (code={resp.error_code.val})")

    def _execute_trajectory_sim(self, traj: RobotTrajectory):
        """通过 controller 执行轨迹"""
        jt = traj.joint_trajectory
        if not jt.points:
            return

        if self._use_controller and self._arm_action.server_is_ready():
            goal = FollowJointTrajectory.Goal()
            goal.trajectory = jt
            self.get_logger().info(f"通过 controller 执行轨迹 ({len(jt.points)} 点)...")
            future = self._arm_action.send_goal_async(goal)
            # 非阻塞，让 controller 自己执行
        else:
            prev_time = 0.0
            for point in jt.points:
                t = point.time_from_start.sec + point.time_from_start.nanosec / 1e9
                dt = t - prev_time
                if dt > 0:
                    time.sleep(dt)
                prev_time = t
                msg = JointState()
                msg.header.stamp = self.get_clock().now().to_msg()
                msg.name = list(jt.joint_names)
                msg.position = list(point.positions)
                # removed: self.joint_pub.publish(msg) — use controller only

        self.get_logger().info("轨迹执行完成")

    def _pub_plan_result(self, success, message, n_points=0, duration=0.0):
        msg = String()
        msg.data = json.dumps({
            "success": success,
            "message": message,
            "n_points": n_points,
            "duration": duration,
        })
        self.plan_result_pub.publish(msg)


def main():
    rclpy.init()
    node = JointControlBridge()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

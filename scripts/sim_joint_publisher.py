#!/usr/bin/env python3
"""
仿真关节状态发布器
发布 dummy2_robot 的 6 个关节的正弦波动画，用于测试 3D 前端关节同步。

运行方式：
    source ~/miniforge3/etc/profile.d/conda.sh && conda activate unilab
    python3 scripts/sim_joint_publisher.py
"""
import math
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState

JOINT_NAMES = [
    "dummy2_arm_Joint1",
    "dummy2_arm_Joint2",
    "dummy2_arm_Joint3",
    "dummy2_arm_Joint4",
    "dummy2_arm_Joint5",
    "dummy2_arm_Joint6",
]
AMPLITUDES = [0.5, -0.3, 0.4, 0.6, -0.4, 0.3]
PHASES = [0.0, 1.0, 2.0, 0.5, 1.5, 3.0]


class SimJointPublisher(Node):
    def __init__(self):
        super().__init__("sim_joint_publisher")
        self.pub = self.create_publisher(JointState, "/joint_states", 10)
        self.timer = self.create_timer(1.0 / 20.0, self._publish)  # 20 Hz
        self.t = 0.0
        self.get_logger().info("Sim joint publisher started at 20 Hz")

    def _publish(self):
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = JOINT_NAMES
        msg.position = [
            AMPLITUDES[i] * math.sin(self.t * 0.5 + PHASES[i])
            for i in range(len(JOINT_NAMES))
        ]
        msg.velocity = []
        msg.effort = []
        self.pub.publish(msg)
        self.t += 1.0 / 20.0


def main():
    rclpy.init()
    node = SimJointPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

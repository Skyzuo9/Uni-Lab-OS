#!/usr/bin/env python3
"""
仿真耗材位姿发布器
发布 resource_pose 话题，模拟培养板在实验台上的移动，用于测试 resource-tracker.js。

运行方式：
    python3 scripts/sim_resource_pose.py
"""
import math
import json
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class SimResourcePosePublisher(Node):
    def __init__(self):
        super().__init__("sim_resource_pose")
        self.pub = self.create_publisher(String, "resource_pose", 10)
        self.timer = self.create_timer(1.0 / 50.0, self._publish)  # 50 Hz
        self.t = 0.0
        self.get_logger().info("Sim resource pose publisher started at 50 Hz")

    def _publish(self):
        msg = String()
        data = {
            "resource_id": "plate_96_1",
            "pose": {
                "position": {
                    "x": 0.3 * math.cos(self.t * 0.3),
                    "y": 0.3 * math.sin(self.t * 0.3),
                    "z": 0.05,
                },
                "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
            },
            "attached": self.t % 10 < 5,
            "attached_to": "dummy2_arm_end_effector" if self.t % 10 < 5 else None,
        }
        msg.data = json.dumps(data)
        self.pub.publish(msg)
        self.t += 1.0 / 50.0


def main():
    rclpy.init()
    node = SimResourcePosePublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

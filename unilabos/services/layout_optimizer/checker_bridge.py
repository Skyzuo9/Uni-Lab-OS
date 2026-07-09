"""从 Uni-Lab-OS 的 registered_devices 中发现并桥接 MoveIt2 实例。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CheckerBridge:

    @staticmethod
    def discover_moveit2_instances() -> dict[str, Any]:
        try:
            from unilabos.ros.nodes.base_device_node import registered_devices
        except ImportError:
            logger.warning("Cannot import registered_devices (ROS2 not available)")
            return {}

        moveit2_instances: dict[str, Any] = {}
        for device_id, device_info in registered_devices.items():
            # driver_instance is the direct field in DeviceInfoType
            driver = device_info.get("driver_instance")
            if driver and hasattr(driver, "moveit2") and isinstance(driver.moveit2, dict):
                for group_name, m2 in driver.moveit2.items():
                    key = f"{device_id}_{group_name}"
                    moveit2_instances[key] = m2
                    logger.info("Found MoveIt2 instance: %s", key)
        logger.info("Discovered %d MoveIt2 instances: %s",
                     len(moveit2_instances), list(moveit2_instances.keys()))
        return moveit2_instances

    @staticmethod
    def discover_resource_mesh_manager() -> Any | None:
        try:
            from unilabos.ros.nodes.base_device_node import registered_devices
        except ImportError:
            return None
        for device_id, device_info in registered_devices.items():
            node = device_info.get("base_node_instance")
            if node and hasattr(node, "add_resource_collision_meshes"):
                return node
        return None

    @classmethod
    def create_checkers(cls, primary_arm_id: str | None = None) -> tuple[Any, Any]:
        instances = cls.discover_moveit2_instances()
        if not instances:
            raise RuntimeError("No MoveIt2 instances found in registered_devices")

        if primary_arm_id and primary_arm_id in instances:
            moveit2 = instances[primary_arm_id]
        else:
            moveit2 = next(iter(instances.values()))

        from .ros_checkers import MoveItCollisionChecker, IKFastReachabilityChecker
        collision = MoveItCollisionChecker(moveit2, sync_to_scene=True)
        reachability = IKFastReachabilityChecker(
            moveit2,
            voxel_dir=Path(__file__).parent / "voxel_maps",
        )
        return collision, reachability

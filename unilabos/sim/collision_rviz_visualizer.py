from __future__ import annotations

import math
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass
from typing import Any, Callable

from unilabos.sim.collision_event import CollisionEvent
from unilabos.utils import logger


@dataclass(frozen=True)
class LinkVisual:
    mesh_uri: str
    xyz: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rpy: tuple[float, float, float] = (0.0, 0.0, 0.0)
    parent_joint: str = ""


class UrdfVisualIndex:
    def __init__(self) -> None:
        self.links: dict[str, LinkVisual] = {}

    @classmethod
    def from_urdf(cls, urdf_text: str) -> "UrdfVisualIndex":
        index = cls()
        root = ET.fromstring(urdf_text)
        parent_joints = {
            child.attrib.get("link", ""): joint.attrib.get("name", "")
            for joint in root.findall("joint")
            if (child := joint.find("child")) is not None
        }
        for link in root.findall("link"):
            link_name = link.attrib.get("name", "")
            visual = link.find("visual")
            mesh = visual.find("./geometry/mesh") if visual is not None else None
            if not link_name or mesh is None or not mesh.attrib.get("filename"):
                continue
            origin = visual.find("origin") if visual is not None else None
            index.links[link_name] = LinkVisual(
                mesh_uri=mesh.attrib["filename"],
                xyz=_parse_vector(origin.attrib.get("xyz", "") if origin is not None else ""),
                rpy=_parse_vector(origin.attrib.get("rpy", "") if origin is not None else ""),
                parent_joint=parent_joints.get(link_name, ""),
            )
        return index

    def get(self, link_name: str) -> LinkVisual | None:
        return self.links.get(link_name)


class RvizCollisionSink:
    """Render colliding links as colored mesh overlays in RViz."""

    def __init__(
        self,
        *,
        publisher_provider: Callable[[], Any],
        visual_index: UrdfVisualIndex | None = None,
    ) -> None:
        self.publisher_provider = publisher_provider
        self.visual_index = visual_index or UrdfVisualIndex()
        self.unmapped_count = 0

    def update_urdf(self, urdf_text: str) -> None:
        self.visual_index = UrdfVisualIndex.from_urdf(urdf_text)

    def publish(self, event: CollisionEvent) -> None:
        publisher = self.publisher_provider()
        if publisher is None:
            return
        try:
            from visualization_msgs.msg import Marker, MarkerArray
        except ImportError as exc:
            logger.warning(f"[CollisionRViz] visualization_msgs unavailable: {exc}")
            return

        marker_array = MarkerArray()
        action = Marker.DELETE if event.event_phase == "end" else Marker.ADD
        for pair in event.pairs:
            for link_name in (pair.link_a, pair.link_b):
                if not link_name:
                    continue
                visual = self.visual_index.get(link_name)
                if visual is None:
                    self.unmapped_count += 1
                    logger.debug(f"[CollisionRViz] no visual mesh for link={link_name!r}")
                    continue
                marker = Marker()
                marker.header.frame_id = link_name
                marker.header.stamp.sec = 0
                marker.header.stamp.nanosec = 0
                marker.ns = f"collision_{event.event_id}"
                marker.id = _stable_marker_id(event.event_id, link_name)
                marker.type = Marker.MESH_RESOURCE
                marker.action = action
                marker.mesh_resource = visual.mesh_uri
                marker.mesh_use_embedded_materials = False
                marker.frame_locked = True
                marker.pose.position.x, marker.pose.position.y, marker.pose.position.z = visual.xyz
                (
                    marker.pose.orientation.x,
                    marker.pose.orientation.y,
                    marker.pose.orientation.z,
                    marker.pose.orientation.w,
                ) = _quaternion_from_rpy(*visual.rpy)
                marker.scale.x = marker.scale.y = marker.scale.z = 1.002
                marker.color.r, marker.color.g, marker.color.b, marker.color.a = _event_color(event)
                marker_array.markers.append(marker)
        for index, point in enumerate(event.contact.points):
            marker = Marker()
            marker.header.frame_id = "world"
            marker.ns = f"collision_points_{event.event_id}"
            marker.id = _stable_marker_id(event.event_id, f"contact_{index}")
            marker.type = Marker.SPHERE
            marker.action = action
            marker.pose.position.x = float(point.get("x", 0.0))
            marker.pose.position.y = float(point.get("y", 0.0))
            marker.pose.position.z = float(point.get("z", 0.0))
            marker.pose.orientation.w = 1.0
            marker.scale.x = marker.scale.y = marker.scale.z = 0.025
            marker.color.r, marker.color.g, marker.color.b, marker.color.a = _event_color(event)
            marker_array.markers.append(marker)
        if marker_array.markers:
            publisher.publish(marker_array)

    def close(self) -> None:
        publisher = self.publisher_provider()
        if publisher is None:
            return
        try:
            from visualization_msgs.msg import Marker, MarkerArray
        except ImportError:
            return
        marker = Marker()
        marker.action = Marker.DELETEALL
        marker_array = MarkerArray()
        marker_array.markers.append(marker)
        publisher.publish(marker_array)


def _parse_vector(value: str) -> tuple[float, float, float]:
    parts = value.split()
    if len(parts) != 3:
        return 0.0, 0.0, 0.0
    return float(parts[0]), float(parts[1]), float(parts[2])


def _quaternion_from_rpy(roll: float, pitch: float, yaw: float) -> tuple[float, float, float, float]:
    cr, sr = math.cos(roll / 2.0), math.sin(roll / 2.0)
    cp, sp = math.cos(pitch / 2.0), math.sin(pitch / 2.0)
    cy, sy = math.cos(yaw / 2.0), math.sin(yaw / 2.0)
    return (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )


def _stable_marker_id(event_id: str, link_name: str) -> int:
    return zlib.crc32(f"{event_id}:{link_name}".encode("utf-8")) & 0x7FFFFFFF


def _event_color(event: CollisionEvent) -> tuple[float, float, float, float]:
    if event.classification == "expected":
        return 1.0, 0.8, 0.0, 0.75
    if event.severity == "warning":
        return 1.0, 0.25, 0.0, 0.85
    return 1.0, 0.0, 0.0, 0.9

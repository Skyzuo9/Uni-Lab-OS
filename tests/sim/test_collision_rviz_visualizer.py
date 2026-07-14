from dataclasses import dataclass, field

from unilabos.sim.collision_event import CollisionEvent, CollisionPair
from unilabos.sim.collision_rviz_visualizer import RvizCollisionSink, UrdfVisualIndex


URDF = """
<robot name="test">
  <link name="base_link"/>
  <link name="arm3_Link">
    <visual>
      <origin xyz="0.1 0.2 0.3" rpy="0 0 0"/>
      <geometry><mesh filename="package://hor/meshes/arm3_Link.STL"/></geometry>
    </visual>
  </link>
  <joint name="arm3_joint" type="revolute">
    <parent link="base_link"/>
    <child link="arm3_Link"/>
  </joint>
</robot>
"""


@dataclass
class FakePublisher:
    messages: list = field(default_factory=list)

    def publish(self, message) -> None:
        self.messages.append(message)


def make_event(phase: str, classification: str = "unexpected") -> CollisionEvent:
    return CollisionEvent(
        event_id="col_1",
        event_phase=phase,
        timestamp_ms=1,
        sim_time_s=0.1,
        severity="warning",
        sim_engine="isaac",
        session_id="sim",
        pairs=(CollisionPair("fixture", "hor", link_b="arm3_Link"),),
        classification=classification,
    )


def test_urdf_visual_index_tracks_mesh_origin_and_parent_joint() -> None:
    visual = UrdfVisualIndex.from_urdf(URDF).get("arm3_Link")
    assert visual is not None
    assert visual.mesh_uri == "package://hor/meshes/arm3_Link.STL"
    assert visual.xyz == (0.1, 0.2, 0.3)
    assert visual.parent_joint == "arm3_joint"


def test_rviz_sink_adds_and_deletes_red_link_marker() -> None:
    publisher = FakePublisher()
    sink = RvizCollisionSink(
        publisher_provider=lambda: publisher,
        visual_index=UrdfVisualIndex.from_urdf(URDF),
    )

    sink.publish(make_event("begin"))
    begin_marker = publisher.messages[-1].markers[0]
    assert begin_marker.header.frame_id == "arm3_Link"
    assert begin_marker.mesh_resource == "package://hor/meshes/arm3_Link.STL"
    assert begin_marker.color.r == 1.0
    assert begin_marker.color.g == 0.25
    assert begin_marker.frame_locked is True
    assert begin_marker.action == begin_marker.ADD

    sink.publish(make_event("end"))
    end_marker = publisher.messages[-1].markers[0]
    assert end_marker.id == begin_marker.id
    assert end_marker.action == end_marker.DELETE


def test_rviz_sink_uses_expected_contact_color() -> None:
    publisher = FakePublisher()
    sink = RvizCollisionSink(
        publisher_provider=lambda: publisher,
        visual_index=UrdfVisualIndex.from_urdf(URDF),
    )
    sink.publish(make_event("begin", classification="expected"))
    marker = publisher.messages[-1].markers[0]
    assert marker.color.r == 1.0
    assert marker.color.g == 0.8


def test_rviz_sink_ignores_unmapped_links() -> None:
    publisher = FakePublisher()
    sink = RvizCollisionSink(publisher_provider=lambda: publisher)
    sink.publish(make_event("begin"))
    assert publisher.messages == []
    assert sink.unmapped_count == 1

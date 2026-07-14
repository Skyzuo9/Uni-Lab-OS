#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import xacro

from unilabos.sim.collision_bridge import CollisionEventBridge
from unilabos.sim.collision_event import CollisionEvent
from unilabos.sim.isaac_gateway import IsaacSimGateway


@dataclass
class RecordingSink:
    events: list[CollisionEvent] = field(default_factory=list)

    def publish(self, event: CollisionEvent) -> None:
        self.events.append(event)
        print(json.dumps(event.to_dict(), ensure_ascii=False), flush=True)

    def close(self) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HOR Horizon PhysX collision smoke test.")
    parser.add_argument("--endpoint", default="ws://127.0.0.1:9003/edge-sim/v1")
    parser.add_argument(
        "--macro",
        type=Path,
        default=Path("unilabos/device_mesh/devices/hor_horizon_v2_1/macro_device.xacro"),
    )
    parser.add_argument("--mesh-path", type=Path, default=Path("unilabos/device_mesh"))
    parser.add_argument("--import-wait-s", type=float, default=20.0)
    parser.add_argument("--collision-timeout-s", type=float, default=10.0)
    return parser.parse_args()


def expand_hor_urdf(macro_path: Path, mesh_path: Path) -> str:
    text = (
        '<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="full_dev">'
        '<link name="world"/>'
        f'<xacro:include filename="{macro_path.resolve()}"/>'
        f'<xacro:hor_horizon_v2_1 parent_link="world" mesh_path="{mesh_path.resolve()}" '
        'device_name="virtual_hor_horizon_"/>'
        "</robot>"
    )
    document = xacro.parse(io.StringIO(text))
    xacro.process_doc(document)
    return document.toxml()


def write_collision_fixture() -> Path:
    urdf = """
<robot name="collision_fixture">
  <link name="fixture_link">
    <inertial>
      <origin xyz="0 0 0"/>
      <mass value="10"/>
      <inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/>
    </inertial>
    <visual><geometry><box size="1.5 1.5 1.5"/></geometry></visual>
    <collision><geometry><box size="1.5 1.5 1.5"/></geometry></collision>
  </link>
</robot>
""".strip()
    path = Path(tempfile.gettempdir()) / "hor_collision_fixture.urdf"
    path.write_text(urdf, encoding="utf-8")
    return path


def main() -> int:
    args = parse_args()
    sink = RecordingSink()
    bridge = CollisionEventBridge(
        sinks=[sink],
        update_interval_ms=1000,
        end_grace_ms=500,
    )
    gateway = IsaacSimGateway(endpoint=args.endpoint, heartbeat_interval_ms=2000)
    gateway.add_collision_handler(bridge.submit)
    bridge.start()
    gateway.start()
    try:
        if not gateway.wait_world_ready(30):
            raise RuntimeError("Isaac world did not become ready")
        gateway.upsert_scene_urdf(expand_hor_urdf(args.macro, args.mesh_path))
        time.sleep(args.import_wait_s)
        fixture_path = write_collision_fixture()
        gateway.upsert_asset(
            {
                "asset_id": "collision_fixture",
                "asset_kind": "device",
                "format": "urdf",
                "source_uri": fixture_path.as_uri(),
                "prim_path": "/World/collision_fixture",
                "pose": {
                    "frame_id": "world",
                    "position_m": {"x": 0.0, "y": 0.0, "z": 0.25},
                    "orientation_xyzw": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                },
                "metadata": {"id": "collision_fixture"},
                "replace_if_exists": True,
            }
        )
        deadline = time.monotonic() + args.collision_timeout_s
        while time.monotonic() < deadline and not any(event.event_phase == "begin" for event in sink.events):
            time.sleep(0.1)
        begin_events = [event for event in sink.events if event.event_phase == "begin"]
        if not begin_events:
            raise RuntimeError("No normalized collision begin event received")
        first = begin_events[0]
        if not any("virtual_hor_horizon_" in (pair.link_a + pair.link_b) for pair in first.pairs):
            raise RuntimeError(f"HOR link not identified in collision: {first.to_dict()}")
        print(
            json.dumps(
                {
                    "result": "passed",
                    "raw_payloads": bridge.stats.received,
                    "normalized_events": bridge.stats.emitted,
                    "deduplicated": bridge.stats.deduplicated,
                    "first_event_id": first.event_id,
                }
            ),
            flush=True,
        )
        return 0
    finally:
        gateway.stop()
        bridge.stop()


if __name__ == "__main__":
    raise SystemExit(main())

from dataclasses import dataclass, field

from unilabos.sim.collision_bridge import CollisionEventBridge
from unilabos.sim.collision_event import CollisionEvent


@dataclass
class RecordingSink:
    events: list[CollisionEvent] = field(default_factory=list)

    def publish(self, event: CollisionEvent) -> None:
        self.events.append(event)

    def close(self) -> None:
        return


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def collision_payload() -> dict:
    return {
        "event_id": "raw_1",
        "severity": "warn",
        "sim_time_s": 2.5,
        "pairs": [
            {
                "a_asset_id": "hor_horizon",
                "b_asset_id": "fixture_box",
                "a_link": "arm3_Link",
                "b_link": "box_link",
                "a_prim_path": "/World/HOR/arm3_Link",
                "b_prim_path": "/World/Fixture/box_link",
            }
        ],
    }


def test_bridge_emits_begin_update_and_end_with_stable_id() -> None:
    clock = FakeClock()
    sink = RecordingSink()
    bridge = CollisionEventBridge(
        sinks=[sink],
        clock=clock,
        wall_clock_ms=lambda: int(clock() * 1000),
        update_interval_ms=1000,
        end_grace_ms=500,
    )

    begin = bridge.process_payload(collision_payload())
    assert [event.event_phase for event in begin] == ["begin"]
    assert begin[0].event_id == "raw_1"
    assert begin[0].pairs[0].link_b == "arm3_Link"

    clock.advance(0.1)
    assert bridge.process_payload(collision_payload()) == []
    assert bridge.stats.deduplicated == 1

    clock.advance(1.0)
    update = bridge.process_payload(collision_payload())
    assert [event.event_phase for event in update] == ["update"]
    assert update[0].event_id == begin[0].event_id

    clock.advance(0.6)
    ended = bridge.poll_expired()
    assert [event.event_phase for event in ended] == ["end"]
    assert ended[0].event_id == begin[0].event_id
    assert bridge.active_count() == 0


def test_bridge_enriches_workflow_context() -> None:
    sink = RecordingSink()
    bridge = CollisionEventBridge(
        sinks=[sink],
        workflow_context_provider=lambda pair: {
            "task_id": "task-1",
            "job_id": "job-1",
            "device_id": "hor_horizon",
            "action": "run_collision_demo",
        },
    )

    event = bridge.process_payload(collision_payload())[0]
    assert event.workflow_context.task_id == "task-1"
    assert event.workflow_context.job_id == "job-1"
    assert event.workflow_context.action == "run_collision_demo"


def test_bridge_honors_explicit_physx_contact_lost() -> None:
    bridge = CollisionEventBridge()
    bridge.process_payload(collision_payload())
    lost = collision_payload()
    lost["pairs"][0]["event_phase"] = "end"

    events = bridge.process_payload(lost)

    assert [event.event_phase for event in events] == ["end"]
    assert bridge.active_count() == 0


def test_bridge_drops_invalid_pair_without_raising() -> None:
    bridge = CollisionEventBridge()
    assert bridge.process_payload({"pairs": [{"asset_a": "only_one"}]}) == []
    assert bridge.stats.invalid == 1


def test_bridge_isolates_sink_errors() -> None:
    class BrokenSink:
        def publish(self, event: CollisionEvent) -> None:
            raise RuntimeError("broken")

        def close(self) -> None:
            return

    recording = RecordingSink()
    bridge = CollisionEventBridge(sinks=[BrokenSink(), recording])
    bridge.process_payload(collision_payload())

    assert bridge.stats.sink_errors == 1
    assert len(recording.events) == 1

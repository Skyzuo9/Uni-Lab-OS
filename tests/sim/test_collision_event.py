import pytest

from unilabos.sim.collision_event import CollisionEvent, CollisionPair, normalize_severity


def test_collision_pair_normalizes_direction() -> None:
    pair = CollisionPair.from_payload(
        {
            "a_asset_id": "z_device",
            "b_asset_id": "a_device",
            "a_link": "z_link",
            "b_link": "a_link",
        }
    )

    assert pair.asset_a == "a_device"
    assert pair.link_a == "a_link"
    assert pair.asset_b == "z_device"
    assert pair.key == "a_device|a_link||z_device|z_link|"


def test_collision_pair_requires_two_assets() -> None:
    with pytest.raises(ValueError, match="requires two assets"):
        CollisionPair.from_payload({"asset_a": "only_one"})


def test_severity_alias_and_validation() -> None:
    assert normalize_severity("warn") == "warning"
    assert normalize_severity(None) == "warning"
    with pytest.raises(ValueError, match="Unsupported collision severity"):
        normalize_severity("fatal")


def test_collision_event_serializes_nested_dataclasses() -> None:
    event = CollisionEvent(
        event_id="col_1",
        event_phase="begin",
        timestamp_ms=10,
        sim_time_s=0.2,
        severity="warning",
        sim_engine="isaac",
        session_id="sim_1",
        pairs=(CollisionPair("a", "b"),),
    )

    payload = event.to_dict()
    assert payload["schema_version"] == "1.0"
    assert payload["pairs"] == [
        {
            "asset_a": "a",
            "asset_b": "b",
            "link_a": "",
            "link_b": "",
            "prim_a": "",
            "prim_b": "",
        }
    ]
    assert payload["workflow_context"]["job_id"] == ""


def test_collision_event_rejects_invalid_phase() -> None:
    with pytest.raises(ValueError, match="event phase"):
        CollisionEvent(
            event_id="col_1",
            event_phase="active",
            timestamp_ms=10,
            sim_time_s=0.2,
            severity="warning",
            sim_engine="isaac",
            session_id="sim_1",
            pairs=(CollisionPair("a", "b"),),
        )

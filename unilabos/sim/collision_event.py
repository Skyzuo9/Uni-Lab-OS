from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


SCHEMA_VERSION = "1.0"
EVENT_PHASES = frozenset({"begin", "update", "end"})
SEVERITIES = frozenset({"info", "warning", "critical"})
CLASSIFICATIONS = frozenset({"expected", "unexpected", "self_collision", "environment", "unknown"})


def normalize_severity(value: str | None) -> str:
    severity = (value or "warning").lower()
    if severity == "warn":
        severity = "warning"
    if severity not in SEVERITIES:
        raise ValueError(f"Unsupported collision severity: {value!r}")
    return severity


def normalize_classification(value: str | None) -> str:
    classification = (value or "unknown").lower()
    if classification not in CLASSIFICATIONS:
        return "unknown"
    return classification


@dataclass(frozen=True)
class CollisionPair:
    asset_a: str
    asset_b: str
    link_a: str = ""
    link_b: str = ""
    prim_a: str = ""
    prim_b: str = ""

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "CollisionPair":
        pair = cls(
            asset_a=str(payload.get("asset_a") or payload.get("a_asset_id") or payload.get("body_a") or ""),
            asset_b=str(payload.get("asset_b") or payload.get("b_asset_id") or payload.get("body_b") or ""),
            link_a=str(payload.get("link_a") or payload.get("a_link") or ""),
            link_b=str(payload.get("link_b") or payload.get("b_link") or ""),
            prim_a=str(payload.get("prim_a") or payload.get("a_prim_path") or ""),
            prim_b=str(payload.get("prim_b") or payload.get("b_prim_path") or ""),
        )
        if not pair.asset_a or not pair.asset_b:
            raise ValueError(f"Collision pair requires two assets: {payload!r}")
        return pair.normalized()

    def normalized(self) -> "CollisionPair":
        left = (self.asset_a, self.link_a, self.prim_a)
        right = (self.asset_b, self.link_b, self.prim_b)
        if left <= right:
            return self
        return CollisionPair(
            asset_a=self.asset_b,
            asset_b=self.asset_a,
            link_a=self.link_b,
            link_b=self.link_a,
            prim_a=self.prim_b,
            prim_b=self.prim_a,
        )

    @property
    def key(self) -> str:
        return "|".join((self.asset_a, self.link_a, self.prim_a, self.asset_b, self.link_b, self.prim_b))


@dataclass(frozen=True)
class WorkflowContext:
    task_id: str = ""
    job_id: str = ""
    node_id: str = ""
    device_id: str = ""
    action: str = ""
    notebook_id: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "WorkflowContext":
        value = value or {}
        return cls(
            task_id=str(value.get("task_id") or ""),
            job_id=str(value.get("job_id") or ""),
            node_id=str(value.get("node_id") or ""),
            device_id=str(value.get("device_id") or ""),
            action=str(value.get("action") or value.get("action_name") or ""),
            notebook_id=str(value.get("notebook_id") or ""),
        )


@dataclass(frozen=True)
class ContactSummary:
    point_count: int = 0
    max_impulse: float | None = None
    relative_velocity: float | None = None
    points: tuple[Mapping[str, float], ...] = ()


@dataclass(frozen=True)
class CollisionEvent:
    event_id: str
    event_phase: str
    timestamp_ms: int
    sim_time_s: float
    severity: str
    sim_engine: str
    session_id: str
    pairs: tuple[CollisionPair, ...]
    classification: str = "unknown"
    contact: ContactSummary = field(default_factory=ContactSummary)
    workflow_context: WorkflowContext = field(default_factory=WorkflowContext)
    extra: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("Collision event_id is required")
        if self.event_phase not in EVENT_PHASES:
            raise ValueError(f"Unsupported collision event phase: {self.event_phase!r}")
        if self.severity not in SEVERITIES:
            raise ValueError(f"Unsupported collision severity: {self.severity!r}")
        if self.classification not in CLASSIFICATIONS:
            raise ValueError(f"Unsupported collision classification: {self.classification!r}")
        if self.timestamp_ms < 0:
            raise ValueError("Collision timestamp_ms must be non-negative")
        if not self.pairs:
            raise ValueError("Collision event requires at least one pair")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["pairs"] = list(payload["pairs"])
        return payload

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from unilabos.sim.collision_event import (
    CollisionEvent,
    CollisionPair,
    ContactSummary,
    WorkflowContext,
    normalize_classification,
    normalize_severity,
)
from unilabos.utils import logger


class CollisionSink(Protocol):
    def publish(self, event: CollisionEvent) -> None: ...

    def close(self) -> None: ...


@dataclass
class CollisionStats:
    received: int = 0
    emitted: int = 0
    deduplicated: int = 0
    dropped: int = 0
    invalid: int = 0
    sink_errors: int = 0


@dataclass
class _ActiveCollision:
    event_id: str
    pair: CollisionPair
    first_seen: float
    last_seen: float
    last_emitted: float
    severity: str
    classification: str
    sim_time_s: float
    session_id: str
    contact: ContactSummary
    workflow_context: WorkflowContext
    extra: Mapping[str, Any]


class LoggingCollisionSink:
    def publish(self, event: CollisionEvent) -> None:
        logger.warning(
            f"[Collision] phase={event.event_phase} severity={event.severity} "
            f"pairs={[pair.key for pair in event.pairs]} event_id={event.event_id}"
        )

    def close(self) -> None:
        return


class JsonlCollisionSink:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def publish(self, event: CollisionEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":"))
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.write("\n")

    def close(self) -> None:
        return


class CommunicationCollisionSink:
    def __init__(self, communication_client: Any) -> None:
        self.communication_client = communication_client

    def publish(self, event: CollisionEvent) -> None:
        self.communication_client.publish_collision_event(event.to_dict())

    def close(self) -> None:
        return


class CollisionEventBridge:
    """Normalize Isaac contacts, control event lifecycle, and fan out to sinks."""

    def __init__(
        self,
        *,
        sinks: list[CollisionSink] | None = None,
        workflow_context_provider: Callable[[CollisionPair], Mapping[str, Any] | None] | None = None,
        queue_size: int = 1024,
        update_interval_ms: int = 1000,
        end_grace_ms: int = 2000,
        clock: Callable[[], float] = time.monotonic,
        wall_clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        self.sinks = list(sinks or [])
        self.workflow_context_provider = workflow_context_provider
        self.update_interval_s = max(0, update_interval_ms) / 1000.0
        self.end_grace_s = max(1, end_grace_ms) / 1000.0
        self.clock = clock
        self.wall_clock_ms = wall_clock_ms
        self.stats = CollisionStats()

        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=max(1, queue_size))
        self._active: dict[str, _ActiveCollision] = {}
        self._lock = threading.RLock()
        self._running = False
        self._thread: threading.Thread | None = None

    def add_sink(self, sink: CollisionSink) -> None:
        with self._lock:
            self.sinks.append(sink)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="collision_event_bridge", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        now = self.clock()
        with self._lock:
            keys = list(self._active)
        for key in keys:
            self._emit_end(key, now)
        for sink in list(self.sinks):
            try:
                sink.close()
            except Exception as exc:
                self.stats.sink_errors += 1
                logger.warning(f"[CollisionBridge] sink close failed: {exc}")

    def submit(self, payload: Mapping[str, Any]) -> bool:
        try:
            self._queue.put_nowait(dict(payload))
            return True
        except queue.Full:
            self.stats.dropped += 1
            logger.warning("[CollisionBridge] input queue full; collision payload dropped")
            return False

    def process_payload(self, payload: Mapping[str, Any]) -> list[CollisionEvent]:
        """Synchronous processing hook used by the worker and unit tests."""
        self.stats.received += 1
        raw_pairs = payload.get("pairs")
        if not isinstance(raw_pairs, list):
            raw_pairs = [payload]

        emitted: list[CollisionEvent] = []
        now = self.clock()
        for index, raw_pair in enumerate(raw_pairs):
            if not isinstance(raw_pair, Mapping):
                self.stats.invalid += 1
                continue
            try:
                pair = CollisionPair.from_payload(raw_pair)
                severity = normalize_severity(str(payload.get("severity") or "warning"))
            except (TypeError, ValueError) as exc:
                self.stats.invalid += 1
                logger.warning(f"[CollisionBridge] invalid collision payload: {exc}")
                continue

            key = pair.key
            with self._lock:
                active = self._active.get(key)
                phase_hint = str(raw_pair.get("event_phase") or payload.get("event_phase") or "")
                if phase_hint == "end":
                    if active is None:
                        self.stats.deduplicated += 1
                        continue
                    self._active.pop(key, None)
                    event = self._build_event(active, "end")
                    self._publish(event)
                    emitted.append(event)
                    continue
                if active is None:
                    context_value = self.workflow_context_provider(pair) if self.workflow_context_provider else None
                    event_id = str(payload.get("event_id") or f"col_{uuid.uuid4().hex}")
                    if len(raw_pairs) > 1:
                        event_id = f"{event_id}_{index}"
                    active = _ActiveCollision(
                        event_id=event_id,
                        pair=pair,
                        first_seen=now,
                        last_seen=now,
                        last_emitted=now,
                        severity=severity,
                        classification=normalize_classification(str(payload.get("classification") or "unknown")),
                        sim_time_s=float(payload.get("sim_time_s") or 0.0),
                        session_id=str(payload.get("session_id") or ""),
                        contact=self._contact_from_payload(payload),
                        workflow_context=WorkflowContext.from_mapping(context_value),
                        extra=self._extra_from_payload(payload),
                    )
                    self._active[key] = active
                    event = self._build_event(active, "begin")
                    self._publish(event)
                    emitted.append(event)
                    continue

                active.last_seen = now
                active.severity = severity
                active.sim_time_s = float(payload.get("sim_time_s") or active.sim_time_s)
                active.contact = self._contact_from_payload(payload)
                active.extra = self._extra_from_payload(payload)
                if now - active.last_emitted >= self.update_interval_s:
                    active.last_emitted = now
                    event = self._build_event(active, "update")
                    self._publish(event)
                    emitted.append(event)
                else:
                    self.stats.deduplicated += 1
        return emitted

    def poll_expired(self) -> list[CollisionEvent]:
        now = self.clock()
        with self._lock:
            expired = [key for key, active in self._active.items() if now - active.last_seen >= self.end_grace_s]
        events: list[CollisionEvent] = []
        for key in expired:
            event = self._emit_end(key, now)
            if event is not None:
                events.append(event)
        return events

    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def _run(self) -> None:
        poll_interval = min(0.1, self.end_grace_s / 2.0)
        while self._running:
            try:
                payload = self._queue.get(timeout=max(0.01, poll_interval))
            except queue.Empty:
                self.poll_expired()
                continue
            try:
                self.process_payload(payload)
            except Exception as exc:
                self.stats.invalid += 1
                logger.exception(f"[CollisionBridge] payload processing failed: {exc}")
            finally:
                self._queue.task_done()
            self.poll_expired()

    def _emit_end(self, key: str, now: float) -> CollisionEvent | None:
        with self._lock:
            active = self._active.pop(key, None)
            if active is None:
                return None
            active.last_seen = now
            event = self._build_event(active, "end")
        self._publish(event)
        return event

    def _build_event(self, active: _ActiveCollision, phase: str) -> CollisionEvent:
        return CollisionEvent(
            event_id=active.event_id,
            event_phase=phase,
            timestamp_ms=self.wall_clock_ms(),
            sim_time_s=active.sim_time_s,
            severity=active.severity,
            sim_engine="isaac",
            session_id=active.session_id,
            pairs=(active.pair,),
            classification=active.classification,
            contact=active.contact,
            workflow_context=active.workflow_context,
            extra=active.extra,
        )

    def _publish(self, event: CollisionEvent) -> None:
        for sink in list(self.sinks):
            try:
                sink.publish(event)
            except Exception as exc:
                self.stats.sink_errors += 1
                logger.warning(f"[CollisionBridge] sink publish failed: {exc}")
        self.stats.emitted += 1

    @staticmethod
    def _contact_from_payload(payload: Mapping[str, Any]) -> ContactSummary:
        contact = payload.get("contact")
        contact = contact if isinstance(contact, Mapping) else {}
        max_impulse = contact.get("max_impulse", payload.get("max_impulse"))
        relative_velocity = contact.get("relative_velocity", payload.get("relative_velocity"))
        return ContactSummary(
            point_count=int(contact.get("point_count", payload.get("point_count", 0)) or 0),
            max_impulse=float(max_impulse) if max_impulse is not None else None,
            relative_velocity=float(relative_velocity) if relative_velocity is not None else None,
            points=tuple(contact.get("points") or ()),
        )

    @staticmethod
    def _extra_from_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        ignored = {
            "event_id",
            "pairs",
            "severity",
            "classification",
            "sim_time_s",
            "session_id",
            "contact",
            "point_count",
            "max_impulse",
            "relative_velocity",
        }
        return {key: value for key, value in payload.items() if key not in ignored}

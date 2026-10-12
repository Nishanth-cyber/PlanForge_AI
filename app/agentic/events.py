"""Append-only runtime event log for agentic runs.

Events are emitted *while the workflow executes* (never reconstructed afterwards), so a UI can poll
``since(seq)`` and show genuine progress. Payloads are JSON-safe and contain no prompts, raw LLM replies
or credentials.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

from app.agentic.util import to_jsonable


@dataclass(frozen=True)
class AgentEvent:
    seq: int
    ts: float
    type: str
    agent: str
    summary: str
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EventSink(Protocol):
    def emit(self, type: str, agent: str, summary: str, data: Optional[Dict[str, Any]] = None) -> AgentEvent: ...


class InMemoryEventLog:
    """Thread-safe in-memory sink. Listener errors never affect the run."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._events: List[AgentEvent] = []
        self._listeners: List[Callable[[AgentEvent], None]] = []

    def add_listener(self, listener: Callable[[AgentEvent], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def emit(self, type: str, agent: str, summary: str, data: Optional[Dict[str, Any]] = None) -> AgentEvent:
        with self._lock:
            event = AgentEvent(
                seq=len(self._events) + 1,
                ts=self._clock(),
                type=type,
                agent=agent,
                summary=summary,
                data=to_jsonable(data or {}),
            )
            self._events.append(event)
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(event)
            except Exception:  # noqa: BLE001 - observers must never break a run
                pass
        return event

    def since(self, seq: int = 0) -> List[AgentEvent]:
        with self._lock:
            return [e for e in self._events if e.seq > seq]

    def all(self) -> List[AgentEvent]:
        return self.since(0)

    @property
    def events(self) -> List[AgentEvent]:
        return self.all()

    def types(self) -> List[str]:
        return [e.type for e in self.all()]

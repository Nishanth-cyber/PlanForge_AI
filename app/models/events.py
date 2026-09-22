"""Event models for pipeline explainability and decision tracking.

Events capture structured decisions and transitions across all seven stages:
- Requirement
- Planning
- ASAA
- Architectural LLM
- Geometry Engine
- Validator
- Refinement Agent
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from app.utils.ids import generate_id


@dataclass
class Event:
    """A single structured event in the pipeline."""
    id: str = field(default_factory=generate_id)
    timestamp: datetime = field(default_factory=datetime.now)
    stage: str = ""  # "requirement", "planning", "asaa", "architectural_llm", "geometry", "validation", "refinement", "system"
    event_type: str = ""  # e.g. "REQUIREMENTS_PARSED", "REGIONS_ALLOCATED", "VALIDATION_EVALUATED"
    message: str = ""
    data: Optional[dict] = None
    metadata: Optional[dict] = None
    execution_time_ms: Optional[float] = None


@dataclass
class EventLog:
    """Complete chronological event log across the pipeline execution."""
    id: str = field(default_factory=generate_id)
    events: list[Event] = field(default_factory=list)

    def add_event(
        self,
        event_type: str,
        stage: str,
        message: str,
        data: Optional[dict] = None,
        metadata: Optional[dict] = None,
        execution_time_ms: Optional[float] = None,
    ) -> Event:
        """Create, append, and return a new pipeline event."""
        event = Event(
            event_type=event_type,
            stage=stage,
            message=message,
            data=data,
            metadata=metadata,
            execution_time_ms=execution_time_ms,
        )
        self.events.append(event)
        return event

    def get_events_by_stage(self, stage: str) -> list[Event]:
        """Filter events originating from a specific pipeline stage."""
        return [e for e in self.events if e.stage.lower() == stage.lower()]

    def get_events_by_type(self, event_type: str) -> list[Event]:
        """Filter events of a specific event type."""
        return [e for e in self.events if e.event_type.lower() == event_type.lower()]

    def clear(self) -> None:
        """Clear all events in the log."""
        self.events.clear()

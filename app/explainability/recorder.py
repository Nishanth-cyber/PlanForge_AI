"""Runtime trace recorder for non-invasive event accumulation.

The TraceRecorder observes pipeline stages and accumulates DecisionEvents without
altering business logic or mutating pipeline models.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.explainability.events import (
    create_alternative_event,
    create_architectural_event,
    create_asaa_event,
    create_diversity_event,
    create_geometry_event,
    create_planning_event,
    create_refinement_event,
    create_requirement_event,
    create_validation_event,
)
from app.explainability.models import (
    AlternativeTrace,
    DecisionEvent,
    DecisionTrace,
    DecisionType,
    EntityTraceChain,
    ProvenanceSource,
    StageName,
    StageTrace,
)
from app.utils.ids import generate_id


class TraceRecorder:
    """Non-invasive observer and accumulator for decision events."""

    def __init__(self, project_name: str = "") -> None:
        self.project_name = project_name
        self.events: list[DecisionEvent] = []
        self.alternatives: list[AlternativeTrace] = []

    def record_event(self, event: DecisionEvent) -> DecisionEvent:
        """Record an already constructed DecisionEvent."""
        self.events.append(event)
        return event

    def record_requirement(
        self,
        entity_id: str,
        entity_type: str,
        reason: str,
        evidence: dict[str, Any],
        constraints: Optional[dict[str, Any]] = None,
        floor_number: Optional[int] = None,
    ) -> DecisionEvent:
        """Record a requirement parsed event."""
        evt = create_requirement_event(
            entity_id=entity_id,
            entity_type=entity_type,
            reason=reason,
            evidence=evidence,
            constraints=constraints,
            floor_number=floor_number,
        )
        return self.record_event(evt)

    def record_planning(
        self,
        event_type: DecisionType,
        source: ProvenanceSource,
        entity_id: str,
        reason: str,
        evidence: dict[str, Any],
        entity_type: str = "room",
        floor_number: Optional[int] = None,
    ) -> DecisionEvent:
        """Record a planning agent decision event."""
        evt = create_planning_event(
            event_type=event_type,
            source=source,
            entity_id=entity_id,
            reason=reason,
            evidence=evidence,
            entity_type=entity_type,
            floor_number=floor_number,
        )
        return self.record_event(evt)

    def record_asaa(
        self,
        event_type: DecisionType,
        entity_id: str,
        reason: str,
        evidence: dict[str, Any],
        entity_type: str = "region",
        floor_number: Optional[int] = None,
    ) -> DecisionEvent:
        """Record an ASAA spatial allocation decision event."""
        evt = create_asaa_event(
            event_type=event_type,
            entity_id=entity_id,
            reason=reason,
            evidence=evidence,
            entity_type=entity_type,
            floor_number=floor_number,
        )
        return self.record_event(evt)

    def record_architectural(
        self,
        event_type: DecisionType,
        entity_id: str,
        reason: str,
        evidence: dict[str, Any],
        entity_type: str = "room",
        floor_number: Optional[int] = None,
    ) -> DecisionEvent:
        """Record an architectural LLM intent event."""
        evt = create_architectural_event(
            event_type=event_type,
            entity_id=entity_id,
            reason=reason,
            evidence=evidence,
            entity_type=entity_type,
            floor_number=floor_number,
        )
        return self.record_event(evt)

    def record_geometry(
        self,
        entity_id: str,
        reason: str,
        evidence: dict[str, Any],
        entity_type: str = "room",
        floor_number: Optional[int] = None,
    ) -> DecisionEvent:
        """Record a geometry construction fact event."""
        evt = create_geometry_event(
            entity_id=entity_id,
            reason=reason,
            evidence=evidence,
            entity_type=entity_type,
            floor_number=floor_number,
        )
        return self.record_event(evt)

    def record_validation(
        self,
        event_type: DecisionType,
        entity_id: Optional[str],
        check: str,
        reason: str,
        evidence: dict[str, Any],
        severity: str = "error",
        floor_number: Optional[int] = None,
    ) -> DecisionEvent:
        """Record a validation check or issue event."""
        evt = create_validation_event(
            event_type=event_type,
            entity_id=entity_id,
            check=check,
            reason=reason,
            evidence=evidence,
            severity=severity,
            floor_number=floor_number,
        )
        return self.record_event(evt)

    def record_refinement(
        self,
        event_type: DecisionType,
        entity_id: str,
        reason: str,
        evidence: dict[str, Any],
        validation_issue_ids: Optional[list[str]] = None,
        floor_number: Optional[int] = None,
    ) -> DecisionEvent:
        """Record a refinement iteration event."""
        evt = create_refinement_event(
            event_type=event_type,
            entity_id=entity_id,
            reason=reason,
            evidence=evidence,
            validation_issue_ids=validation_issue_ids,
            floor_number=floor_number,
        )
        return self.record_event(evt)

    def record_diversity(
        self,
        event_type: DecisionType,
        entity_id: str,
        reason: str,
        evidence: dict[str, Any],
        status: str = "success",
    ) -> DecisionEvent:
        """Record a diversity evaluation event."""
        evt = create_diversity_event(
            event_type=event_type,
            entity_id=entity_id,
            reason=reason,
            evidence=evidence,
            status=status,
        )
        return self.record_event(evt)

    def record_alternative(
        self,
        event_type: DecisionType,
        alternative_id: str,
        reason: str,
        evidence: dict[str, Any],
        status: str = "accepted",
    ) -> DecisionEvent:
        """Record an alternative acceptance or rejection event."""
        evt = create_alternative_event(
            event_type=event_type,
            alternative_id=alternative_id,
            reason=reason,
            evidence=evidence,
            status=status,
        )
        return self.record_event(evt)

    def add_alternative_trace(self, alt_trace: AlternativeTrace) -> None:
        """Register an alternative trace."""
        self.alternatives.append(alt_trace)

    def build_trace(self, project_name: Optional[str] = None) -> DecisionTrace:
        """Assemble all accumulated events into a linked DecisionTrace."""
        proj = project_name or self.project_name or "Residential Project"

        # Group events by stage
        stages_map: dict[str, list[DecisionEvent]] = {
            s.value: [] for s in StageName
        }
        for e in self.events:
            if e.stage in stages_map:
                stages_map[e.stage].append(e)
            else:
                stages_map.setdefault(e.stage, []).append(e)

        stage_traces = [
            StageTrace(
                stage_name=stage_name,
                events=evts,
                summary=f"Recorded {len(evts)} decision events in {stage_name} stage.",
            )
            for stage_name, evts in stages_map.items()
            if evts
        ]

        # Assemble entity chains (for rooms)
        entity_chains: dict[str, EntityTraceChain] = {}
        for e in self.events:
            if e.entity_id and e.entity_type == "room":
                chain = entity_chains.setdefault(
                    e.entity_id,
                    EntityTraceChain(
                        entity_id=e.entity_id,
                        entity_type="room",
                        room_type=e.evidence.get("room_type", ""),
                        floor_number=e.floor_number or 1,
                        events=[],
                    ),
                )
                chain.events.append(e)
                if not chain.room_type and e.evidence.get("room_type"):
                    chain.room_type = e.evidence["room_type"]

        return DecisionTrace(
            trace_id=generate_id("trace"),
            project_name=proj,
            stages=stage_traces,
            alternatives=list(self.alternatives),
            entity_chains=entity_chains,
        )

    def clear(self) -> None:
        """Reset the recorder."""
        self.events.clear()
        self.alternatives.clear()

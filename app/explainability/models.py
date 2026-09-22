"""Data models for PlanForge AI Explainability and Decision Trace (Phase 10).

This module defines the structured models capturing decisions, evidence, provenance,
and entity trace chains across the entire floor-plan generation pipeline:
Requirements -> Planning -> ASAA -> Architectural LLM -> Geometry -> Validator -> Refinement -> Diversity -> Final Selection.

Critical Invariant:
Stores DECISIONS, EVIDENCE, and RATIONALES.
Strictly NEVER stores internal LLM chain-of-thought, private reasoning traces,
or model scratchpads.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from app.utils.ids import generate_id


class StageName(str, Enum):
    """Pipeline stages participating in decision tracking."""
    REQUIREMENT = "requirement"
    PLANNING = "planning"
    ASAA_ALLOCATION = "asaa_allocation"
    ARCHITECTURAL_DESIGN = "architectural_design"
    GEOMETRY = "geometry"
    VALIDATION = "validation"
    REFINEMENT = "refinement"
    DIVERSITY = "diversity"
    FINAL_SELECTION = "final_selection"


class ProvenanceSource(str, Enum):
    """Authoritative sources of decisions across the system."""
    USER = "user"
    RULE = "rule"
    PLANNING_AGENT = "planning_agent"
    ASAA = "asaa"
    ARCHITECTURAL_LLM = "architectural_llm"
    GEOMETRY_ENGINE = "geometry_engine"
    VALIDATOR = "validator"
    REFINEMENT_LLM = "refinement_llm"
    DIVERSITY_ENGINE = "diversity_engine"
    SYSTEM_DERIVED = "system_derived"


class DecisionType(str, Enum):
    """Controlled vocabulary of architectural decision types."""
    REQUIREMENT_PARSED = "requirement_parsed"
    ROOM_CLASSIFIED = "room_classified"
    PRIORITY_ASSIGNED = "priority_assigned"
    RELATIONSHIP_CREATED = "relationship_created"
    ALLOCATION_ASSIGNED = "allocation_assigned"
    ALLOCATION_SCORED = "allocation_scored"
    STRATEGY_SELECTED = "strategy_selected"
    ROOM_SHAPE_SELECTED = "room_shape_selected"
    ROOM_DIMENSIONS_SELECTED = "room_dimensions_selected"
    DOOR_INTENT_CREATED = "door_intent_created"
    WINDOW_INTENT_CREATED = "window_intent_created"
    STAIRCASE_INTENT_CREATED = "staircase_intent_created"
    GEOMETRY_CONSTRUCTED = "geometry_constructed"
    VALIDATION_CHECKED = "validation_checked"
    VALIDATION_FAILURE = "validation_failure"
    VALIDATION_WARNING = "validation_warning"
    REFINEMENT_PROPOSED = "refinement_proposed"
    REFINEMENT_APPLIED = "refinement_applied"
    REFINEMENT_REJECTED = "refinement_rejected"
    DIVERSITY_COMPUTED = "diversity_computed"
    DUPLICATE_REJECTED = "duplicate_rejected"
    ALTERNATIVE_ACCEPTED = "alternative_accepted"
    ALTERNATIVE_REJECTED = "alternative_rejected"


@dataclass
class DecisionEvent:
    """An individual atomic decision or evidence record."""
    event_id: str = field(default_factory=lambda: generate_id("evt"))
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    stage: str = StageName.REQUIREMENT.value
    event_type: str = DecisionType.REQUIREMENT_PARSED.value
    source: str = ProvenanceSource.SYSTEM_DERIVED.value
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None  # "room", "door", "window", "staircase", "plot", "alternative"
    floor_number: Optional[int] = None
    input_references: list[str] = field(default_factory=list)
    output_references: list[str] = field(default_factory=list)
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    status: str = "success"  # "success", "warning", "error", "rejected", "accepted"

    def to_dict(self) -> dict[str, Any]:
        """Convert event to primitive dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionEvent:
        """Construct event from dictionary."""
        d = dict(data)
        if isinstance(d.get("stage"), Enum):
            d["stage"] = d["stage"].value
        if isinstance(d.get("event_type"), Enum):
            d["event_type"] = d["event_type"].value
        if isinstance(d.get("source"), Enum):
            d["source"] = d["source"].value
        return cls(**d)


@dataclass
class StageTrace:
    """Chronological trace of events for a single pipeline stage."""
    stage_name: str
    events: list[DecisionEvent] = field(default_factory=list)
    summary: str = ""

    def add_event(self, event: DecisionEvent) -> None:
        self.events.append(event)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_name": self.stage_name,
            "events": [e.to_dict() for e in self.events],
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StageTrace:
        events = [DecisionEvent.from_dict(e) for e in data.get("events", [])]
        return cls(
            stage_name=data.get("stage_name", ""),
            events=events,
            summary=data.get("summary", ""),
        )


@dataclass
class EntityTraceChain:
    """Full lifecycle traceability chain for an individual entity (e.g. Room)."""
    entity_id: str
    entity_type: str = "room"
    room_type: str = ""
    floor_number: int = 1
    events: list[DecisionEvent] = field(default_factory=list)

    @property
    def requirement_event(self) -> Optional[DecisionEvent]:
        for e in self.events:
            if e.stage == StageName.REQUIREMENT.value or e.event_type == DecisionType.REQUIREMENT_PARSED.value:
                return e
        return None

    @property
    def planning_event(self) -> Optional[DecisionEvent]:
        for e in self.events:
            if e.stage == StageName.PLANNING.value or e.event_type in (DecisionType.ROOM_CLASSIFIED.value, DecisionType.PRIORITY_ASSIGNED.value):
                return e
        return None

    @property
    def allocation_event(self) -> Optional[DecisionEvent]:
        for e in self.events:
            if e.stage == StageName.ASAA_ALLOCATION.value or e.event_type == DecisionType.ALLOCATION_ASSIGNED.value:
                return e
        return None

    @property
    def architectural_event(self) -> Optional[DecisionEvent]:
        for e in self.events:
            if e.stage == StageName.ARCHITECTURAL_DESIGN.value or e.event_type in (DecisionType.ROOM_SHAPE_SELECTED.value, DecisionType.ROOM_DIMENSIONS_SELECTED.value):
                return e
        return None

    @property
    def geometry_event(self) -> Optional[DecisionEvent]:
        for e in self.events:
            if e.stage == StageName.GEOMETRY.value or e.event_type == DecisionType.GEOMETRY_CONSTRUCTED.value:
                return e
        return None

    @property
    def validation_events(self) -> list[DecisionEvent]:
        return [e for e in self.events if e.stage == StageName.VALIDATION.value or "validation" in e.event_type]

    @property
    def refinement_events(self) -> list[DecisionEvent]:
        return [e for e in self.events if e.stage == StageName.REFINEMENT.value or "refinement" in e.event_type]

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "room_type": self.room_type,
            "floor_number": self.floor_number,
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EntityTraceChain:
        events = [DecisionEvent.from_dict(e) for e in data.get("events", [])]
        return cls(
            entity_id=data.get("entity_id", ""),
            entity_type=data.get("entity_type", "room"),
            room_type=data.get("room_type", ""),
            floor_number=data.get("floor_number", 1),
            events=events,
        )


@dataclass
class AlternativeTrace:
    """Trace and provenance container for a specific design alternative."""
    alternative_id: str
    index: int
    strategy: str
    status: str
    rejection_reason: Optional[str] = None
    design_signature: Optional[dict[str, Any]] = None
    characteristics: list[str] = field(default_factory=list)
    validation_summary: dict[str, Any] = field(default_factory=dict)
    refinement_summary: dict[str, Any] = field(default_factory=dict)
    diversity_scores: dict[str, float] = field(default_factory=dict)
    events: list[DecisionEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alternative_id": self.alternative_id,
            "index": self.index,
            "strategy": self.strategy,
            "status": self.status,
            "rejection_reason": self.rejection_reason,
            "design_signature": self.design_signature,
            "characteristics": list(self.characteristics),
            "validation_summary": dict(self.validation_summary),
            "refinement_summary": dict(self.refinement_summary),
            "diversity_scores": dict(self.diversity_scores),
            "events": [e.to_dict() for e in self.events],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlternativeTrace:
        events = [DecisionEvent.from_dict(e) for e in data.get("events", [])]
        return cls(
            alternative_id=data.get("alternative_id", ""),
            index=data.get("index", 1),
            strategy=data.get("strategy", ""),
            status=data.get("status", "proposed"),
            rejection_reason=data.get("rejection_reason"),
            design_signature=data.get("design_signature"),
            characteristics=data.get("characteristics", []),
            validation_summary=data.get("validation_summary", {}),
            refinement_summary=data.get("refinement_summary", {}),
            diversity_scores=data.get("diversity_scores", {}),
            events=events,
        )


@dataclass
class DecisionTrace:
    """Top-level immutable Decision Trace recording the complete generation lifecycle."""
    trace_id: str = field(default_factory=lambda: generate_id("trace"))
    project_name: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    stages: list[StageTrace] = field(default_factory=list)
    alternatives: list[AlternativeTrace] = field(default_factory=list)
    entity_chains: dict[str, EntityTraceChain] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_stage(self, stage_name: Union[str, StageName]) -> Optional[StageTrace]:
        """Get the stage trace container by stage name."""
        name = stage_name.value if isinstance(stage_name, Enum) else str(stage_name).lower()
        for s in self.stages:
            if s.stage_name.lower() == name:
                return s
        return None

    def get_events_by_stage(self, stage_name: Union[str, StageName]) -> list[DecisionEvent]:
        """Return all events recorded under a specific stage."""
        stage = self.get_stage(stage_name)
        return list(stage.events) if stage else []

    def get_events_by_entity(self, entity_id: str) -> list[DecisionEvent]:
        """Return all events mentioning or referencing an entity."""
        matches: list[DecisionEvent] = []
        for s in self.stages:
            for e in s.events:
                if (
                    e.entity_id == entity_id
                    or entity_id in e.input_references
                    or entity_id in e.output_references
                ):
                    matches.append(e)
        return matches

    def get_events_by_type(self, event_type: Union[str, DecisionType]) -> list[DecisionEvent]:
        """Filter all events across all stages by decision type."""
        t = event_type.value if isinstance(event_type, Enum) else str(event_type)
        matches: list[DecisionEvent] = []
        for s in self.stages:
            for e in s.events:
                if e.event_type == t:
                    matches.append(e)
        return matches

    def get_entity_chain(self, entity_id: str) -> Optional[EntityTraceChain]:
        """Retrieve the unbroken traceability chain for an entity."""
        return self.entity_chains.get(entity_id)

    def to_dict(self) -> dict[str, Any]:
        """Convert the entire trace into a serializable dictionary."""
        return {
            "trace_id": self.trace_id,
            "project_name": self.project_name,
            "created_at": self.created_at,
            "stages": [s.to_dict() for s in self.stages],
            "alternatives": [a.to_dict() for a in self.alternatives],
            "entity_chains": {k: v.to_dict() for k, v in self.entity_chains.items()},
            "metadata": dict(self.metadata),
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize the trace to a formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    # Pydantic-style convention aliases
    def model_dump(self) -> dict[str, Any]:
        """Pydantic v2 convention alias for to_dict()."""
        return self.to_dict()

    def model_dump_json(self, indent: int = 2) -> str:
        """Pydantic v2 convention alias for to_json()."""
        return self.to_json(indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionTrace:
        """Deserialize DecisionTrace from a dictionary."""
        stages = [StageTrace.from_dict(s) for s in data.get("stages", [])]
        alternatives = [AlternativeTrace.from_dict(a) for a in data.get("alternatives", [])]
        entity_chains = {
            k: EntityTraceChain.from_dict(v)
            for k, v in data.get("entity_chains", {}).items()
        }
        return cls(
            trace_id=data.get("trace_id", generate_id("trace")),
            project_name=data.get("project_name", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
            stages=stages,
            alternatives=alternatives,
            entity_chains=entity_chains,
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> DecisionTrace:
        """Deserialize DecisionTrace from a JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

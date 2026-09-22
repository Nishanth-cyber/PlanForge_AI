"""Event factories for creating standardized DecisionEvent records.

This module provides factory functions to produce well-typed DecisionEvent instances
across all 9 pipeline stages.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.explainability.models import (
    DecisionEvent,
    DecisionType,
    ProvenanceSource,
    StageName,
)
from app.utils.ids import generate_id


def create_requirement_event(
    entity_id: str,
    entity_type: str,
    reason: str,
    evidence: dict[str, Any],
    constraints: Optional[dict[str, Any]] = None,
    floor_number: Optional[int] = None,
    input_references: Optional[list[str]] = None,
    output_references: Optional[list[str]] = None,
    status: str = "success",
) -> DecisionEvent:
    """Create a trace event for parsed requirements."""
    return DecisionEvent(
        event_id=generate_id("evt_req"),
        stage=StageName.REQUIREMENT.value,
        event_type=DecisionType.REQUIREMENT_PARSED.value,
        source=ProvenanceSource.USER.value,
        entity_id=entity_id,
        entity_type=entity_type,
        floor_number=floor_number,
        input_references=input_references or ["user_brief"],
        output_references=output_references or [entity_id],
        reason=reason,
        evidence=evidence,
        constraints=constraints or {},
        status=status,
    )


def create_planning_event(
    event_type: DecisionType,
    source: ProvenanceSource,
    entity_id: str,
    reason: str,
    evidence: dict[str, Any],
    entity_type: str = "room",
    floor_number: Optional[int] = None,
    input_references: Optional[list[str]] = None,
    output_references: Optional[list[str]] = None,
    status: str = "success",
) -> DecisionEvent:
    """Create a trace event for strategic planning decisions."""
    return DecisionEvent(
        event_id=generate_id("evt_plan"),
        stage=StageName.PLANNING.value,
        event_type=event_type.value,
        source=source.value,
        entity_id=entity_id,
        entity_type=entity_type,
        floor_number=floor_number,
        input_references=input_references or [],
        output_references=output_references or [entity_id],
        reason=reason,
        evidence=evidence,
        constraints={},
        status=status,
    )


def create_asaa_event(
    event_type: DecisionType,
    entity_id: str,
    reason: str,
    evidence: dict[str, Any],
    entity_type: str = "region",
    floor_number: Optional[int] = None,
    input_references: Optional[list[str]] = None,
    output_references: Optional[list[str]] = None,
    status: str = "success",
) -> DecisionEvent:
    """Create a trace event for ASAA spatial allocation decisions."""
    return DecisionEvent(
        event_id=generate_id("evt_asaa"),
        stage=StageName.ASAA_ALLOCATION.value,
        event_type=event_type.value,
        source=ProvenanceSource.ASAA.value,
        entity_id=entity_id,
        entity_type=entity_type,
        floor_number=floor_number,
        input_references=input_references or [],
        output_references=output_references or [entity_id],
        reason=reason,
        evidence=evidence,
        constraints={},
        status=status,
    )


def create_architectural_event(
    event_type: DecisionType,
    entity_id: str,
    reason: str,
    evidence: dict[str, Any],
    entity_type: str = "room",
    floor_number: Optional[int] = None,
    input_references: Optional[list[str]] = None,
    output_references: Optional[list[str]] = None,
    status: str = "success",
) -> DecisionEvent:
    """Create a trace event for Architectural LLM intent proposals."""
    return DecisionEvent(
        event_id=generate_id("evt_arch"),
        stage=StageName.ARCHITECTURAL_DESIGN.value,
        event_type=event_type.value,
        source=ProvenanceSource.ARCHITECTURAL_LLM.value,
        entity_id=entity_id,
        entity_type=entity_type,
        floor_number=floor_number,
        input_references=input_references or [],
        output_references=output_references or [entity_id],
        reason=reason if reason.strip() else "Rationale not provided.",
        evidence=evidence,
        constraints={},
        status=status,
    )


def create_geometry_event(
    entity_id: str,
    reason: str,
    evidence: dict[str, Any],
    entity_type: str = "room",
    floor_number: Optional[int] = None,
    input_references: Optional[list[str]] = None,
    output_references: Optional[list[str]] = None,
    status: str = "success",
) -> DecisionEvent:
    """Create a trace event for deterministic geometry construction facts."""
    return DecisionEvent(
        event_id=generate_id("evt_geom"),
        stage=StageName.GEOMETRY.value,
        event_type=DecisionType.GEOMETRY_CONSTRUCTED.value,
        source=ProvenanceSource.GEOMETRY_ENGINE.value,
        entity_id=entity_id,
        entity_type=entity_type,
        floor_number=floor_number,
        input_references=input_references or [],
        output_references=output_references or [entity_id],
        reason=reason,
        evidence=evidence,
        constraints={},
        status=status,
    )


def create_validation_event(
    event_type: DecisionType,
    entity_id: Optional[str],
    check: str,
    reason: str,
    evidence: dict[str, Any],
    severity: str = "error",
    floor_number: Optional[int] = None,
    input_references: Optional[list[str]] = None,
    output_references: Optional[list[str]] = None,
) -> DecisionEvent:
    """Create a trace event for an independent validation check or issue."""
    status_map = {
        "error": "error",
        "warning": "warning",
        "info": "success",
        "passed": "success",
    }
    return DecisionEvent(
        event_id=generate_id("evt_val"),
        stage=StageName.VALIDATION.value,
        event_type=event_type.value,
        source=ProvenanceSource.VALIDATOR.value,
        entity_id=entity_id,
        entity_type="validation_issue" if event_type != DecisionType.VALIDATION_CHECKED else "check",
        floor_number=floor_number,
        input_references=input_references or [],
        output_references=output_references or [],
        reason=reason,
        evidence=evidence,
        constraints={"check": check, "severity": severity},
        status=status_map.get(severity.lower(), "warning"),
    )


def create_refinement_event(
    event_type: DecisionType,
    entity_id: str,
    reason: str,
    evidence: dict[str, Any],
    validation_issue_ids: Optional[list[str]] = None,
    floor_number: Optional[int] = None,
    status: str = "success",
) -> DecisionEvent:
    """Create a trace event for a refinement correction."""
    return DecisionEvent(
        event_id=generate_id("evt_ref"),
        stage=StageName.REFINEMENT.value,
        event_type=event_type.value,
        source=ProvenanceSource.REFINEMENT_LLM.value,
        entity_id=entity_id,
        entity_type="room",
        floor_number=floor_number,
        input_references=validation_issue_ids or [],
        output_references=[entity_id],
        reason=reason if reason.strip() else "Rationale not provided.",
        evidence=evidence,
        constraints={},
        status=status,
    )


def create_diversity_event(
    event_type: DecisionType,
    entity_id: str,
    reason: str,
    evidence: dict[str, Any],
    status: str = "success",
) -> DecisionEvent:
    """Create a trace event for diversity evaluation and duplicate filtering."""
    return DecisionEvent(
        event_id=generate_id("evt_div"),
        stage=StageName.DIVERSITY.value,
        event_type=event_type.value,
        source=ProvenanceSource.DIVERSITY_ENGINE.value,
        entity_id=entity_id,
        entity_type="alternative",
        input_references=[entity_id],
        output_references=[entity_id],
        reason=reason,
        evidence=evidence,
        constraints={},
        status=status,
    )


def create_alternative_event(
    event_type: DecisionType,
    alternative_id: str,
    reason: str,
    evidence: dict[str, Any],
    status: str = "accepted",
) -> DecisionEvent:
    """Create a trace event for final alternative acceptance or rejection."""
    return DecisionEvent(
        event_id=generate_id("evt_alt"),
        stage=StageName.FINAL_SELECTION.value,
        event_type=event_type.value,
        source=ProvenanceSource.DIVERSITY_ENGINE.value,
        entity_id=alternative_id,
        entity_type="alternative",
        input_references=[alternative_id],
        output_references=[alternative_id],
        reason=reason,
        evidence=evidence,
        constraints={},
        status=status,
    )

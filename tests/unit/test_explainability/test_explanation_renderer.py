"""Unit tests for deterministic human-readable explanation rendering."""

import pytest

from app.explainability.builder import DecisionTraceBuilder
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
from app.explainability.renderer import ExplanationRenderer


def test_human_readable_project_explanation():
    """Verify Project Summary explanation rendering."""
    trace = DecisionTrace(project_name="Maple Court Residence")
    trace.stages.append(
        StageTrace(
            stage_name=StageName.REQUIREMENT.value,
            events=[
                DecisionEvent(
                    stage=StageName.REQUIREMENT.value,
                    entity_type="plot",
                    evidence={"plot_dimensions": (12.0, 16.0), "setbacks": {"front": 2.0, "rear": 2.0}},
                ),
                DecisionEvent(stage=StageName.REQUIREMENT.value, entity_type="room"),
                DecisionEvent(stage=StageName.REQUIREMENT.value, entity_type="room"),
            ],
        )
    )
    trace.stages.append(
        StageTrace(
            stage_name=StageName.PLANNING.value,
            events=[
                DecisionEvent(
                    stage=StageName.PLANNING.value,
                    event_type=DecisionType.ROOM_CLASSIFIED.value,
                    evidence={"category": "social"},
                ),
                DecisionEvent(
                    stage=StageName.PLANNING.value,
                    event_type=DecisionType.PRIORITY_ASSIGNED.value,
                    evidence={"room_type": "living", "priority": "high"},
                ),
            ],
        )
    )
    trace.alternatives.append(
        AlternativeTrace(
            alternative_id="alt_1",
            index=1,
            strategy="social_centric",
            status="validated",
            characteristics=["Direct kitchen-dining flow", "Spacious living area"],
        )
    )

    summary = ExplanationRenderer.render_project_summary(trace)
    assert "Maple Court Residence" in summary
    assert "12.00m × 16.00m" in summary
    assert "2 room requirement(s)" in summary
    assert "High Priority Spaces: living" in summary
    assert "Alternative 1 (social_centric)" in summary


def test_human_readable_room_explanation():
    """Verify complete room lifecycle narrative from requirement to validation."""
    chain = EntityTraceChain(
        entity_id="room_101",
        room_type="master_bedroom",
        floor_number=1,
        events=[
            DecisionEvent(
                stage=StageName.REQUIREMENT.value,
                entity_type="room",
                evidence={"room_type": "master_bedroom", "target_area_sqm": 18.5, "required_adjacency": ["bathroom"]},
            ),
            DecisionEvent(
                stage=StageName.PLANNING.value,
                entity_type="room",
                reason="High priority private space for homeowner rest",
                evidence={"category": "private", "priority": "high"},
            ),
            DecisionEvent(
                stage=StageName.ASAA_ALLOCATION.value,
                entity_type="region",
                reason="Allocated 19.20 m² region for 'master_bedroom'. Prioritized due to high functional importance.",
                evidence={"allocated_area_sqm": 19.20, "allocated_region_id": "reg_05", "priority": "high", "zone_type": "room"},
            ),
            DecisionEvent(
                stage=StageName.ARCHITECTURAL_DESIGN.value,
                entity_type="room",
                reason="Oriented north to capture natural daylight.",
                evidence={"intended_shape": "rectangular", "intended_dimensions": [4.0, 4.8]},
            ),
            DecisionEvent(
                stage=StageName.GEOMETRY.value,
                entity_type="room",
                evidence={"usable_area_sqm": 18.8, "walls_count": 4},
            ),
            DecisionEvent(
                stage=StageName.VALIDATION.value,
                entity_type="room",
                status="success",
                reason="Area and boundary checks passed",
            ),
        ],
    )
    trace = DecisionTrace(entity_chains={"room_101": chain})

    explanation = ExplanationRenderer.render_room_explanation(trace, "room_101")
    assert "Room Lifecycle Narrative: master_bedroom" in explanation
    assert "target area 18.50 m²" in explanation
    assert "Classified as 'private' space with 'high' priority" in explanation
    assert "Assigned to Region reg_05 with 19.20 m²" in explanation
    assert "Designed as a rectangular room" in explanation
    assert "Oriented north to capture natural daylight." in explanation
    assert "Constructed 4-wall boundary polygon with 18.80 m²" in explanation
    assert "**Validation**: Room passed all geometric, area, and boundary checks." in explanation


def test_no_fabrication_in_room_explanation():
    """Verify that when factors (like orientation or LLM rationale) are missing, they are NOT fabricated."""
    chain = EntityTraceChain(
        entity_id="room_kitchen",
        room_type="kitchen",
        floor_number=1,
        events=[
            DecisionEvent(
                stage=StageName.ASAA_ALLOCATION.value,
                entity_type="region",
                evidence={"allocated_area_sqm": 12.0, "allocated_region_id": "reg_02", "priority": "normal"},
            ),
            DecisionEvent(
                stage=StageName.ARCHITECTURAL_DESIGN.value,
                entity_type="room",
                reason="Rationale not provided.",
                evidence={"intended_shape": "rectangular", "intended_dimensions": [3.0, 4.0]},
            ),
        ],
    )
    trace = DecisionTrace(entity_chains={"room_kitchen": chain})

    explanation = ExplanationRenderer.render_room_explanation(trace, "room_kitchen")
    # Must NOT fabricate sunlight or orientation if not computed
    assert "sunlight" not in explanation.lower()
    assert "orientation score" not in explanation.lower()
    assert "morning sun" not in explanation.lower()
    assert "Rationale not provided." in explanation


def test_human_readable_validation_explanation():
    """Verify evidence-based validation explanation rendering."""
    trace = DecisionTrace()
    trace.stages.append(
        StageTrace(
            stage_name=StageName.VALIDATION.value,
            events=[
                DecisionEvent(
                    stage=StageName.VALIDATION.value,
                    status="error",
                    constraints={"check": "boundary_containment"},
                    reason="Room 'living' extends outside the buildable envelope by 2.5 sqm",
                    evidence={"details": {"expected": "contained", "observed": "protrudes 2.5m"}},
                ),
                DecisionEvent(
                    stage=StageName.VALIDATION.value,
                    status="warning",
                    constraints={"check": "window_orientation"},
                    reason="Window faces west instead of preferred north",
                    evidence={},
                ),
                DecisionEvent(
                    stage=StageName.VALIDATION.value,
                    status="success",
                    evidence={"check": "overlap"},
                ),
            ],
        )
    )

    val_text = ExplanationRenderer.render_validation_explanation(trace)
    assert "Independent Validation Report" in val_text
    assert "Status: FAILED" in val_text
    assert "Errors: 1" in val_text
    assert "Warnings: 1" in val_text
    assert "boundary_containment" in val_text
    assert "Expected: contained | Observed: protrudes 2.5m" in val_text
    assert "Passed Check Categories:" in val_text
    assert "overlap" in val_text


def test_human_readable_refinement_explanation():
    """Verify closed-loop refinement explanation linking changes to validation issues."""
    trace = DecisionTrace()
    trace.stages.append(
        StageTrace(
            stage_name=StageName.REFINEMENT.value,
            events=[
                DecisionEvent(
                    stage=StageName.REFINEMENT.value,
                    entity_id="room_living",
                    reason="Re-positioned entrance door to resolve setback boundary collision",
                    evidence={
                        "field_changed": "doors",
                        "old_value": [{"wall": "south"}],
                        "new_value": [{"wall": "east"}],
                        "validation_issue_ids": ["val_issue_door_01"],
                    },
                )
            ],
        )
    )

    ref_text = ExplanationRenderer.render_refinement_explanation(trace)
    assert "Refinement & Iterative Correction Narrative" in ref_text
    assert "Room 'room_living' doors" in ref_text
    assert "Prompted by issue(s): val_issue_door_01" in ref_text
    assert "Decision Rationale: Re-positioned entrance door" in ref_text


def test_human_readable_alternative_explanation():
    """Verify alternative summary explanation."""
    trace = DecisionTrace()
    trace.alternatives.append(
        AlternativeTrace(
            alternative_id="alt_001",
            index=1,
            strategy="corridor_centric",
            status="validated",
            characteristics=["Central circulation spine", "Acoustic private buffer"],
            validation_summary={"is_valid": True, "score": 96.5, "error_count": 0},
            refinement_summary={"refinement_status": "converged", "iterations": 1},
            diversity_scores={"alt_002": 0.42},
        )
    )

    alt_text = ExplanationRenderer.render_alternative_summary(trace, "alt_001")
    assert "Alternative 1: Strategy 'corridor_centric'" in alt_text
    assert "Central circulation spine" in alt_text
    assert "Validation: VALID (Score: 96.5, Errors: 0)" in alt_text
    assert "Distance to alt_002: 0.420" in alt_text


def test_human_readable_diversity_explanation():
    """Verify objective pairwise structural comparison between two alternatives."""
    alt_a = AlternativeTrace(
        alternative_id="alt_A",
        index=1,
        strategy="social_centric",
        status="validated",
        design_signature={
            "circulation_type": "open_plan",
            "entrance_room_type": "living",
            "social_sequence": ["living", "dining", "kitchen"],
            "private_clustering": "dispersed",
            "staircase_relationship": "living",
        },
        diversity_scores={"alt_B": 0.44},
    )
    alt_b = AlternativeTrace(
        alternative_id="alt_B",
        index=2,
        strategy="corridor_centric",
        status="validated",
        design_signature={
            "circulation_type": "central_spine",
            "entrance_room_type": "foyer",
            "social_sequence": ["foyer", "living", "dining"],
            "private_clustering": "clustered",
            "staircase_relationship": "corridor",
        },
        diversity_scores={"alt_A": 0.44},
    )
    trace = DecisionTrace(alternatives=[alt_a, alt_b])

    comp_text = ExplanationRenderer.render_diversity_explanation(trace, "alt_A", "alt_B")
    assert "Structural Diversity Comparison: Alternative 1 vs Alternative 2" in comp_text
    assert "Pairwise Diversity Distance: 0.440" in comp_text
    assert "**Circulation Topology** [DIFFERENT]" in comp_text
    assert "Alt 1: open_plan" in comp_text
    assert "Alt 2: central_spine" in comp_text
    assert "**Entrance Room** [DIFFERENT]" in comp_text
    assert "Alt 1: living" in comp_text
    assert "Alt 2: foyer" in comp_text
    assert "**Social Flow Sequence** [DIFFERENT]" in comp_text
    assert "**Private Zone Clustering** [DIFFERENT]" in comp_text


def test_rejection_explanation():
    """Verify explanation rendering for a rejected candidate."""
    trace = DecisionTrace()
    trace.stages.append(
        StageTrace(
            stage_name=StageName.FINAL_SELECTION.value,
            events=[
                DecisionEvent(
                    stage=StageName.FINAL_SELECTION.value,
                    event_type=DecisionType.ALTERNATIVE_REJECTED.value,
                    entity_id="cand_rej_1",
                    reason="Candidate rejected: duplicate (closest distance=0.0)",
                    evidence={"rejection_reason": "duplicate", "strategy": "privacy_centric"},
                )
            ],
        )
    )

    rej_text = ExplanationRenderer.render_alternative_summary(trace, "cand_rej_1")
    assert "Alternative cand_rej_1 was REJECTED." in rej_text
    assert "duplicate" in rej_text


def test_deterministic_explanation_rendering():
    """Verify that calling explanation renderer multiple times on the same trace produces identical outputs."""
    chain = EntityTraceChain(
        entity_id="room_1",
        room_type="living",
        events=[
            DecisionEvent(stage=StageName.REQUIREMENT.value, entity_type="room", evidence={"target_area_sqm": 25.0}),
            DecisionEvent(stage=StageName.PLANNING.value, entity_type="room", evidence={"category": "social", "priority": "high"}),
        ],
    )
    trace = DecisionTrace(project_name="Deterministic Test", entity_chains={"room_1": chain})

    res1 = ExplanationRenderer.render_room_explanation(trace, "room_1")
    res2 = ExplanationRenderer.render_room_explanation(trace, "room_1")
    assert res1 == res2

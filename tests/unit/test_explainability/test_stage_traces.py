"""Unit tests for stage-specific event extraction, provenance attribution, and model immutability."""

import copy
import pytest

from app.explainability.builder import DecisionTraceBuilder
from app.explainability.models import (
    DecisionType,
    ProvenanceSource,
    StageName,
)
from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
from app.models.alternatives import (
    AlternativeStatus,
    DesignAlternative,
    DesignAlternativeSet,
    DesignSignature,
    DesignStrategy,
)
from app.models.architectural_design import (
    ArchitecturalDesign,
    ArchitecturalDesignSet,
    RoomDesign,
)
from app.models.doors import DoorIntent
from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.models.geometry import GeoDoor, GeoRoom, GeoWall, GeoWindow, Geometry, GeometrySet
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec
from app.models.refinement import RefinementChange, RefinementIterationRecord, RefinementResult, RefinementStatus
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement
from app.models.validation import ValidationIssue, ValidationReport, ValidationResult
from app.models.windows import WindowIntent


def test_requirement_trace_extraction():
    """Verify extraction of requirement events with USER provenance."""
    reqs = Requirements(
        project_name="Requirement Trace Test",
        plot_dimensions=(12.0, 15.0),
        setbacks={"front": 2.0, "rear": 2.0, "side": 1.5},
        floor_requirements=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(id="rr_living", room_type="living", min_count=1, target_area_sqm=25.0, min_area_sqm=20.0),
                    RoomRequirement(id="rr_dining", room_type="dining", min_count=1, target_area_sqm=15.0),
                ],
            )
        ],
    )

    trace = DecisionTraceBuilder.build(requirements=reqs)
    req_stage = trace.get_stage(StageName.REQUIREMENT)
    assert req_stage is not None
    assert len(req_stage.events) == 3  # plot + 2 rooms

    for evt in req_stage.events:
        assert evt.source == ProvenanceSource.USER.value
        assert evt.stage == StageName.REQUIREMENT.value

    living_evt = next(e for e in req_stage.events if e.entity_id == "rr_living")
    assert living_evt.evidence["room_type"] == "living"
    assert living_evt.evidence["target_area_sqm"] == 25.0
    assert living_evt.constraints["min_area_sqm"] == 20.0


def test_planning_trace_user_vs_system_distinction():
    """Verify explicit distinction between USER-SPECIFIED and SYSTEM-DERIVED planning decisions."""
    # User specified living -> dining in requirements
    reqs = Requirements(
        floor_requirements=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(id="rr_1", room_type="living", adjacency=["dining"]),
                    RoomRequirement(id="rr_2", room_type="dining"),
                ],
            )
        ]
    )
    # Planning spec contains user-specified living -> dining, AND system-derived dining -> kitchen
    rs1 = RoomSpec(
        id="rs_1",
        room_type="living",
        room_category="social",
        priority="high",
        priority_rationale="Primary entertainment hub",
        adjacency=["dining"],
        source_requirement_id="rr_1",
    )
    rs2 = RoomSpec(
        id="rs_2",
        room_type="dining",
        room_category="social",
        priority="normal",
        adjacency=["kitchen"],  # System derived preference
        avoid=["bathroom"],     # System derived avoidance
        source_requirement_id="rr_2",
    )
    plan_spec = PlanningSpec(
        floors=[FloorPlanSpec(floor_number=1, room_specs=[rs1, rs2])]
    )

    trace = DecisionTraceBuilder.build(requirements=reqs, planning_spec=plan_spec)
    plan_events = trace.get_events_by_stage(StageName.PLANNING)

    # 1. Categorization and priority events are attributed to PLANNING_AGENT
    classified_evts = [e for e in plan_events if e.event_type == DecisionType.ROOM_CLASSIFIED.value]
    assert len(classified_evts) == 2
    for ce in classified_evts:
        assert ce.source == ProvenanceSource.PLANNING_AGENT.value

    # 2. Relationship events: Living -> Dining must be USER provenance
    rel_evts = [e for e in plan_events if e.event_type == DecisionType.RELATIONSHIP_CREATED.value]
    user_rel = next(e for e in rel_evts if e.evidence.get("from_room") == "living" and e.evidence.get("to_room") == "dining")
    assert user_rel.source == ProvenanceSource.USER.value
    assert user_rel.evidence["is_user_specified"] is True

    # 3. Relationship events: Dining -> Kitchen must be SYSTEM_DERIVED provenance
    sys_rel = next(e for e in rel_evts if e.evidence.get("from_room") == "dining" and e.evidence.get("to_room") == "kitchen")
    assert sys_rel.source == ProvenanceSource.SYSTEM_DERIVED.value
    assert sys_rel.evidence["is_user_specified"] is False


def test_asaa_allocation_trace_and_no_fabrication():
    """Verify ASAA allocation facts are preserved and uncalculated factors (e.g. orientation) are NOT fabricated."""
    reg = AllocatedRegion(
        id="reg_101",
        room_type="living",
        room_spec_id="rs_living",
        target_area_sqm=25.0,
        area_sqm=26.4,
        approximate_dimensions=(4.8, 5.5),
        priority="high",
        zone_type="room",
        score=92.5,
    )
    alloc = Allocation(floor_number=1, allocated_regions=[reg])
    alloc_set = AllocationSet(allocations=[alloc])

    trace = DecisionTraceBuilder.build(allocation_set=alloc_set)
    asaa_events = trace.get_events_by_stage(StageName.ASAA_ALLOCATION)
    assert len(asaa_events) == 1

    evt = asaa_events[0]
    assert evt.source == ProvenanceSource.ASAA.value
    assert evt.entity_id == "rs_living"
    assert evt.output_references == ["reg_101"]
    assert evt.evidence["allocated_area_sqm"] == 26.4
    assert evt.evidence["score"] == 92.5

    # Critical: No fabrication of orientation or sunlight if not present
    assert "orientation_score" not in evt.evidence
    assert "sunlight" not in evt.reason.lower()


def test_architectural_design_trace_and_rationale_fallback():
    """Verify architectural intent proposals, doors, windows, and rationale fallback when empty."""
    d_intent = DoorIntent(
        id="door_1",
        connects_from="living",
        connects_to="dining",
        door_type="interior",
        recommended_width=0.9,
        rationale="Direct social connection between living and dining",
    )
    w_intent = WindowIntent(
        id="win_1",
        wall_orientation="north",
        window_type="standard",
        rationale="Daylight aperture",
    )
    room1 = RoomDesign(
        id="room_design_1",
        room_type="living",
        allocated_region_id="reg_101",
        intended_shape="rectangular",
        intended_dimensions=(4.8, 5.5),
        intended_area_sqm=26.4,
        doors=[d_intent],
        windows=[w_intent],
        design_rationale="",  # Empty rationale to test fallback
    )
    arch_set = ArchitecturalDesignSet(
        designs=[ArchitecturalDesign(floor_number=1, rooms=[room1])]
    )

    trace = DecisionTraceBuilder.build(architectural_design_set=arch_set)
    arch_events = trace.get_events_by_stage(StageName.ARCHITECTURAL_DESIGN)
    assert len(arch_events) == 3  # room + door + window

    room_evt = next(e for e in arch_events if e.event_type == DecisionType.ROOM_SHAPE_SELECTED.value)
    assert room_evt.source == ProvenanceSource.ARCHITECTURAL_LLM.value
    assert "Rationale not provided." in room_evt.reason


def test_geometry_trace():
    """Verify deterministic geometry construction fact tracing."""
    geo_room = GeoRoom(
        id="georoom_1",
        room_type="living",
        architectural_room_id="room_design_1",
        area_sqm=25.8,
        walls=["w1", "w2", "w3", "w4"],
        doors=["d1"],
        windows=["win1"],
    )
    geom = Geometry(floor_number=1, rooms=[geo_room])
    fp = FloorPlan(floor_number=1, geometry=geom)
    fp_set = FloorPlanSet(floor_plans=[fp])

    trace = DecisionTraceBuilder.build(geometry_set=fp_set)
    geom_events = trace.get_events_by_stage(StageName.GEOMETRY)
    assert len(geom_events) == 1

    evt = geom_events[0]
    assert evt.source == ProvenanceSource.GEOMETRY_ENGINE.value
    assert evt.entity_id == "room_design_1"
    assert evt.output_references == ["georoom_1"]
    assert evt.evidence["usable_area_sqm"] == 25.8


def test_validation_trace():
    """Verify validation check events and issue reporting with expected vs observed."""
    iss = ValidationIssue(
        id="val_issue_1",
        severity="error",
        category="dimension",
        check="minimum_room_area",
        message="Room 'bedroom' area 9.50 sqm is below required minimum 11.15 sqm",
        details={"expected": 11.15, "observed": 9.50},
        target_id="room_bed_1",
        floor_number=1,
    )
    res = ValidationResult(floor_number=1, is_valid=False, issues=[iss], checks_failed=["dimension"], checks_passed=["boundary", "overlap"])
    report = ValidationReport(results=[res])

    trace = DecisionTraceBuilder.build(validation_report=report)
    val_events = trace.get_events_by_stage(StageName.VALIDATION)
    assert len(val_events) == 3  # 2 passed checks + 1 failure issue

    fail_evt = next(e for e in val_events if e.event_type == DecisionType.VALIDATION_FAILURE.value)
    assert fail_evt.source == ProvenanceSource.VALIDATOR.value
    assert fail_evt.status == "error"
    assert fail_evt.evidence["details"]["expected"] == 11.15
    assert fail_evt.evidence["details"]["observed"] == 9.50


def test_refinement_trace_and_issue_linkage():
    """Verify refinement change tracing with explicit linkage to validation issues."""
    chg = RefinementChange(
        id="chg_01",
        floor_number=1,
        room_id="room_bed_1",
        field_changed="intended_dimensions",
        old_value=[2.8, 3.4],
        new_value=[3.3, 3.4],
        reason="Expanded room dimensions to satisfy minimum area constraint",
        validation_issue_ids=["val_issue_1"],
    )
    ref_res = RefinementResult(
        status=RefinementStatus.CONVERGED,
        iterations=[RefinementIterationRecord(iteration=1), RefinementIterationRecord(iteration=2)],
        changes=[chg],
    )

    trace = DecisionTraceBuilder.build(refinement_result=ref_res)
    ref_events = trace.get_events_by_stage(StageName.REFINEMENT)
    assert len(ref_events) == 1

    evt = ref_events[0]
    assert evt.source == ProvenanceSource.REFINEMENT_LLM.value
    assert evt.entity_id == "room_bed_1"
    assert evt.input_references == ["val_issue_1"]
    assert evt.evidence["field_changed"] == "intended_dimensions"


def test_diversity_trace_objective_comparison():
    """Verify objective diversity reporting without subjective quality claims."""
    sig1 = DesignSignature(
        adjacency_edges=(("dining", "living"), ("corridor", "kitchen")),
        circulation_type="central_spine",
        entrance_room_type="living",
        social_sequence=("living", "dining"),
        private_clustering="clustered",
        staircase_relationship="none",
        room_shapes=(("living", "rectangular"),),
        proportion_buckets=(("living", "standard"),),
    )
    alt1 = DesignAlternative(
        alternative_id="alt_1",
        index=1,
        strategy="social_centric",
        design_signature=sig1,
        characteristics=["direct social flow"],
        status=AlternativeStatus.VALIDATED,
        diversity_scores={"alt_2": 0.38},
    )
    alt2 = DesignAlternative(
        alternative_id="alt_2",
        index=2,
        strategy="corridor_centric",
        characteristics=["central circulation"],
        status=AlternativeStatus.VALIDATED,
        diversity_scores={"alt_1": 0.38},
    )
    alt_set = DesignAlternativeSet(
        alternatives=[alt1, alt2],
        rejected_candidates=[],
    )

    trace = DecisionTraceBuilder.build(alternative_set=alt_set)
    div_events = trace.get_events_by_stage(StageName.DIVERSITY)
    assert len(div_events) == 2

    evt1 = next(e for e in div_events if e.entity_id == "alt_1")
    assert evt1.evidence["strategy"] == "social_centric"
    assert evt1.evidence["diversity_scores"]["alt_2"] == 0.38
    # No subjective claims
    assert "better" not in evt1.reason.lower()
    assert "beautiful" not in evt1.reason.lower()


def test_final_alternative_trace_and_rejection():
    """Verify accepted alternatives and rejected candidates are logged with reasons."""
    rej = DesignAlternative(
        alternative_id="cand_rej",
        index=3,
        strategy="compact_circulation",
        status=AlternativeStatus.DUPLICATE,
        rejection_reason="duplicate",
        design_rationale="Candidate rejected: duplicate (closest distance=0.0)",
    )
    alt_set = DesignAlternativeSet(
        alternatives=[],
        rejected_candidates=[rej],
    )

    trace = DecisionTraceBuilder.build(alternative_set=alt_set)
    div_events = trace.get_events_by_stage(StageName.DIVERSITY)
    rej_evt = div_events[0]
    assert rej_evt.status == "rejected"
    assert rej_evt.event_type == DecisionType.ALTERNATIVE_REJECTED.value
    assert rej_evt.evidence["rejection_reason"] == "duplicate"


def test_no_mutation_of_source_models():
    """Verify that DecisionTraceBuilder is strictly READ-ONLY and does not mutate source objects."""
    reqs = Requirements(project_name="Immutable Test")
    reqs_copy = copy.deepcopy(reqs)

    trace = DecisionTraceBuilder.build(requirements=reqs)
    assert reqs == reqs_copy


def test_requirement_trace_floor_count_regression():
    """Verify regression fix: requirements parsed via agent correctly report floor count in summary."""
    from app.agents.requirement_agent.parser import RequirementParser

    parser = RequirementParser()

    # 1. Single floor brief
    r1 = parser.parse("Plot: 20x30m. Ground floor: living room 20 sqm, kitchen 10 sqm.")
    trace1 = DecisionTraceBuilder.build(requirements=r1)
    req_stage1 = trace1.get_stage(StageName.REQUIREMENT)
    assert req_stage1 is not None
    assert "1 floor(s)" in req_stage1.summary
    assert "0 floor(s)" not in req_stage1.summary

    # 2. Multi-floor brief
    r2 = parser.parse("Plot: 20x30m. Target floors: 2. Floor 1: living 20 sqm. Floor 2: bedroom 15 sqm.")
    trace2 = DecisionTraceBuilder.build(requirements=r2)
    req_stage2 = trace2.get_stage(StageName.REQUIREMENT)
    assert req_stage2 is not None
    assert "2 floor(s)" in req_stage2.summary
    assert "0 floor(s)" not in req_stage2.summary

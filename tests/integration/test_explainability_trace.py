"""Integration tests for Phase 10 Explainability & Decision Trace.

Verifies end-to-end decision tracing, entity traceability chains, multi-floor distinction,
closed-loop refinement traceability, and multi-design diversity explanations.
"""

import copy
from app.agents.architectural_agent import ArchitecturalAgent
from app.agents.diversity_agent import MultiDesignGenerator
from app.agents.planning_agent import PlanningAgent
from app.agents.refinement_agent import RefinementLoop, RefinementStatus
from app.agents.requirement_agent import RequirementAgent
from app.asaa.allocator import ASAAAllocator
from app.explainability.builder import DecisionTraceBuilder
from app.explainability.models import DecisionType, ProvenanceSource, StageName
from app.explainability.renderer import ExplanationRenderer
from app.geometry.engine import GeometryEngine
from app.validation.validator import FloorPlanValidator


def test_end_to_end_entity_traceability():
    """Verify unbroken entity linkage:

    Requirement room_id == Planning room_id == Allocation room_id == Architectural room_id == GeoRoom.architectural_room_id
    and ValidationIssue references GeoRoom.
    """
    brief = """
    Single floor family home on a 40 feet by 50 feet rectangular plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 spacious living room of 300 sq ft
    - 1 dining room of 150 sq ft
    - 1 kitchen of 120 sq ft
    """
    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief, project_name="Traceability Test")

    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)

    asaa = ASAAAllocator(seed=42)
    allocation_set = asaa.allocate(planning_spec)

    arch_agent = ArchitecturalAgent()
    arch_set = arch_agent.design(planning_spec=planning_spec, allocation_set=allocation_set, strategy="social_centric")

    geom_engine = GeometryEngine()
    floor_plans = geom_engine.construct(arch_set, allocation_set)

    validator = FloorPlanValidator()
    val_rep = validator.validate(floor_plans, reqs, planning_spec, allocation_set, arch_set)

    trace = DecisionTraceBuilder.build(
        requirements=reqs,
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        architectural_design_set=arch_set,
        geometry_set=floor_plans,
        validation_report=val_rep,
        project_name="Traceability Test",
    )

    # Verify every planned room has an unbroken entity chain
    for r_spec in planning_spec.floors[0].room_specs:
        r_id = r_spec.id
        chain = trace.get_entity_chain(r_id)
        assert chain is not None, f"Entity trace chain missing for room {r_id} ({r_spec.room_type})"

        # 1. Planning event present
        assert chain.planning_event is not None
        assert chain.planning_event.entity_id == r_id

        # 2. Allocation event present and linked
        assert chain.allocation_event is not None
        assert chain.allocation_event.entity_id == r_id
        alloc_reg_id = chain.allocation_event.output_references[0]
        assert alloc_reg_id.startswith("region_")

        # 3. Architectural event present and linked
        assert chain.architectural_event is not None
        assert chain.architectural_event.entity_id == r_id
        assert chain.architectural_event.evidence["allocated_region_id"] == alloc_reg_id

        # 4. Geometry event present and linked
        assert chain.geometry_event is not None
        assert chain.geometry_event.entity_id == r_id
        geo_room_id = chain.geometry_event.output_references[0]
        assert geo_room_id.startswith("georoom_")


def test_end_to_end_multi_design_trace():
    """Verify trace creation from MultiDesignGenerator with distinct alternatives and diversity matrices."""
    brief = """
    Single floor family home on a 40 feet by 50 feet rectangular plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 spacious living room of 300 sq ft
    - 1 dining room of 150 sq ft
    - 1 kitchen of 120 sq ft
    - 1 master bedroom of 200 sq ft
    - 1 guest bedroom of 140 sq ft
    - 1 bathroom of 60 sq ft
    """
    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief, project_name="Multi-Design Trace")

    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)

    asaa = ASAAAllocator(seed=42)
    allocation_set = asaa.allocate(planning_spec)

    generator = MultiDesignGenerator()
    alt_set = generator.generate(
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        requirements=reqs,
        num_alternatives=3,
        candidate_budget=6,
        minimum_diversity_distance=0.15,
        project_name="Multi-Design Trace",
    )

    trace = DecisionTraceBuilder.build(
        requirements=reqs,
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        alternative_set=alt_set,
        project_name="Multi-Design Trace",
    )

    assert len(trace.alternatives) == 3
    alt1, alt2, alt3 = trace.alternatives[0], trace.alternatives[1], trace.alternatives[2]

    # Verify distinct strategies
    strategies = {alt1.strategy, alt2.strategy, alt3.strategy}
    assert len(strategies) >= 2

    # Verify diversity explanation between Alternative 1 and Alternative 2
    comp_text = ExplanationRenderer.render_diversity_explanation(trace, alt1.alternative_id, alt2.alternative_id)
    assert f"Structural Diversity Comparison: Alternative {alt1.index} vs Alternative {alt2.index}" in comp_text
    assert "Circulation Topology" in comp_text
    assert "Pairwise Diversity Distance" in comp_text


def test_multi_floor_trace_separation():
    """Verify that multi-floor trace strictly separates Floor 1 and Floor 2 rooms and tracks vertical core."""
    brief = """
    2-floor residential villa on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 250 sq ft
    - 1 dining room of 150 sq ft
    - 1 kitchen of 120 sq ft
    - staircase to upper floor
    Floor 2:
    - 1 master bedroom of 200 sq ft
    - 1 bedroom of 150 sq ft
    - 1 bathroom of 60 sq ft
    """
    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief, project_name="Two-Floor Trace")

    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)

    asaa = ASAAAllocator(seed=101)
    allocation_set = asaa.allocate(planning_spec)

    arch_agent = ArchitecturalAgent()
    arch_set = arch_agent.design(planning_spec=planning_spec, allocation_set=allocation_set, strategy="social_centric")

    geom_engine = GeometryEngine()
    floor_plans = geom_engine.construct(arch_set, allocation_set)

    trace = DecisionTraceBuilder.build(
        requirements=reqs,
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        architectural_design_set=arch_set,
        geometry_set=floor_plans,
        project_name="Two-Floor Trace",
    )

    # Verify rooms are strictly grouped on their respective floors
    f1_plan_events = [e for e in trace.get_events_by_stage(StageName.PLANNING) if e.floor_number == 1 and e.entity_type == "room"]
    f2_plan_events = [e for e in trace.get_events_by_stage(StageName.PLANNING) if e.floor_number == 2 and e.entity_type == "room"]

    f1_types = {e.evidence.get("room_type") for e in f1_plan_events}
    f2_types = {e.evidence.get("room_type") for e in f2_plan_events}

    assert "living" in f1_types
    assert "kitchen" in f1_types
    assert "master_bedroom" in f2_types
    assert "bedroom" in f2_types
    # No crossover
    assert "master_bedroom" not in f1_types
    assert "living" not in f2_types

    # Staircase intent present
    stair_evts = [e for e in trace.get_events_by_stage(StageName.PLANNING) if e.entity_type == "staircase"]
    assert len(stair_evts) >= 1


def test_refinement_loop_trace_linkage():
    """Verify closed loop traceability:

    Initial flawed design -> Validator detects issue -> Refinement -> Revised design -> Validator.
    Validation issue links to RefinementChange which links to RevisedDesign.
    """
    brief = """
    Design a 1-floor house on a 30 feet by 30 feet plot with 1.5m setbacks.
    Floor 1:
    - 1 living room of 150 sq ft
    - 1 bedroom of 100 sq ft
    - 1 bathroom of 40 sq ft
    """
    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief, project_name="Refinement Trace Test")

    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)

    asaa = ASAAAllocator(seed=42)
    allocation_set = asaa.allocate(planning_spec)

    arch_agent = ArchitecturalAgent()
    initial_design = arch_agent.design(planning_spec=planning_spec, allocation_set=allocation_set)

    # Introduce flaw: remove entrance door so initial validation fails
    flawed_design = copy.deepcopy(initial_design)
    for room in flawed_design.designs[0].rooms:
        if room.room_type == "living":
            room.doors = [d for d in room.doors if d.door_type != "entrance"]

    # Run RefinementLoop
    loop = RefinementLoop(max_iterations=3)
    ref_result = loop.run(
        initial_design=flawed_design,
        allocation_set=allocation_set,
        requirements=reqs,
        planning_spec=planning_spec,
        project_name="Refinement Trace Test",
    )
    assert ref_result.is_valid is True

    trace = DecisionTraceBuilder.build(
        requirements=reqs,
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        architectural_design_set=ref_result.final_design,
        geometry_set=ref_result.final_floor_plan_set,
        refinement_result=ref_result,
        project_name="Refinement Trace Test",
    )

    # Verify Refinement stage events exist and link to changes
    ref_events = trace.get_events_by_stage(StageName.REFINEMENT)
    assert len(ref_events) >= 1
    assert ref_events[0].source == ProvenanceSource.REFINEMENT_LLM.value
    assert ref_events[0].entity_id is not None

    # Render refinement narrative
    ref_narrative = ExplanationRenderer.render_refinement_explanation(trace)
    assert "Refinement & Iterative Correction Narrative" in ref_narrative
    assert "Change 1:" in ref_narrative


def test_irregular_plot_trace():
    """Verify trace preservation for irregular L-shaped plot."""
    l_shaped_plot = [
        (0.0, 0.0),
        (15.0, 0.0),
        (15.0, 8.0),
        (8.0, 8.0),
        (8.0, 15.0),
        (0.0, 15.0),
    ]
    brief = "Single floor house on a 50 feet by 50 feet plot with front setback: 1m, rear setback: 1m, side setback: 1m with 1 living room of 200 sq ft, 1 dining room of 100 sq ft, 1 kitchen of 80 sq ft."
    req_agent = RequirementAgent()
    reqs = req_agent.parse(brief, project_name="Irregular Trace Test")
    reqs.plot_shape = tuple(l_shaped_plot)

    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(reqs)

    asaa = ASAAAllocator(seed=77)
    allocation_set = asaa.allocate(planning_spec)

    trace = DecisionTraceBuilder.build(
        requirements=reqs,
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        project_name="Irregular Trace Test",
    )

    req_events = trace.get_events_by_stage(StageName.REQUIREMENT)
    plot_evt = next(e for e in req_events if e.entity_type == "plot")
    assert plot_evt.evidence["plot_shape"] == l_shaped_plot

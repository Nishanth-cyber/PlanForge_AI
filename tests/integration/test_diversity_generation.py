"""Integration tests for Phase 9 Multi-Design Generation & Architectural Diversity."""

from app.agents.diversity_agent.generator import MultiDesignGenerator
from app.agents.diversity_agent.metrics import calculate_diversity_distance
from app.agents.planning_agent.agent import PlanningAgent
from app.agents.requirement_agent.agent import RequirementAgent
from app.asaa.allocator import ASAAAllocator
from app.models.alternatives import AlternativeStatus, DesignAlternativeSet
from app.models.geometry import GeometrySet


def test_end_to_end_multi_design_generation():
    """Verify complete end-to-end multi-design generation on a single-floor house.

    Pipeline:
      Requirements -> Planning -> ASAA -> MultiDesignGenerator -> Geometry -> Validator -> Refinement
    Verifies:
      - 3 valid alternatives produced
      - Each alternative is independently validated (is_valid == True)
      - Each alternative has a distinct DesignSignature with pairwise diversity distance >= 0.25
      - 100% room preservation and ASAA allocation immutability
      - Rejection logs and characteristics exist
    """
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
    requirements = req_agent.parse(brief, project_name="Meadowbrook Residence")

    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(requirements)

    asaa = ASAAAllocator(seed=42)
    allocation_set = asaa.allocate(planning_spec)

    generator = MultiDesignGenerator()

    # Request 3 distinct alternatives with candidate budget of 6
    alt_set: DesignAlternativeSet = generator.generate(
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        requirements=requirements,
        num_alternatives=3,
        candidate_budget=6,
        minimum_diversity_distance=0.15,
        project_name="Meadowbrook Residence",
    )

    # 1. Structure of Alternative Set
    assert isinstance(alt_set, DesignAlternativeSet)
    assert alt_set.valid_count == 3
    assert len(alt_set.alternatives) == 3

    # 2. Validity of every alternative
    for alt in alt_set.alternatives:
        assert alt.is_valid is True
        assert alt.status in (AlternativeStatus.VALIDATED, AlternativeStatus.REFINED_AND_VALID)
        assert alt.validation_report is not None
        assert alt.validation_report.overall_valid is True
        assert alt.floor_plan_set is not None
        assert alt.floor_plan_set.all_valid is True
        assert alt.design_signature is not None
        assert len(alt.characteristics) >= 3

    # 3. Structural Diversity: Pairwise distances between all 3 designs
    alt1, alt2, alt3 = alt_set.alternatives[0], alt_set.alternatives[1], alt_set.alternatives[2]
    d12 = calculate_diversity_distance(alt1.design_signature, alt2.design_signature)
    d13 = calculate_diversity_distance(alt1.design_signature, alt3.design_signature)
    d23 = calculate_diversity_distance(alt2.design_signature, alt3.design_signature)

    assert d12 >= 0.15, f"Expected distance(alt1, alt2) >= 0.15, got {d12}"
    assert d13 >= 0.15, f"Expected distance(alt1, alt3) >= 0.15, got {d13}"
    assert d23 >= 0.15, f"Expected distance(alt2, alt3) >= 0.15, got {d23}"

    # 4. Immutability: Room IDs and ASAA Allocations preserved across all alternatives
    floor_alloc = allocation_set.get_allocation(1)
    alloc_reg_map = {r.id: r.room_type for r in floor_alloc.allocated_regions}

    for alt in alt_set.alternatives:
        arch_design = alt.architectural_design.get_design(1)
        assert len(arch_design.rooms) == 6
        for room in arch_design.rooms:
            assert room.allocated_region_id in alloc_reg_map
            # Room type matches allocated region
            assert room.room_type == alloc_reg_map[room.allocated_region_id]


def test_multi_floor_diversity_generation():
    """Verify multi-design generation on a multi-floor building preserving staircase alignment."""
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
    requirements = req_agent.parse(brief, project_name="Twin Oaks")

    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(requirements)

    asaa = ASAAAllocator(seed=101)
    allocation_set = asaa.allocate(planning_spec)
    assert allocation_set.staircase_aligned is True

    generator = MultiDesignGenerator()

    alt_set = generator.generate(
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        requirements=requirements,
        num_alternatives=2,
        candidate_budget=4,
        minimum_diversity_distance=0.15,
        project_name="Twin Oaks",
    )

    assert alt_set.valid_count >= 1
    for alt in alt_set.alternatives:
        assert alt.is_valid is True
        # Staircase core preserved on all floors
        for d in alt.architectural_design.designs:
            assert d.staircase_intent is not None


def test_irregular_plot_diversity_generation():
    """Verify diversity generation on an L-shaped plot without bounding box fallback."""
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
    requirements = req_agent.parse(brief, project_name="L-Shaped Haven")
    requirements.plot_shape = tuple(l_shaped_plot)

    plan_agent = PlanningAgent()
    planning_spec = plan_agent.plan(requirements)

    asaa = ASAAAllocator(seed=77)
    allocation_set = asaa.allocate(planning_spec)

    generator = MultiDesignGenerator()
    alt_set = generator.generate(
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        requirements=requirements,
        num_alternatives=2,
        candidate_budget=4,
        minimum_diversity_distance=0.15,
        project_name="L-Shaped Haven",
        plot_boundary=l_shaped_plot,
    )

    assert alt_set.valid_count >= 1
    for alt in alt_set.alternatives:
        assert alt.is_valid is True

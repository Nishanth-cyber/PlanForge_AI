"""Unit tests for MultiDesignGenerator coordinator and candidate filtering."""

from unittest.mock import MagicMock
from app.agents.architectural_agent.agent import ArchitecturalAgent
from app.agents.diversity_agent.generator import MultiDesignGenerator
from app.agents.diversity_agent.signature import DesignSignatureBuilder
from app.agents.refinement_agent.loop import RefinementLoop
from app.models.allocation import Allocation, AllocationSet, AllocatedRegion
from app.models.alternatives import (
    AlternativeStatus,
    DesignAlternative,
    DesignAlternativeSet,
    DesignSignature,
    RejectionReason,
)
from app.models.architectural_design import (
    ArchitecturalDesign,
    ArchitecturalDesignSet,
    RoomDesign,
)
from app.models.doors import DoorIntent
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec
from app.models.refinement import RefinementResult, RefinementStatus
from app.models.requirements import Requirements
from app.models.validation import ValidationReport, ValidationResult


def _create_test_environment():
    """Helper to create minimal valid PlanningSpec and AllocationSet."""
    reg1 = AllocatedRegion(id="reg_1", room_type="living", approximate_dimensions=(5.0, 5.0), polygon=[(0, 0), (5, 0), (5, 5), (0, 5)])
    reg2 = AllocatedRegion(id="reg_2", room_type="dining", approximate_dimensions=(4.0, 4.0), polygon=[(5, 0), (9, 0), (9, 4), (5, 4)])
    alloc_set = AllocationSet(allocations=[Allocation(floor_number=1, allocated_regions=[reg1, reg2])])

    rs1 = RoomSpec(id="r1", room_type="living", floor_number=1)
    rs2 = RoomSpec(id="r2", room_type="dining", floor_number=1)
    plan_spec = PlanningSpec(floors=[FloorPlanSpec(floor_number=1, room_specs=[rs1, rs2])])

    return plan_spec, alloc_set


def test_validity_plus_diversity_filtering():
    """Verify the mandatory test requirement:
    Candidates:
      A = valid, initial candidate
      B = invalid (fails validation, refinement fails), even though diverse
      C = valid and diverse relative to A
      D = valid duplicate of A
    Selection must accept: A, C
    Selection must reject:
      B because invalid (never accepted despite diversity)
      D because duplicate of A
    """
    plan_spec, alloc_set = _create_test_environment()

    # Candidate A: Valid Living -> Dining direct
    design_a = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[
                    RoomDesign(id="r1", room_type="living", allocated_region_id="reg_1", doors=[DoorIntent(connects_to="dining")]),
                    RoomDesign(id="r2", room_type="dining", allocated_region_id="reg_2", doors=[DoorIntent(connects_to="living")]),
                ],
            )
        ]
    )

    # Candidate B: Structurally diverse (corridor) but invalid
    design_b = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[
                    RoomDesign(id="r1", room_type="living", allocated_region_id="reg_1", doors=[DoorIntent(connects_to="circulation")]),
                    RoomDesign(id="r2", room_type="dining", allocated_region_id="reg_2", doors=[DoorIntent(connects_to="circulation")]),
                ],
            )
        ]
    )

    # Candidate C: Valid and diverse (living to exterior only, dining separate)
    design_c = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[
                    RoomDesign(id="r1", room_type="living", allocated_region_id="reg_1", intended_shape="square", doors=[DoorIntent(connects_to="exterior", door_type="entrance")]),
                    RoomDesign(id="r2", room_type="dining", allocated_region_id="reg_2", intended_shape="square", doors=[DoorIntent(connects_to="circulation")]),
                ],
            )
        ]
    )

    # Candidate D: Structurally identical duplicate of A
    design_d = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[
                    RoomDesign(id="r1", room_type="living", allocated_region_id="reg_1", doors=[DoorIntent(connects_to="dining")]),
                    RoomDesign(id="r2", room_type="dining", allocated_region_id="reg_2", doors=[DoorIntent(connects_to="living")]),
                ],
            )
        ]
    )

    # Candidate D is placed before C so it is evaluated before budget target of 2 is satisfied
    candidates = [design_a, design_b, design_d, design_c]

    mock_arch_agent = MagicMock(spec=ArchitecturalAgent)
    mock_arch_agent.design.side_effect = candidates

    # Mock RefinementLoop: A valid, B invalid, C valid, D valid
    mock_refinement_loop = MagicMock(spec=RefinementLoop)

    def fake_refine_run(initial_design, **kwargs):
        is_cand_b = (initial_design == design_b)
        status = RefinementStatus.REFINEMENT_FAILED if is_cand_b else RefinementStatus.VALID_ON_INITIAL_PASS
        is_valid = not is_cand_b
        return RefinementResult(
            status=status,
            initial_design=initial_design,
            final_design=initial_design,
            termination_reason="Failed validation" if is_cand_b else "Valid design",
            validation_reports=[ValidationReport(results=[ValidationResult(floor_number=1, is_valid=is_valid)])],
        )

    mock_refinement_loop.run.side_effect = fake_refine_run

    generator = MultiDesignGenerator(
        architectural_agent=mock_arch_agent,
        refinement_loop=mock_refinement_loop,
    )

    result_set = generator.generate(
        planning_spec=plan_spec,
        allocation_set=alloc_set,
        num_alternatives=2,
        candidate_budget=4,
        minimum_diversity_distance=0.20,
    )

    # Assertions:
    # Exactly 2 alternatives accepted: A and C
    assert result_set.valid_count == 2
    accepted_designs = [alt.architectural_design for alt in result_set.alternatives]
    assert design_a in accepted_designs
    assert design_c in accepted_designs
    assert design_b not in accepted_designs
    assert design_d not in accepted_designs

    # Rejected candidates contains B (validation_failure) and D (duplicate)
    rejected_reasons = {alt.rejection_reason for alt in result_set.rejected_candidates}
    assert RejectionReason.VALIDATION_FAILURE.value in rejected_reasons
    assert RejectionReason.DUPLICATE.value in rejected_reasons


def test_candidate_budget_and_insufficient_diversity():
    """Verify generator stops when candidate budget is exhausted and sets INSUFFICIENT_DIVERSITY."""
    plan_spec, alloc_set = _create_test_environment()

    # Generator returns duplicate designs for all calls
    design_dup = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[RoomDesign(id="r1", room_type="living", allocated_region_id="reg_1", doors=[DoorIntent(connects_to="dining")])],
            )
        ]
    )

    mock_arch_agent = MagicMock(spec=ArchitecturalAgent)
    mock_arch_agent.design.return_value = design_dup

    mock_refinement_loop = MagicMock(spec=RefinementLoop)
    mock_refinement_loop.run.return_value = RefinementResult(
        status=RefinementStatus.VALID_ON_INITIAL_PASS,
        initial_design=design_dup,
        final_design=design_dup,
        validation_reports=[ValidationReport(results=[ValidationResult(floor_number=1, is_valid=True)])],
    )

    generator = MultiDesignGenerator(
        architectural_agent=mock_arch_agent,
        refinement_loop=mock_refinement_loop,
    )

    result_set = generator.generate(
        planning_spec=plan_spec,
        allocation_set=alloc_set,
        num_alternatives=3,
        candidate_budget=3,
    )

    # 1 accepted, 2 rejected as duplicates
    assert result_set.valid_count == 1
    assert result_set.rejected_count == 2
    assert result_set.status == "INSUFFICIENT_DIVERSITY"

"""Unit tests for RefinementLoop coordinator."""

from unittest.mock import MagicMock
from app.agents.refinement_agent.agent import RefinementAgent
from app.agents.refinement_agent.loop import RefinementLoop
from app.geometry.engine import GeometryEngine
from app.llm.client import MockLLMClient
from app.models.allocation import Allocation, AllocationSet, AllocatedRegion
from app.models.architectural_design import ArchitecturalDesign, ArchitecturalDesignSet, RoomDesign
from app.models.doors import DoorIntent
from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.models.geometry import Geometry, GeoRoom, GeoWall, GeoDoor
from app.models.planning import PlanningSpec
from app.models.refinement import RefinementStatus
from app.models.requirements import Requirements
from app.models.validation import ValidationIssue, ValidationReport, ValidationResult
from app.validation.validator import FloorPlanValidator


def test_refinement_loop_valid_on_initial_pass():
    """Verify that an initially valid floor plan terminates immediately without LLM refinement."""
    alloc_set = AllocationSet(
        allocations=[
            Allocation(
                floor_number=1,
                allocated_regions=[
                    AllocatedRegion(
                        id="reg_1",
                        room_type="living",
                        approximate_dimensions=(5, 5),
                        polygon=[(1, 1), (6, 1), (6, 6), (1, 6)],
                    )
                ],
            )
        ]
    )
    design_set = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[
                    RoomDesign(
                        id="r_1",
                        room_type="living",
                        allocated_region_id="reg_1",
                        intended_dimensions=(5, 5),
                        doors=[DoorIntent(wall_orientation="south", connects_to="exterior", door_type="entrance")],
                    )
                ],
            )
        ]
    )

    # Mock validator returning True on initial pass
    mock_validator = MagicMock(spec=FloorPlanValidator)
    mock_report = ValidationReport(
        results=[ValidationResult(floor_number=1, is_valid=True, score=100.0)],
        iteration=0,
    )
    mock_validator.validate.return_value = mock_report

    mock_agent = MagicMock(spec=RefinementAgent)

    loop = RefinementLoop(refinement_agent=mock_agent, validator=mock_validator)
    result = loop.run(
        initial_design=design_set,
        allocation_set=alloc_set,
        requirements=Requirements(),
    )

    assert result.status == RefinementStatus.VALID_ON_INITIAL_PASS
    assert result.is_valid is True
    assert len(result.iterations) == 1
    assert result.iterations[0].iteration == 0
    # RefinementAgent should never be called
    mock_agent.refine.assert_not_called()


def test_refinement_loop_stops_on_no_change():
    """Verify that if RefinementAgent produces an unchanged design, loop stops with REFINEMENT_FAILED."""
    alloc_set = AllocationSet(
        allocations=[
            Allocation(
                floor_number=1,
                allocated_regions=[
                    AllocatedRegion(
                        id="reg_1",
                        room_type="living",
                        approximate_dimensions=(5, 5),
                        polygon=[(0, 0), (5, 0), (5, 5), (0, 5)],
                    )
                ],
            )
        ]
    )
    design_set = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[RoomDesign(id="r_1", room_type="living", allocated_region_id="reg_1", intended_dimensions=(4, 4))],
            )
        ]
    )

    # Validator returns failure
    mock_validator = MagicMock(spec=FloorPlanValidator)
    invalid_report = ValidationReport(
        results=[
            ValidationResult(
                floor_number=1,
                is_valid=False,
                issues=[ValidationIssue(severity="error", category="door", check="missing_entrance")],
            )
        ],
        iteration=0,
    )
    mock_validator.validate.return_value = invalid_report

    # Agent returns unchanged design and empty change list
    mock_agent = MagicMock(spec=RefinementAgent)
    mock_agent.refine.return_value = (design_set, [])

    loop = RefinementLoop(refinement_agent=mock_agent, validator=mock_validator, max_iterations=3)
    result = loop.run(initial_design=design_set, allocation_set=alloc_set)

    assert result.status == RefinementStatus.REFINEMENT_FAILED
    assert "unchanged design" in result.termination_reason


def test_refinement_loop_enforces_max_iterations():
    """Verify loop terminates with MAX_ITERATIONS_REACHED if errors persist."""
    alloc_set = AllocationSet(
        allocations=[
            Allocation(
                floor_number=1,
                allocated_regions=[
                    AllocatedRegion(
                        id="reg_1",
                        room_type="living",
                        approximate_dimensions=(5, 5),
                        polygon=[(0, 0), (5, 0), (5, 5), (0, 5)],
                    )
                ],
            )
        ]
    )
    design_set = ArchitecturalDesignSet(
        designs=[
            ArchitecturalDesign(
                floor_number=1,
                rooms=[RoomDesign(id="r_1", room_type="living", allocated_region_id="reg_1", intended_dimensions=(4, 4))],
            )
        ]
    )

    mock_validator = MagicMock(spec=FloorPlanValidator)
    invalid_report = ValidationReport(
        results=[
            ValidationResult(
                floor_number=1,
                is_valid=False,
                issues=[ValidationIssue(severity="error", category="door", check="missing_entrance")],
            )
        ]
    )
    mock_validator.validate.return_value = invalid_report

    # Agent returns a different design each time, but validator keeps failing
    counter = [0]
    def fake_refine(ctx):
        counter[0] += 1
        d = ArchitecturalDesignSet(
            designs=[
                ArchitecturalDesign(
                    floor_number=1,
                    rooms=[RoomDesign(id="r_1", room_type="living", allocated_region_id="reg_1", intended_dimensions=(4.0 + 0.1 * counter[0], 4.0))],
                )
            ],
            version=counter[0],
        )
        return d, [MagicMock()]

    mock_agent = MagicMock(spec=RefinementAgent)
    mock_agent.refine.side_effect = fake_refine

    loop = RefinementLoop(refinement_agent=mock_agent, validator=mock_validator, max_iterations=2)
    result = loop.run(initial_design=design_set, allocation_set=alloc_set)

    assert result.status == RefinementStatus.MAX_ITERATIONS_REACHED
    assert result.total_iterations == 3  # Iteration 0, 1, 2
    assert "maximum allowed refinement iterations" in result.termination_reason

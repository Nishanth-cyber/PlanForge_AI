"""Unit tests verifying refinement maintains design strategy and strict invariants."""

from app.agents.refinement_agent.context import RefinementContextBuilder
from app.agents.refinement_agent.output_validator import RefinementOutputValidator
from app.agents.refinement_agent.prompts import build_refinement_floor_prompt
from app.models.allocation import Allocation, AllocationSet, AllocatedRegion
from app.models.architectural_design import (
    ArchitecturalDesign,
    ArchitecturalDesignSet,
    RoomDesign,
)
from app.models.doors import DoorIntent
from app.models.planning import PlanningSpec
from app.models.requirements import Requirements
from app.models.validation import ValidationReport


def test_refinement_prompt_includes_target_strategy():
    """Verify target strategy is included in refinement prompt instructions."""
    floor_d = ArchitecturalDesign(
        floor_number=1,
        rooms=[RoomDesign(id="r1", room_type="living", allocated_region_id="reg_1")],
    )
    alloc = Allocation(
        floor_number=1,
        allocated_regions=[AllocatedRegion(id="reg_1", room_type="living", approximate_dimensions=(4.0, 5.0))],
    )

    prompt = build_refinement_floor_prompt(
        floor_design=floor_d,
        allocation=alloc,
        diagnostics_text="Error: missing door",
        iteration=1,
        target_design_strategy="corridor_centric",
    )

    assert "TARGET DESIGN STRATEGY:" in prompt
    assert "corridor_centric" in prompt
    assert "Preserve the distinctive architectural character" in prompt


def test_refinement_output_validator_rejects_allocation_or_room_tampering():
    """Verify RefinementOutputValidator strictly enforces allocation and room immutability."""
    alloc = Allocation(
        floor_number=1,
        allocated_regions=[
            AllocatedRegion(id="reg_1", room_type="living", approximate_dimensions=(4.0, 5.0), area_sqm=20.0),
            AllocatedRegion(id="reg_2", room_type="dining", approximate_dimensions=(3.0, 4.0), area_sqm=12.0),
        ],
    )
    current_floor = ArchitecturalDesign(
        floor_number=1,
        rooms=[
            RoomDesign(id="r1", room_type="living", allocated_region_id="reg_1"),
            RoomDesign(id="r2", room_type="dining", allocated_region_id="reg_2"),
        ],
    )

    # 1. Attempt to move room to different allocation region
    tampered_allocation_payload = {
        "rooms": [
            {"id": "r1", "room_type": "living", "allocated_region_id": "reg_2"},  # Tampered!
            {"id": "r2", "room_type": "dining", "allocated_region_id": "reg_2"},
        ]
    }
    try:
        RefinementOutputValidator.validate_and_parse(tampered_allocation_payload, current_floor, alloc)
        assert False, "Should have raised exception for tampered allocation region"
    except Exception as e:
        assert "allocated_region_id" in str(e).lower() or "allocation" in str(e).lower()

    # 2. Attempt to invent a new room
    invented_room_payload = {
        "rooms": [
            {"id": "r1", "room_type": "living", "allocated_region_id": "reg_1"},
            {"id": "r2", "room_type": "dining", "allocated_region_id": "reg_2"},
            {"id": "r3_invented", "room_type": "bedroom", "allocated_region_id": "reg_1"},
        ]
    }
    try:
        RefinementOutputValidator.validate_and_parse(invented_room_payload, current_floor, alloc)
        assert False, "Should have raised exception for invented room"
    except Exception as e:
        assert "unrecognized room" in str(e).lower() or "invent" in str(e).lower()

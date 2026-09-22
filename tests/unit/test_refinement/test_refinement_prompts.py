"""Unit tests for refinement prompts."""

from app.agents.refinement_agent.prompts import (
    REFINEMENT_SYSTEM_PROMPT,
    build_refinement_floor_prompt,
)
from app.models.allocation import Allocation, AllocatedRegion
from app.models.architectural_design import ArchitecturalDesign, RoomDesign
from app.models.doors import DoorIntent


def test_refinement_system_prompt_invariants():
    """Verify system prompt contains core architectural boundary directives."""
    assert "PRESERVE ROOM IDENTITIES" in REFINEMENT_SYSTEM_PROMPT
    assert "ALLOCATION IMMUTABILITY" in REFINEMENT_SYSTEM_PROMPT
    assert "ARCHITECTURAL INTENT LEVEL (NO RAW GEOMETRY)" in REFINEMENT_SYSTEM_PROMPT
    assert "MUST NOT invent any new rooms" in REFINEMENT_SYSTEM_PROMPT
    assert "MUST NOT delete any required rooms" in REFINEMENT_SYSTEM_PROMPT


def test_build_refinement_floor_prompt():
    """Verify floor prompt contains current rooms, allocation bounds, and diagnostics."""
    floor_design = ArchitecturalDesign(
        floor_number=1,
        rooms=[
            RoomDesign(
                id="room_liv",
                room_type="living",
                allocated_region_id="reg_liv",
                intended_dimensions=(4.0, 5.0),
                doors=[DoorIntent(wall_orientation="south", connects_to="dining")],
            )
        ],
    )
    allocation = Allocation(
        floor_number=1,
        allocated_regions=[
            AllocatedRegion(
                id="reg_liv",
                room_type="living",
                target_area_sqm=20.0,
                approximate_dimensions=(4.2, 5.2),
            )
        ],
    )
    diagnostics = "### HARD VALIDATION ERRORS (1):\n  1. [DOOR] missing_entrance_connection: No entry"

    prompt = build_refinement_floor_prompt(
        floor_design=floor_design,
        allocation=allocation,
        diagnostics_text=diagnostics,
        iteration=2,
    )

    assert "REFINEMENT PASS (Iteration 2) FOR FLOOR 1" in prompt
    assert "missing_entrance_connection" in prompt
    assert "room_liv" in prompt
    assert "reg_liv" in prompt
    assert "approximate_dimensions" in prompt

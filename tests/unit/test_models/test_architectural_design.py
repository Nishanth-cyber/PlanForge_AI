"""Unit tests for Architectural Design (LLM proposal) data contracts."""

from app.models.architectural_design import (
    RoomDesign,
    RoomDesignProposal,
    ArchitecturalDesign,
    ArchitecturalDesignSet,
    Door,
    Window,
)
from app.models.doors import DoorIntent
from app.models.windows import WindowIntent
from app.models.staircase import StaircaseIntent


def test_aliases_consistency():
    """Verify backward-compatible aliases."""
    assert RoomDesignProposal is RoomDesign
    assert Door is DoorIntent
    assert Window is WindowIntent


def test_room_design_proposal():
    """Test RoomDesign with doors, windows, proposed boundary, and rationale."""
    d1 = DoorIntent(connects_from="bedroom_01", connects_to="hallway", door_type="interior")
    w1 = WindowIntent(room_id="bedroom_01", wall_orientation="south")

    room = RoomDesign(
        room_type="bedroom",
        allocated_region_id="region_bed_01",
        floor_number=1,
        intended_shape="rectangular",
        intended_dimensions=(3.5, 4.0),
        intended_area_sqm=14.0,
        proposed_boundary=[(2.0, 3.0), (5.5, 3.0), (5.5, 7.0), (2.0, 7.0)],
        doors=[d1],
        windows=[w1],
        connected_spaces=["hallway"],
        design_rationale="Corner placement maximizes south-facing natural lighting",
    )

    assert room.id is not None
    assert room.intended_shape == "rectangular"
    assert room.intended_dimensions == (3.5, 4.0)
    assert len(room.doors) == 1
    assert len(room.windows) == 1
    assert room.design_rationale != ""


def test_architectural_design_floor_and_set():
    """Test ArchitecturalDesign collection and ArchitecturalDesignSet multi-floor query."""
    d1 = DoorIntent(connects_from="living", connects_to="patio", door_type="exterior")
    w1 = WindowIntent(room_id="living", wall_orientation="north")
    r_living = RoomDesign(room_type="living", doors=[d1], windows=[w1])

    stair = StaircaseIntent(from_floor=1, to_floor=2, stair_type="straight")

    design_f1 = ArchitecturalDesign(
        floor_number=1,
        floor_name="Ground Floor",
        rooms=[r_living],
        staircase_intent=stair,
        design_rationale="Open-plan layout with living connected to outdoor patio",
    )

    design_f2 = ArchitecturalDesign(
        floor_number=2,
        floor_name="Upper Floor",
        rooms=[RoomDesign(room_type="bedroom")],
    )

    design_set = ArchitecturalDesignSet(
        designs=[design_f1, design_f2],
    )

    assert design_f1.get_room(r_living.id) == r_living
    assert len(design_f1.get_rooms_by_type("living")) == 1
    assert len(design_f1.all_door_intents()) == 1
    assert len(design_f1.all_window_intents()) == 1
    assert design_f1.staircase_intent == stair

    assert design_set.get_design(1) == design_f1
    assert design_set.get_design(2) == design_f2
    assert design_set.get_design(3) is None

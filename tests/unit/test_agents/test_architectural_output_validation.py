"""Unit tests for ArchitecturalOutputValidator and schema error handling."""

import pytest
from app.agents.architectural_agent.context import FloorDesignContext, RoomDesignContext
from app.agents.architectural_agent.structured_output import (
    AllocationMismatchError,
    ArchitecturalOutputValidator,
    DimensionExceedsAllocationError,
    InvalidShapeError,
    MalformedLLMResponseError,
    RoomCoverageError,
)


def _make_dummy_floor_context() -> FloorDesignContext:
    r1 = RoomDesignContext(
        room_id="room_1",
        room_type="living",
        floor_number=1,
        priority="high",
        category="social",
        target_area_sqm=30.0,
        min_area_sqm=25.0,
        max_area_sqm=35.0,
        allocated_region_id="reg_1",
        allocated_area_sqm=30.0,
        approximate_dimensions=(5.0, 6.0),
        allocated_polygon=((0.0, 0.0), (5.0, 0.0), (5.0, 6.0), (0.0, 6.0)),
        adjacent_region_ids=("reg_2",),
        adjacent_room_types=("kitchen",),
        user_required_adjacencies=(),
        system_preferred_adjacencies=(),
        avoid_rooms=(),
        attached_to_room_id=None,
    )
    r2 = RoomDesignContext(
        room_id="room_2",
        room_type="kitchen",
        floor_number=1,
        priority="normal",
        category="service",
        target_area_sqm=15.0,
        min_area_sqm=12.0,
        max_area_sqm=18.0,
        allocated_region_id="reg_2",
        allocated_area_sqm=15.0,
        approximate_dimensions=(3.0, 5.0),
        allocated_polygon=((5.0, 0.0), (8.0, 0.0), (8.0, 5.0), (5.0, 5.0)),
        adjacent_region_ids=("reg_1",),
        adjacent_room_types=("living",),
        user_required_adjacencies=(),
        system_preferred_adjacencies=(),
        avoid_rooms=(),
        attached_to_room_id=None,
    )
    return FloorDesignContext(
        floor_number=1,
        floor_name="Ground Floor",
        rooms=(r1, r2),
        circulation_zones=(),
        circulation_notes="",
        entrance_intent=None,
        staircase_intent=None,
        staircase_region_id=None,
        plot_orientation="north",
    )


def test_validator_valid_proposal():
    """Test valid proposal passes validation and constructs RoomDesign instances."""
    ctx = _make_dummy_floor_context()
    raw = {
        "rooms": [
            {
                "room_id": "room_1",
                "room_type": "living",
                "allocated_region_id": "reg_1",
                "intended_shape": "rectangular",
                "intended_dimensions": [5.0, 6.0],
                "intended_area_sqm": 30.0,
                "doors": [
                    {
                        "connects_to": "circulation",
                        "door_type": "interior",
                        "recommended_width": 0.9,
                        "recommended_height": 2.1,
                    }
                ],
                "windows": [
                    {
                        "wall_orientation": "north",
                        "window_type": "standard",
                        "recommended_width": 1.5,
                        "recommended_height": 1.2,
                    }
                ],
                "design_rationale": "High ceiling living area facing north",
            },
            {
                "room_id": "room_2",
                "room_type": "kitchen",
                "allocated_region_id": "reg_2",
                "intended_shape": "rectangular",
                "intended_dimensions": [3.0, 5.0],
                "intended_area_sqm": 15.0,
            },
        ]
    }

    designs = ArchitecturalOutputValidator.validate_and_parse(raw, ctx)
    assert len(designs) == 2
    d1, d2 = designs[0], designs[1]
    assert d1.room_type == "living"
    assert d1.intended_shape == "rectangular"
    assert d1.intended_dimensions == (5.0, 6.0)
    assert d1.intended_area_sqm == 30.0
    assert len(d1.doors) == 1
    assert len(d1.windows) == 1
    assert d1.doors[0].connects_to == "circulation"
    assert d1.windows[0].wall_orientation == "north"


def test_validator_missing_rooms_key():
    """Test validator rejects responses without 'rooms' key."""
    ctx = _make_dummy_floor_context()
    with pytest.raises(MalformedLLMResponseError, match="missing 'rooms' list"):
        ArchitecturalOutputValidator.validate_and_parse({"status": "done"}, ctx)


def test_validator_missing_room_coverage():
    """Test validator raises RoomCoverageError if any allocated room is omitted."""
    ctx = _make_dummy_floor_context()
    # Missing room_2
    raw = {
        "rooms": [
            {
                "room_id": "room_1",
                "allocated_region_id": "reg_1",
                "intended_area_sqm": 30.0,
            }
        ]
    }
    with pytest.raises(RoomCoverageError, match="Missing room proposals"):
        ArchitecturalOutputValidator.validate_and_parse(raw, ctx)


def test_validator_invented_room_rejected():
    """Test validator raises RoomCoverageError if an unknown room is added."""
    ctx = _make_dummy_floor_context()
    raw = {
        "rooms": [
            {"room_id": "room_1", "allocated_region_id": "reg_1", "intended_area_sqm": 30.0},
            {"room_id": "room_2", "allocated_region_id": "reg_2", "intended_area_sqm": 15.0},
            {"room_id": "room_99_cinema", "intended_area_sqm": 20.0},  # Invented!
        ]
    }
    with pytest.raises(RoomCoverageError, match="Invented room detected"):
        ArchitecturalOutputValidator.validate_and_parse(raw, ctx)


def test_validator_duplicate_room_rejected():
    """Test validator raises RoomCoverageError if the same room is specified twice."""
    ctx = _make_dummy_floor_context()
    raw = {
        "rooms": [
            {"room_id": "room_1", "allocated_region_id": "reg_1", "intended_area_sqm": 30.0},
            {"room_id": "room_1", "allocated_region_id": "reg_1", "intended_area_sqm": 30.0},
        ]
    }
    with pytest.raises(RoomCoverageError, match="Duplicate room proposal"):
        ArchitecturalOutputValidator.validate_and_parse(raw, ctx)


def test_validator_allocation_mismatch_rejected():
    """Test validator raises AllocationMismatchError if room cites wrong allocation ID."""
    ctx = _make_dummy_floor_context()
    raw = {
        "rooms": [
            {"room_id": "room_1", "allocated_region_id": "wrong_reg_id", "intended_area_sqm": 30.0},
            {"room_id": "room_2", "allocated_region_id": "reg_2", "intended_area_sqm": 15.0},
        ]
    }
    with pytest.raises(AllocationMismatchError, match="allocation reference mismatch"):
        ArchitecturalOutputValidator.validate_and_parse(raw, ctx)


def test_validator_area_exceeds_allocation_rejected():
    """Test validator raises DimensionExceedsAllocationError if proposed area exceeds allocation."""
    ctx = _make_dummy_floor_context()
    # Allocated area for room_2 is 15.0, proposing 25.0 (> 15 * 1.05)
    raw = {
        "rooms": [
            {"room_id": "room_1", "allocated_region_id": "reg_1", "intended_area_sqm": 30.0},
            {"room_id": "room_2", "allocated_region_id": "reg_2", "intended_area_sqm": 25.0},
        ]
    }
    with pytest.raises(DimensionExceedsAllocationError, match="exceeds ASAA allocated region area"):
        ArchitecturalOutputValidator.validate_and_parse(raw, ctx)


def test_validator_non_positive_dimensions_rejected():
    """Test validator raises DimensionExceedsAllocationError for zero or negative dimensions."""
    ctx = _make_dummy_floor_context()
    raw = {
        "rooms": [
            {
                "room_id": "room_1",
                "allocated_region_id": "reg_1",
                "intended_dimensions": [-5.0, 6.0],
                "intended_area_sqm": 30.0,
            },
            {"room_id": "room_2", "allocated_region_id": "reg_2", "intended_area_sqm": 15.0},
        ]
    }
    with pytest.raises(DimensionExceedsAllocationError, match="dimensions must be positive"):
        ArchitecturalOutputValidator.validate_and_parse(raw, ctx)


def test_validator_unsupported_shape_rejected():
    """Test validator raises InvalidShapeError for unsupported shape types."""
    ctx = _make_dummy_floor_context()
    raw = {
        "rooms": [
            {
                "room_id": "room_1",
                "allocated_region_id": "reg_1",
                "intended_shape": "octagonal_spiral",
                "intended_area_sqm": 30.0,
            },
            {"room_id": "room_2", "allocated_region_id": "reg_2", "intended_area_sqm": 15.0},
        ]
    }
    with pytest.raises(InvalidShapeError, match="unsupported shape"):
        ArchitecturalOutputValidator.validate_and_parse(raw, ctx)

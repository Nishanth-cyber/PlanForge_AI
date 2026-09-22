"""Unit tests for ArchitecturalAgent single-floor design generation."""

import json
from app.agents.architectural_agent.agent import ArchitecturalAgent
from app.llm.client import MockLLMClient
from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
from app.models.architectural_design import ArchitecturalDesignSet, RoomDesign
from app.models.doors import DoorIntent
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec
from app.models.windows import WindowIntent


def _build_test_setup():
    r_liv = RoomSpec(id="rs_1", room_type="living", floor_number=1, target_area_sqm=25.0)
    r_kit = RoomSpec(id="rs_2", room_type="kitchen", floor_number=1, target_area_sqm=12.0)
    f_spec = FloorPlanSpec(
        floor_number=1,
        floor_name="Ground Floor",
        room_specs=[r_liv, r_kit],
    )
    p_spec = PlanningSpec(floors=[f_spec])

    reg_1 = AllocatedRegion(
        id="reg_1",
        room_type="living",
        room_spec_id="rs_1",
        floor_number=1,
        area_sqm=25.0,
        approximate_dimensions=(5.0, 5.0),
    )
    reg_2 = AllocatedRegion(
        id="reg_2",
        room_type="kitchen",
        room_spec_id="rs_2",
        floor_number=1,
        area_sqm=12.0,
        approximate_dimensions=(3.0, 4.0),
    )
    alloc = Allocation(floor_number=1, allocated_regions=[reg_1, reg_2])
    alloc_set = AllocationSet(allocations=[alloc])

    return p_spec, alloc_set


def test_architectural_agent_deterministic_default():
    """Test ArchitecturalAgent generates valid design set with default deterministic mock."""
    p_spec, alloc_set = _build_test_setup()
    agent = ArchitecturalAgent()

    design_set = agent.design(p_spec, alloc_set)
    assert isinstance(design_set, ArchitecturalDesignSet)
    assert len(design_set.designs) == 1

    d1 = design_set.get_design(1)
    assert d1 is not None
    assert d1.floor_number == 1
    assert len(d1.rooms) == 2

    living_design = d1.get_rooms_by_type("living")[0]
    assert living_design.intended_shape == "rectangular"
    assert living_design.intended_area_sqm == 25.0
    assert len(living_design.doors) >= 1
    assert len(living_design.windows) >= 1
    assert living_design.design_rationale != ""


def test_architectural_agent_custom_mock_response():
    """Test ArchitecturalAgent with explicit custom mock response."""
    p_spec, alloc_set = _build_test_setup()

    custom_payload = {
        "floor_number": 1,
        "design_rationale": "Custom open-concept layout",
        "rooms": [
            {
                "room_id": "rs_1",
                "room_type": "living",
                "allocated_region_id": "reg_1",
                "intended_shape": "rectangular",
                "intended_dimensions": [5.0, 5.0],
                "intended_area_sqm": 25.0,
                "doors": [
                    {
                        "connects_to": "foyer",
                        "door_type": "entrance",
                        "wall_orientation": "north",
                        "recommended_width": 1.0,
                        "recommended_height": 2.2,
                        "rationale": "Main entrance door",
                    }
                ],
                "windows": [
                    {
                        "wall_orientation": "east",
                        "window_type": "bay",
                        "recommended_width": 2.0,
                        "recommended_height": 1.5,
                        "sill_height": 0.8,
                        "rationale": "Morning sunlight bay window",
                    }
                ],
                "connected_spaces": ["foyer", "kitchen"],
                "design_rationale": "Spacious family gathering area",
            },
            {
                "room_id": "rs_2",
                "room_type": "kitchen",
                "allocated_region_id": "reg_2",
                "intended_shape": "rectangular",
                "intended_dimensions": [3.0, 4.0],
                "intended_area_sqm": 12.0,
                "doors": [
                    {
                        "connects_to": "living",
                        "door_type": "interior",
                        "recommended_width": 0.9,
                        "recommended_height": 2.1,
                    }
                ],
                "windows": [
                    {
                        "wall_orientation": "west",
                        "window_type": "ventilation",
                        "recommended_width": 0.8,
                        "recommended_height": 0.8,
                        "sill_height": 1.2,
                    }
                ],
                "connected_spaces": ["living"],
                "design_rationale": "Efficient L-counter kitchen layout",
            },
        ],
    }

    mock_client = MockLLMClient(default_response=json.dumps(custom_payload))
    agent = ArchitecturalAgent(llm_client=mock_client)

    design_set = agent.design(p_spec, alloc_set)
    d1 = design_set.get_design(1)

    assert d1.design_rationale == "Custom open-concept layout"
    living = d1.get_rooms_by_type("living")[0]
    assert living.doors[0].connects_to == "foyer"
    assert living.doors[0].door_type == "entrance"
    assert living.windows[0].window_type == "bay"
    assert living.windows[0].wall_orientation == "east"

    kitchen = d1.get_rooms_by_type("kitchen")[0]
    assert kitchen.windows[0].window_type == "ventilation"

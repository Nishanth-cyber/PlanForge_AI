"""Unit tests verifying strict architectural boundaries of the Planning Agent.

The Planning Agent MUST NOT:
- generate room coordinates (x, y)
- generate polygons
- generate final room dimensions
- generate wall geometry
- generate doors geometry
- generate windows geometry
- generate corridor geometry
- generate staircase geometry
- invoke any Shapely geometry operations
"""

import pytest
from app.agents.planning_agent import PlanningAgent
from app.models.requirements import Requirements, FloorRequirement, RoomRequirement


@pytest.fixture
def planner():
    return PlanningAgent()


def test_no_geometry_in_planning_spec(planner):
    f1 = FloorRequirement(
        floor_number=1,
        room_requirements=[
            RoomRequirement(room_type="living", preferred_area_sqm=25.0),
            RoomRequirement(room_type="kitchen", preferred_area_sqm=12.0),
            RoomRequirement(room_type="master_bedroom", preferred_area_sqm=20.0),
            RoomRequirement(room_type="bathroom", preferred_area_sqm=6.0, attached_to="master_bedroom"),
        ],
    )
    reqs = Requirements(
        plot_dimensions=(15.0, 20.0),
        plot_area_sqm=300.0,
        target_floors=1,
        floors=[f1],
    )
    spec = planner.plan(reqs)

    # 1. Inspect PlanningSpec attributes
    assert not hasattr(spec, "coordinates")
    assert not hasattr(spec, "polygon")
    assert not hasattr(spec, "walls")
    assert not hasattr(spec, "doors")
    assert not hasattr(spec, "windows")

    # 2. Inspect FloorPlanSpec attributes
    for floor in spec.floors:
        assert not hasattr(floor, "coordinates")
        assert not hasattr(floor, "polygon")
        assert not hasattr(floor, "bounds")
        assert not hasattr(floor, "walls")
        assert not hasattr(floor, "doors")
        assert not hasattr(floor, "windows")

        # 3. Inspect each RoomSpec
        for room in floor.room_specs:
            assert not hasattr(room, "x")
            assert not hasattr(room, "y")
            assert not hasattr(room, "width")
            assert not hasattr(room, "height")
            assert not hasattr(room, "polygon")
            assert not hasattr(room, "geometry")
            assert not hasattr(room, "centroid")

            # Verify fields on RoomSpec are purely program/strategic
            assert isinstance(room.room_type, str)
            assert isinstance(room.room_category, str)
            assert isinstance(room.priority, str)
            assert isinstance(room.target_area_sqm, float)


def test_no_geometric_imports_in_planning_package():
    """Verify app.agents.planning_agent does not import shapely or geometry engine."""
    import sys
    import app.agents.planning_agent

    modules_to_check = [
        "app.agents.planning_agent",
        "app.agents.planning_agent.agent",
        "app.agents.planning_agent.categorizer",
        "app.agents.planning_agent.priority_calculator",
        "app.agents.planning_agent.relationship_graph",
        "app.agents.planning_agent.circulation_planner",
    ]

    for mod_name in modules_to_check:
        mod = sys.modules.get(mod_name)
        assert mod is not None
        # Must not import shapely
        assert "shapely" not in mod.__dict__
        assert "geometry" not in mod.__dict__ or mod_name.endswith("agent") and "geometry" not in str(mod.__dict__.get("geometry", ""))

"""Unit tests for relationship graph construction, symmetry, and attached rooms."""

import pytest
from app.agents.planning_agent import PlanningAgent, RelationshipGraphBuilder
from app.models.requirements import Requirements, FloorRequirement, RoomRequirement
from app.models.planning import RoomSpec


@pytest.fixture
def planner():
    return PlanningAgent()


def test_required_adjacency_preservation(planner):
    f1 = FloorRequirement(
        floor_number=1,
        room_requirements=[
            RoomRequirement(room_type="kitchen", adjacency=["dining"]),
            RoomRequirement(room_type="dining", adjacency=["kitchen"]),
            RoomRequirement(room_type="living"),
        ],
    )
    reqs = Requirements(
        plot_dimensions=(15.0, 20.0),
        target_floors=1,
        floors=[f1],
    )
    spec = planner.plan(reqs)
    adj_mat = spec.floors[0].adjacency_matrix

    assert "dining" in adj_mat["kitchen"]
    assert "kitchen" in adj_mat["dining"]


def test_bidirectional_symmetry(planner):
    f1 = FloorRequirement(
        floor_number=1,
        room_requirements=[
            RoomRequirement(room_type="living"),
            RoomRequirement(room_type="dining"),
            RoomRequirement(room_type="kitchen"),
            RoomRequirement(room_type="foyer"),
        ],
    )
    reqs = Requirements(
        plot_dimensions=(15.0, 20.0),
        target_floors=1,
        floors=[f1],
    )
    spec = planner.plan(reqs)
    adj_mat = spec.floors[0].adjacency_matrix

    # Check that for any pair (u, v), u in adj_mat[v] <=> v in adj_mat[u]
    for u, neighbors in adj_mat.items():
        for v in neighbors:
            assert u in adj_mat[v], f"Asymmetry found: {v} is adjacent to {u}, but {u} is not in {v}'s adjacencies"


def test_avoid_separation_matrix(planner):
    f1 = FloorRequirement(
        floor_number=1,
        room_requirements=[
            RoomRequirement(room_type="bedroom"),
            RoomRequirement(room_type="garage", separation=["bedroom"]),
            RoomRequirement(room_type="living"),
        ],
    )
    reqs = Requirements(
        plot_dimensions=(15.0, 20.0),
        target_floors=1,
        floors=[f1],
    )
    spec = planner.plan(reqs)
    avoid_mat = spec.floors[0].avoid_matrix

    assert "bedroom" in avoid_mat["garage"]
    assert "garage" in avoid_mat["bedroom"]


def test_attached_room_coupling(planner):
    f1 = FloorRequirement(
        floor_number=1,
        room_requirements=[
            RoomRequirement(room_type="master_bedroom"),
            RoomRequirement(room_type="bathroom", attached_to="master_bedroom"),
        ],
    )
    reqs = Requirements(
        plot_dimensions=(15.0, 20.0),
        target_floors=1,
        floors=[f1],
    )
    spec = planner.plan(reqs)
    rooms = {r.room_type: r for r in spec.floors[0].room_specs}

    mbr = rooms["master_bedroom"]
    bath = rooms["bathroom"]

    # Verify parent pointer
    assert bath.attached_to_room_id == mbr.id
    # Verify mutual adjacency
    assert "bathroom" in spec.floors[0].adjacency_matrix["master_bedroom"]
    assert "master_bedroom" in spec.floors[0].adjacency_matrix["bathroom"]


def test_conflict_resolution_avoid_overrides_adjacency():
    """If a pair is both marked as preferred adjacency and avoid, avoid strictly wins."""
    r_specs = [
        RoomSpec(room_type="garage"),
        RoomSpec(room_type="bedroom"),
    ]
    # Explicitly attempt to make garage adjacent to bedroom AND avoid bedroom
    adj, avoid = RelationshipGraphBuilder.build_matrices(
        room_specs=r_specs,
        explicit_adjacencies={"garage": ["bedroom"]},
        explicit_avoids={"garage": ["bedroom"]},
    )
    assert "bedroom" in avoid["garage"]
    assert "bedroom" not in adj["garage"]


def test_no_self_loops():
    r_specs = [
        RoomSpec(room_type="living", adjacency=["living"], avoid=["living"]),
    ]
    adj, avoid = RelationshipGraphBuilder.build_matrices(room_specs=r_specs)
    assert "living" not in adj.get("living", [])
    assert "living" not in avoid.get("living", [])

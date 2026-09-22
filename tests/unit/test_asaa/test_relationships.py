"""Unit tests for ASAA relationship-aware allocation."""

from app.asaa.allocator import ASAAAllocator
from app.asaa.spatial_regions import are_regions_adjacent
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec


def test_required_adjacency_satisfied_by_shared_boundary():
    """Test that rooms with required adjacency share physical boundary contact."""
    allocator = ASAAAllocator(seed=42)

    r_living = RoomSpec(
        room_type="living",
        target_area_sqm=30.0,
        adjacency=["dining"],
        room_category="social",
        priority="high",
    )
    r_dining = RoomSpec(
        room_type="dining",
        target_area_sqm=15.0,
        adjacency=["living"],
        room_category="social",
        priority="normal",
    )
    r_bed = RoomSpec(
        room_type="bedroom",
        target_area_sqm=20.0,
        room_category="private",
    )

    floor = FloorPlanSpec(
        floor_number=1,
        room_specs=[r_living, r_dining, r_bed],
        adjacency_matrix={"living": ["dining"], "dining": ["living"]},
    )

    spec = PlanningSpec(
        floors=[floor],
        global_constraints={"plot_width_m": 12.0, "plot_depth_m": 15.0},
    )

    result = allocator.allocate(spec)
    alloc = result.get_allocation(1)

    living_region = alloc.get_regions_by_type("living")[0]
    dining_region = alloc.get_regions_by_type("dining")[0]

    # Boundary contact check
    is_touching = are_regions_adjacent(living_region.polygon, dining_region.polygon)
    assert is_touching is True
    assert dining_region.id in living_region.adjacency_regions
    assert living_region.id in dining_region.adjacency_regions


def test_attached_room_adjacency():
    """Test that an ensuite attached bathroom shares boundary with master bedroom."""
    allocator = ASAAAllocator(seed=42)

    r_master = RoomSpec(
        room_type="master_bedroom",
        target_area_sqm=25.0,
        room_category="private",
    )
    r_ensuite = RoomSpec(
        room_type="attached_bathroom",
        target_area_sqm=6.0,
        room_category="service",
        attached_to_room_id=r_master.id,
    )
    r_living = RoomSpec(
        room_type="living",
        target_area_sqm=30.0,
        room_category="social",
    )

    floor = FloorPlanSpec(
        floor_number=1,
        room_specs=[r_master, r_ensuite, r_living],
    )
    spec = PlanningSpec(
        floors=[floor],
        global_constraints={"plot_width_m": 12.0, "plot_depth_m": 15.0},
    )

    result = allocator.allocate(spec)
    alloc = result.get_allocation(1)

    master_reg = alloc.get_regions_by_type("master_bedroom")[0]
    ensuite_reg = alloc.get_regions_by_type("attached_bathroom")[0]

    assert are_regions_adjacent(master_reg.polygon, ensuite_reg.polygon) is True
    assert ensuite_reg.id in master_reg.adjacency_regions


def test_avoid_separation_scoring():
    """Test that avoid/separation matrix reduces score if separated rooms are forced to touch."""
    from app.asaa.spatial_partitioner import PartitionItem
    from app.asaa.scoring import CandidateScorer
    from shapely.geometry import Polygon

    # Two adjacent boxes
    p1 = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]
    p2 = [(5.0, 0.0), (10.0, 0.0), (10.0, 5.0), (5.0, 5.0)]

    item_garage = PartitionItem(id="g", room_type="garage", target_area_sqm=25.0, allocated_area_sqm=25.0, polygon=p1)
    item_bed = PartitionItem(id="b", room_type="bedroom", target_area_sqm=25.0, allocated_area_sqm=25.0, polygon=p2)

    buildable = Polygon([(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)])

    floor_spec_avoid = FloorPlanSpec(
        avoid_matrix={"garage": ["bedroom"], "bedroom": ["garage"]}
    )

    _, score_avoid, breakdown_avoid, _ = CandidateScorer.evaluate(
        items=[item_garage, item_bed],
        buildable_polygon=buildable,
        room_specs=[],
        floor_plan_spec=floor_spec_avoid,
    )

    # If avoid pair touches, relationship score is lower
    assert breakdown_avoid["relationship_satisfaction"] < 80.0

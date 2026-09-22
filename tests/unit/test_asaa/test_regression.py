"""Regression tests protecting against historical failure modes."""

import pytest
from shapely.geometry import Polygon
from app.asaa.allocator import ASAAAllocator
from app.asaa.boundary import BuildableBoundaryCalculator
from app.asaa.exceptions import InfeasibleAllocationError
from app.asaa.spatial_regions import are_regions_adjacent
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec


def test_regression_1_no_modulo_grid_stride_placement():
    """Verify that allocation does not place rooms on naive (room_idx % 10) grid offsets."""
    spec = PlanningSpec(
        floors=[
            FloorPlanSpec(
                floor_number=1,
                room_specs=[
                    RoomSpec(room_type="room_1", target_area_sqm=20.0),
                    RoomSpec(room_type="room_2", target_area_sqm=20.0),
                    RoomSpec(room_type="room_3", target_area_sqm=20.0),
                ],
            )
        ],
        global_constraints={"plot_width_m": 12.0, "plot_depth_m": 15.0},
    )
    allocator = ASAAAllocator()
    alloc_set = allocator.allocate(spec)
    regions = alloc_set.get_allocation(1).allocated_regions

    # In modulo grid logic: (0 % 10)*(w+1) was used. In real partitioning, all polygons
    # form a tight, gapless space-filling partition within the boundary.
    total_alloc_area = sum(r.area_sqm for r in regions)
    # The partitioned regions must cover the requested room budget cleanly without stride drift
    assert total_alloc_area >= 60.0
    # Check that none of the regions have coordinates placed outside the 12x15 boundary
    for r in regions:
        for x, y in r.polygon:
            assert 0.0 <= x <= 12.0
            assert 0.0 <= y <= 15.0


def test_regression_2_no_overlapping_room_allocation():
    """Verify that no two allocated regions overlap."""
    spec = PlanningSpec(
        floors=[
            FloorPlanSpec(
                floor_number=1,
                room_specs=[
                    RoomSpec(room_type="living", target_area_sqm=30.0),
                    RoomSpec(room_type="kitchen", target_area_sqm=15.0),
                    RoomSpec(room_type="dining", target_area_sqm=15.0),
                    RoomSpec(room_type="bedroom", target_area_sqm=20.0),
                    RoomSpec(room_type="bathroom", target_area_sqm=8.0),
                ],
            )
        ],
        global_constraints={"plot_width_m": 15.0, "plot_depth_m": 15.0},
    )
    allocator = ASAAAllocator()
    alloc = allocator.allocate(spec).get_allocation(1)
    regions = alloc.allocated_regions

    for i in range(len(regions)):
        pi = Polygon(regions[i].polygon)
        for j in range(i + 1, len(regions)):
            pj = Polygon(regions[j].polygon)
            overlap = pi.intersection(pj).area
            assert overlap < 0.02, f"Regions {regions[i].room_type} and {regions[j].room_type} overlap by {overlap}m²"


def test_regression_3_no_rooms_outside_buildable_boundary():
    """Verify that all room regions are completely within the buildable boundary."""
    spec = PlanningSpec(
        floors=[
            FloorPlanSpec(
                floor_number=1,
                room_specs=[
                    RoomSpec(room_type="living", target_area_sqm=40.0),
                    RoomSpec(room_type="bedroom", target_area_sqm=25.0),
                ],
            )
        ],
        global_constraints={
            "plot_width_m": 15.0,
            "plot_depth_m": 15.0,
            "setbacks": {"all": 2.0},  # Buildable: 11x11 = 121 sqm from (2,2) to (13,13)
        },
    )
    allocator = ASAAAllocator()
    alloc = allocator.allocate(spec).get_allocation(1)
    buildable_box = Polygon([(2.0, 2.0), (13.0, 2.0), (13.0, 13.0), (2.0, 13.0)])

    for r in alloc.allocated_regions:
        poly = Polygon(r.polygon)
        diff = poly.difference(buildable_box).area
        assert diff < 0.02, f"Room {r.room_type} extends outside buildable box by {diff}m²"


def test_regression_4_no_automatic_floor_2_room_invention():
    """Verify that ASAA never invents rooms on Floor 2."""
    spec = PlanningSpec(
        floors=[
            FloorPlanSpec(
                floor_number=1,
                room_specs=[RoomSpec(room_type="living", floor_number=1, target_area_sqm=30.0)],
            ),
            FloorPlanSpec(
                floor_number=2,
                room_specs=[RoomSpec(room_type="office", floor_number=2, target_area_sqm=20.0)],
            ),
        ],
        global_constraints={"plot_width_m": 10.0, "plot_depth_m": 12.0},
    )
    allocator = ASAAAllocator()
    alloc_set = allocator.allocate(spec)

    f2_rooms = [r for r in alloc_set.get_allocation(2).allocated_regions if r.zone_type == "room"]
    assert len(f2_rooms) == 1
    assert f2_rooms[0].room_type == "office"


def test_regression_5_no_movement_of_rooms_between_floors():
    """Verify that ASAA never moves rooms from their assigned floor."""
    spec = PlanningSpec(
        floors=[
            FloorPlanSpec(
                floor_number=1,
                room_specs=[
                    RoomSpec(room_type="kitchen", floor_number=1, target_area_sqm=15.0),
                ],
            ),
            FloorPlanSpec(
                floor_number=2,
                room_specs=[
                    RoomSpec(room_type="master_bedroom", floor_number=2, target_area_sqm=25.0),
                ],
            ),
        ],
        global_constraints={"plot_width_m": 10.0, "plot_depth_m": 12.0},
    )
    allocator = ASAAAllocator()
    alloc_set = allocator.allocate(spec)

    f1_types = [r.room_type for r in alloc_set.get_allocation(1).allocated_regions if r.zone_type == "room"]
    f2_types = [r.room_type for r in alloc_set.get_allocation(2).allocated_regions if r.zone_type == "room"]

    assert "kitchen" in f1_types
    assert "master_bedroom" not in f1_types
    assert "master_bedroom" in f2_types
    assert "kitchen" not in f2_types


def test_regression_6_no_silent_reduction_below_user_minimum_area():
    """Verify that user's explicit min_area_sqm is not silently reduced."""
    spec = PlanningSpec(
        floors=[
            FloorPlanSpec(
                floor_number=1,
                room_specs=[
                    RoomSpec(room_type="dining", target_area_sqm=20.0, min_area_sqm=18.0),
                ],
            )
        ],
        global_constraints={"plot_width_m": 10.0, "plot_depth_m": 10.0},
    )
    allocator = ASAAAllocator()
    alloc = allocator.allocate(spec).get_allocation(1)
    dining = alloc.get_regions_by_type("dining")[0]
    assert dining.area_sqm >= 18.0


def test_regression_7_no_silent_removal_of_requested_rooms():
    """Verify that requested rooms are never dropped."""
    rooms = [
        RoomSpec(room_type=f"room_{i}", target_area_sqm=12.0)
        for i in range(5)
    ]
    spec = PlanningSpec(
        floors=[FloorPlanSpec(floor_number=1, room_specs=rooms)],
        global_constraints={"plot_width_m": 15.0, "plot_depth_m": 15.0},
    )
    allocator = ASAAAllocator()
    alloc = allocator.allocate(spec).get_allocation(1)
    allocated_types = {r.room_type for r in alloc.allocated_regions if r.zone_type == "room"}
    for i in range(5):
        assert f"room_{i}" in allocated_types


def test_regression_8_required_adjacency_evaluated_spatially():
    """Verify that adjacency is evaluated through actual boundary contact, not dummy scores."""
    spec = PlanningSpec(
        floors=[
            FloorPlanSpec(
                floor_number=1,
                room_specs=[
                    RoomSpec(room_type="living", target_area_sqm=30.0, adjacency=["dining"]),
                    RoomSpec(room_type="dining", target_area_sqm=15.0, adjacency=["living"]),
                ],
                adjacency_matrix={"living": ["dining"], "dining": ["living"]},
            )
        ],
        global_constraints={"plot_width_m": 10.0, "plot_depth_m": 12.0},
    )
    allocator = ASAAAllocator()
    alloc = allocator.allocate(spec).get_allocation(1)
    r_living = alloc.get_regions_by_type("living")[0]
    r_dining = alloc.get_regions_by_type("dining")[0]

    assert are_regions_adjacent(r_living.polygon, r_dining.polygon) is True
    assert r_dining.id in r_living.adjacency_regions


def test_regression_9_candidate_scoring_actually_invoked():
    """Verify that candidate scoring is actually invoked and produces non-zero score."""
    spec = PlanningSpec(
        floors=[
            FloorPlanSpec(
                floor_number=1,
                room_specs=[
                    RoomSpec(room_type="living", target_area_sqm=30.0),
                    RoomSpec(room_type="kitchen", target_area_sqm=15.0),
                ],
            )
        ],
        global_constraints={"plot_width_m": 10.0, "plot_depth_m": 12.0},
    )
    allocator = ASAAAllocator()
    alloc = allocator.allocate(spec).get_allocation(1)
    assert alloc.score > 0.0
    for r in alloc.allocated_regions:
        assert r.score > 0.0


def test_regression_10_irregular_polygon_not_replaced_by_bounding_box():
    """Verify that an irregular polygon plot is preserved and not replaced by bounding box."""
    l_coords = [
        (0.0, 0.0),
        (20.0, 0.0),
        (20.0, 10.0),
        (10.0, 10.0),
        (10.0, 20.0),
        (0.0, 20.0),
    ]
    spec = PlanningSpec(
        floors=[
            FloorPlanSpec(
                floor_number=1,
                room_specs=[
                    RoomSpec(room_type="living", target_area_sqm=40.0),
                    RoomSpec(room_type="dining", target_area_sqm=20.0),
                ],
            )
        ],
        global_constraints={"plot_polygon": l_coords},
    )
    allocator = ASAAAllocator()
    alloc = allocator.allocate(spec).get_allocation(1)
    l_poly = Polygon(l_coords)

    for r in alloc.allocated_regions:
        poly = Polygon(r.polygon)
        # Check all regions are completely inside original L-shape
        assert poly.difference(l_poly).area < 0.02

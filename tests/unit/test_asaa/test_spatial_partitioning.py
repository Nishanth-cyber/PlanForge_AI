"""Unit tests for ASAA computational spatial partitioning."""

from shapely.geometry import Polygon
from app.asaa.spatial_partitioner import SpatialPartitioner
from app.models.planning import RoomSpec


def test_rectangular_partitioning_containment_and_non_overlap():
    """Test partitioning on a rectangular plot: zero overlap, 100% containment."""
    buildable_poly = Polygon([(0.0, 0.0), (12.0, 0.0), (12.0, 15.0), (0.0, 15.0)])  # 180 sqm

    rooms = [
        RoomSpec(room_type="living", target_area_sqm=35.0, priority="high", room_category="social"),
        RoomSpec(room_type="kitchen", target_area_sqm=15.0, priority="normal", room_category="service"),
        RoomSpec(room_type="dining", target_area_sqm=15.0, priority="normal", room_category="social"),
        RoomSpec(room_type="master_bedroom", target_area_sqm=25.0, priority="high", room_category="private"),
        RoomSpec(room_type="bedroom", target_area_sqm=18.0, priority="normal", room_category="private"),
        RoomSpec(room_type="bathroom", target_area_sqm=8.0, priority="normal", room_category="service"),
    ]
    budgets = {rs.id: rs.target_area_sqm for rs in rooms}

    items = SpatialPartitioner.partition(
        buildable_polygon=buildable_poly,
        room_specs=rooms,
        room_budgets=budgets,
        circulation_area_sqm=15.0,
        zoning_strategy="front_to_back",
    )

    # 1. Every room item must exist
    room_item_types = [it.room_type for it in items if it.zone_type == "room"]
    assert "living" in room_item_types
    assert "master_bedroom" in room_item_types
    assert "kitchen" in room_item_types
    assert "bathroom" in room_item_types

    # 2. Containment: Every item must be inside buildable boundary
    for it in items:
        poly = Polygon(it.polygon)
        diff = poly.difference(buildable_poly)
        assert diff.area < 0.01, f"Item {it.id} extends outside boundary by {diff.area} m²"

    # 3. Non-Overlap: No two items overlap
    for i in range(len(items)):
        poly_i = Polygon(items[i].polygon)
        for j in range(i + 1, len(items)):
            poly_j = Polygon(items[j].polygon)
            overlap = poly_i.intersection(poly_j).area
            assert overlap < 0.01, f"Items {items[i].id} and {items[j].id} overlap by {overlap} m²"


def test_l_shaped_partitioning_containment_and_non_overlap():
    """Test partitioning on an L-shaped plot without fallback to bounding box."""
    l_coords = [
        (0.0, 0.0),
        (20.0, 0.0),
        (20.0, 10.0),
        (10.0, 10.0),
        (10.0, 20.0),
        (0.0, 20.0),
    ]
    buildable_poly = Polygon(l_coords)  # 300 sqm

    rooms = [
        RoomSpec(room_type="living", target_area_sqm=40.0, room_category="social"),
        RoomSpec(room_type="dining", target_area_sqm=20.0, room_category="social"),
        RoomSpec(room_type="kitchen", target_area_sqm=18.0, room_category="service"),
        RoomSpec(room_type="bedroom_1", target_area_sqm=25.0, room_category="private"),
        RoomSpec(room_type="bedroom_2", target_area_sqm=20.0, room_category="private"),
    ]
    budgets = {rs.id: rs.target_area_sqm for rs in rooms}

    items = SpatialPartitioner.partition(
        buildable_polygon=buildable_poly,
        room_specs=rooms,
        room_budgets=budgets,
        circulation_area_sqm=20.0,
    )

    # Every item must be strictly within the L-shaped polygon
    for it in items:
        poly = Polygon(it.polygon)
        assert poly.difference(buildable_poly).area < 0.02
        assert poly.area > 0.0

    # Zero overlap
    for i in range(len(items)):
        poly_i = Polygon(items[i].polygon)
        for j in range(i + 1, len(items)):
            poly_j = Polygon(items[j].polygon)
            assert poly_i.intersection(poly_j).area < 0.02


def test_staircase_carve_out():
    """Test that staircase zone is carved out with correct zone_type and area."""
    buildable_poly = Polygon([(0.0, 0.0), (10.0, 0.0), (10.0, 15.0), (0.0, 15.0)])
    rooms = [RoomSpec(room_type="living", target_area_sqm=30.0)]
    budgets = {rs.id: rs.target_area_sqm for rs in rooms}

    items = SpatialPartitioner.partition(
        buildable_polygon=buildable_poly,
        room_specs=rooms,
        room_budgets=budgets,
        has_staircase=True,
        staircase_area_sqm=8.0,
    )

    staircase_items = [it for it in items if it.zone_type == "staircase"]
    assert len(staircase_items) == 1
    assert staircase_items[0].room_type == "staircase"
    assert staircase_items[0].allocated_area_sqm >= 6.0

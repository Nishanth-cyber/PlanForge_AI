"""Unit tests for ASAA Allocation data contracts."""

from app.models.allocation import AllocatedRegion, Allocation, AllocationSet


def test_allocated_region_creation():
    """Test AllocatedRegion creation with spatial polygon, centroid, and zone type."""
    region = AllocatedRegion(
        room_type="living",
        floor_number=1,
        target_area_sqm=20.0,
        area_sqm=19.8,
        approximate_dimensions=(4.0, 5.0),
        polygon=[(0.0, 0.0), (4.0, 0.0), (4.0, 5.0), (0.0, 5.0)],
        centroid=(2.0, 2.5),
        priority="high",
        adjacency_regions=["region_dining_01"],
        zone_type="room",
        score=95.0,
    )
    assert region.id is not None
    assert region.approximate_dimensions == (4.0, 5.0)
    assert region.centroid == (2.0, 2.5)
    assert region.zone_type == "room"
    assert "region_dining_01" in region.adjacency_regions


def test_allocation_single_floor_helpers():
    """Test Allocation zone queries for circulation, staircase, and entrance."""
    r_living = AllocatedRegion(room_type="living", zone_type="room", area_sqm=20.0)
    r_corridor = AllocatedRegion(room_type="corridor", zone_type="circulation", area_sqm=8.0)
    r_stairs = AllocatedRegion(room_type="staircase", zone_type="staircase", area_sqm=6.0)
    r_entrance = AllocatedRegion(room_type="foyer", zone_type="entrance", area_sqm=4.0)

    alloc = Allocation(
        floor_number=1,
        floor_name="Ground Floor",
        total_area_sqm=38.0,
        allocated_regions=[r_living, r_corridor, r_stairs, r_entrance],
        circulation_area_sqm=8.0,
        score=90.0,
    )

    assert alloc.get_region_by_id(r_living.id) == r_living
    assert len(alloc.get_regions_by_type("living")) == 1
    assert len(alloc.get_circulation_regions()) == 1
    assert alloc.get_circulation_regions()[0] == r_corridor
    assert alloc.get_staircase_region() == r_stairs
    assert alloc.get_entrance_region() == r_entrance


def test_allocation_set_multi_floor():
    """Test AllocationSet across floors with total score and staircase alignment flag."""
    a1 = Allocation(floor_number=1, score=90.0)
    a2 = Allocation(floor_number=2, score=80.0)

    alloc_set = AllocationSet(
        allocations=[a1, a2],
        staircase_aligned=True,
    )

    assert alloc_set.get_allocation(1) == a1
    assert alloc_set.get_allocation(2) == a2
    assert alloc_set.get_allocation(3) is None
    assert alloc_set.staircase_aligned is True
    assert alloc_set.total_score() == 85.0

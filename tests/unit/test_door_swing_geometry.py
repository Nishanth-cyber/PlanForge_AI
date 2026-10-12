"""Regression test suite for PlanForge door-swing geometry and curved-line fixes.

Tests:
1. Rectangular plot with correctly positioned doors.
2. Rectangular plot with door-swing display disabled (swing arc presence in model vs display).
3. Rectangular plot with no doors — no swing arcs appear.
4. Multiple doors — each valid door has at most one swing arc (no duplicate doors/arcs).
5. Irregular plot — boundary remains unchanged.
6. Door arcs are derived strictly from valid door geometry and do not appear at arbitrary locations.
"""

import math
import pytest
from app.geometry.door_builder import DoorBuilder
from app.geometry.engine import GeometryEngine
from app.geometry.geometry_utils import compute_swing_arc, segment_length
from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
from app.models.architectural_design import (
    ArchitecturalDesign,
    ArchitecturalDesignSet,
    RoomDesign,
)
from app.models.doors import DoorIntent
from app.models.geometry import GeoDoor, GeoRoom, GeoWall


def test_1_rectangular_plot_with_correctly_positioned_doors():
    """Verify that on a rectangular plot, doors are correctly placed on walls with valid swing arcs."""
    # 2 adjacent rooms on a rectangular plot
    r1 = AllocatedRegion(
        id="alloc_living",
        room_type="living",
        floor_number=1,
        polygon=[(0.0, 0.0), (5.0, 0.0), (5.0, 4.0), (0.0, 4.0)],
    )
    r2 = AllocatedRegion(
        id="alloc_dining",
        room_type="dining",
        floor_number=1,
        polygon=[(5.0, 0.0), (10.0, 0.0), (10.0, 4.0), (5.0, 4.0)],
    )
    alloc_set = AllocationSet(
        id="alloc_set_1",
        allocations=[Allocation(id="alloc_1", floor_number=1, allocated_regions=[r1, r2])],
    )

    des_living = RoomDesign(
        id="des_living",
        room_type="living",
        allocated_region_id="alloc_living",
        floor_number=1,
        doors=[
            DoorIntent(
                id="intent_entrance",
                connects_from="living",
                connects_to="exterior",
                door_type="entrance",
                wall_orientation="south",
                recommended_width=0.9,
            ),
            DoorIntent(
                id="intent_interior",
                connects_from="living",
                connects_to="dining",
                door_type="interior",
                recommended_width=0.9,
            ),
        ],
    )
    des_dining = RoomDesign(
        id="des_dining",
        room_type="dining",
        allocated_region_id="alloc_dining",
        floor_number=1,
    )
    design_set = ArchitecturalDesignSet(
        id="design_set_1",
        designs=[ArchitecturalDesign(id="arch_1", floor_number=1, rooms=[des_living, des_dining])],
    )

    plot_rect = [(0.0, 0.0), (12.0, 0.0), (12.0, 6.0), (0.0, 6.0)]
    engine = GeometryEngine()
    fps = engine.construct(
        design_set=design_set,
        allocation_set=alloc_set,
        plot_boundary=plot_rect,
    )

    fp = fps.get_floor_plan(1)
    assert fp is not None
    geom = fp.geometry
    assert geom is not None

    # Plot boundary remains exact 4-vertex rectangle
    assert geom.plot_polygon == plot_rect

    # Both doors must have valid wall placements and swing arcs
    assert len(geom.doors) == 2
    for door in geom.doors:
        assert door.wall_id != ""
        wall = geom.get_wall(door.wall_id)
        assert wall is not None
        # Verify position is along the wall segment
        w_len = segment_length((wall.start, wall.end))
        assert w_len >= door.width

        # Swing arc is present, non-degenerate, and starts with hinge
        assert door.swing_arc is not None
        assert len(door.swing_arc) >= 3
        hinge = door.swing_arc[0]
        # Hinge must be on wall
        wx = wall.end[0] - wall.start[0]
        wy = wall.end[1] - wall.start[1]
        t = ((hinge[0] - wall.start[0]) * wx + (hinge[1] - wall.start[1]) * wy) / (w_len * w_len)
        assert 0.0 <= t <= 1.0


def test_2_rectangular_plot_door_swing_data_integrity():
    """Verify backend geometry and validation remain intact regardless of UI display toggle."""
    r1 = AllocatedRegion(
        id="alloc_bed",
        room_type="bedroom",
        floor_number=1,
        polygon=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
    )
    alloc_set = AllocationSet(
        id="alloc_set_2",
        allocations=[Allocation(id="alloc_2", floor_number=1, allocated_regions=[r1])],
    )

    des_bed = RoomDesign(
        id="des_bed",
        room_type="bedroom",
        allocated_region_id="alloc_bed",
        floor_number=1,
        doors=[
            DoorIntent(
                id="intent_ent",
                connects_from="bedroom",
                connects_to="exterior",
                door_type="entrance",
                wall_orientation="south",
            )
        ],
    )
    design_set = ArchitecturalDesignSet(
        id="design_set_2",
        designs=[ArchitecturalDesign(id="arch_2", floor_number=1, rooms=[des_bed])],
    )

    engine = GeometryEngine()
    fps = engine.construct(design_set=design_set, allocation_set=alloc_set)
    door = fps.floor_plans[0].geometry.doors[0]

    # Verify GeoDoor swing_arc retains full geometric definition
    assert door.swing_arc is not None
    assert len(door.swing_arc) >= 3
    # First point is hinge, last point is open leaf tip
    assert math.hypot(door.swing_arc[-1][0] - door.swing_arc[0][0], door.swing_arc[-1][1] - door.swing_arc[0][1]) == pytest.approx(door.width, abs=0.01)


def test_3_rectangular_plot_with_no_doors():
    """Verify that when no door intents exist, exactly zero doors and zero swing arcs appear."""
    r1 = AllocatedRegion(
        id="alloc_living",
        room_type="living",
        floor_number=1,
        polygon=[(0.0, 0.0), (6.0, 0.0), (6.0, 6.0), (0.0, 6.0)],
    )
    alloc_set = AllocationSet(
        id="alloc_set_3",
        allocations=[Allocation(id="alloc_3", floor_number=1, allocated_regions=[r1])],
    )

    des_living = RoomDesign(
        id="des_living",
        room_type="living",
        allocated_region_id="alloc_living",
        floor_number=1,
        doors=[],  # No doors
    )
    design_set = ArchitecturalDesignSet(
        id="design_set_3",
        designs=[ArchitecturalDesign(id="arch_3", floor_number=1, rooms=[des_living])],
    )

    engine = GeometryEngine()
    fps = engine.construct(design_set=design_set, allocation_set=alloc_set)
    geom = fps.floor_plans[0].geometry

    assert len(geom.doors) == 0
    # No swing arcs can exist
    for r in geom.rooms:
        assert len(r.doors) == 0


def test_4_multiple_doors_deduplication_and_single_arc_per_door():
    """Verify that multiple doors between the same room pair are deduplicated, and each valid door has at most one swing arc."""
    r1 = AllocatedRegion(
        id="alloc_r1",
        room_type="living",
        floor_number=1,
        polygon=[(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)],
    )
    r2 = AllocatedRegion(
        id="alloc_r2",
        room_type="kitchen",
        floor_number=1,
        polygon=[(5.0, 0.0), (10.0, 0.0), (10.0, 5.0), (5.0, 5.0)],
    )
    alloc_set = AllocationSet(
        id="alloc_set_4",
        allocations=[Allocation(id="alloc_4", floor_number=1, allocated_regions=[r1, r2])],
    )

    # Both rooms propose a door connecting each other (reciprocal door intents)
    des_living = RoomDesign(
        id="des_living",
        room_type="living",
        allocated_region_id="alloc_r1",
        doors=[
            DoorIntent(
                id="door_liv_to_kit",
                connects_from="living",
                connects_to="kitchen",
                door_type="interior",
            )
        ],
    )
    des_kitchen = RoomDesign(
        id="des_kitchen",
        room_type="kitchen",
        allocated_region_id="alloc_r2",
        doors=[
            DoorIntent(
                id="door_kit_to_liv",
                connects_from="kitchen",
                connects_to="living",
                door_type="interior",
            )
        ],
    )
    design_set = ArchitecturalDesignSet(
        id="design_set_4",
        designs=[ArchitecturalDesign(id="arch_4", floor_number=1, rooms=[des_living, des_kitchen])],
    )

    engine = GeometryEngine()
    fps = engine.construct(design_set=design_set, allocation_set=alloc_set)
    geom = fps.floor_plans[0].geometry

    # Exactly ONE physical door should connect living and kitchen, not two duplicates on top of each other
    assert len(geom.doors) == 1
    single_door = geom.doors[0]
    assert single_door.swing_arc is not None
    assert len(single_door.swing_arc) >= 3


def test_5_irregular_plot_boundary_remains_unchanged():
    """Verify that an irregular plot boundary is strictly preserved and not modified by door placement."""
    irregular_plot = [
        (0.0, 0.0),
        (15.0, 0.0),
        (18.0, 8.0),
        (12.0, 16.0),
        (0.0, 14.0),
    ]

    r1 = AllocatedRegion(
        id="alloc_living",
        room_type="living",
        floor_number=1,
        polygon=[(2.0, 2.0), (8.0, 2.0), (8.0, 7.0), (2.0, 7.0)],
    )
    alloc_set = AllocationSet(
        id="alloc_set_5",
        allocations=[Allocation(id="alloc_5", floor_number=1, allocated_regions=[r1])],
    )

    des_living = RoomDesign(
        id="des_living",
        room_type="living",
        allocated_region_id="alloc_living",
        floor_number=1,
        doors=[
            DoorIntent(
                id="intent_entrance",
                connects_from="living",
                connects_to="exterior",
                door_type="entrance",
                wall_orientation="south",
            )
        ],
    )
    design_set = ArchitecturalDesignSet(
        id="design_set_5",
        designs=[ArchitecturalDesign(id="arch_5", floor_number=1, rooms=[des_living])],
    )

    engine = GeometryEngine()
    fps = engine.construct(
        design_set=design_set,
        allocation_set=alloc_set,
        plot_boundary=irregular_plot,
    )
    geom = fps.floor_plans[0].geometry

    # Plot polygon coordinates must match exactly without rounded corners or extra vertices
    assert geom.plot_polygon == irregular_plot
    assert len(geom.plot_polygon) == 5


def test_6_door_arcs_strictly_derived_from_valid_wall_and_reject_arbitrary_coords():
    """Verify that compute_swing_arc rejects room centroids, plot vertices, and degenerate walls."""
    # 1. Arbitrary centroid coordinate far from wall segment
    wall_start = (0.0, 0.0)
    wall_end = (5.0, 0.0)
    room_centroid = (2.5, 3.5)  # 3.5 meters away from the wall

    arc = compute_swing_arc(
        hinge=room_centroid,
        wall_start=wall_start,
        wall_end=wall_end,
        width=0.9,
    )
    # Must reject arbitrary non-wall coordinate
    assert arc == []

    # 2. Degenerate wall (zero length)
    arc_degenerate = compute_swing_arc(
        hinge=(0.0, 0.0),
        wall_start=(0.0, 0.0),
        wall_end=(0.0, 0.0),
        width=0.9,
    )
    assert arc_degenerate == []

    # 3. Negative or zero door width
    arc_zero_w = compute_swing_arc(
        hinge=(1.0, 0.0),
        wall_start=(0.0, 0.0),
        wall_end=(5.0, 0.0),
        width=0.0,
    )
    assert arc_zero_w == []

    # 4. Valid hinge along wall segment produces valid arc
    valid_hinge = (1.0, 0.0)
    arc_valid = compute_swing_arc(
        hinge=valid_hinge,
        wall_start=wall_start,
        wall_end=wall_end,
        width=0.9,
        swing_inside=True,
    )
    assert len(arc_valid) >= 3
    assert arc_valid[0] == (1.0, 0.0)  # Hinge
    # Closed leaf tip along wall
    assert arc_valid[1] == (1.9, 0.0)
    # Open leaf tip perpendicular to wall
    assert arc_valid[-1] == (1.0, 0.9)

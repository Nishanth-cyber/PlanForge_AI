"""Unit tests for RoomValidator: completeness, ASAA allocation containment, and topology."""

import pytest
from app.models.allocation import AllocatedRegion, Allocation
from app.models.architectural_design import ArchitecturalDesign, RoomDesign
from app.models.geometry import Geometry, GeoRoom
from app.models.planning import FloorPlanSpec, RoomSpec
from app.models.requirements import FloorRequirements, RoomRequirement
from app.validation.room_validator import RoomValidator


def test_missing_room_detected():
    """Verify error when a required room is missing from geometry."""
    # Requirement wants living, dining, kitchen
    reqs = FloorRequirements(
        floor_number=1,
        room_requirements=[
            RoomRequirement(room_type="living"),
            RoomRequirement(room_type="dining"),
            RoomRequirement(room_type="kitchen"),
        ],
    )

    # Geometry only has living and dining (kitchen is missing)
    geom = Geometry(
        floor_number=1,
        rooms=[
            GeoRoom(id="r1", room_type="living", built_polygon=[(0, 0), (4, 0), (4, 4), (0, 4)], usable_polygon=[(0.1, 0.1), (3.9, 0.1), (3.9, 3.9), (0.1, 3.9)], area_sqm=14.0),
            GeoRoom(id="r2", room_type="dining", built_polygon=[(4, 0), (8, 0), (8, 4), (4, 4)], usable_polygon=[(4.1, 0.1), (7.9, 0.1), (7.9, 3.9), (4.1, 3.9)], area_sqm=14.0),
        ],
    )

    val = RoomValidator()
    issues = val.validate_floor(geometry=geom, floor_reqs=reqs)

    assert any(i.check == "missing_room" and "kitchen" in i.message for i in issues)


def test_invented_room_detected():
    """Verify error when an unexpected room is invented in geometry."""
    reqs = FloorRequirements(
        floor_number=1,
        room_requirements=[
            RoomRequirement(room_type="living"),
        ],
    )

    geom = Geometry(
        floor_number=1,
        rooms=[
            GeoRoom(id="r1", room_type="living", built_polygon=[(0, 0), (4, 0), (4, 4), (0, 4)], usable_polygon=[(0.1, 0.1), (3.9, 0.1), (3.9, 3.9), (0.1, 3.9)], area_sqm=14.0),
            GeoRoom(id="r2", room_type="cinema_hall", built_polygon=[(4, 0), (8, 0), (8, 4), (4, 4)], usable_polygon=[(4.1, 0.1), (7.9, 0.1), (7.9, 3.9), (4.1, 3.9)], area_sqm=14.0),
        ],
    )

    val = RoomValidator()
    issues = val.validate_floor(geometry=geom, floor_reqs=reqs)

    assert any(i.check == "invented_room" and "cinema_hall" in i.message for i in issues)


def test_wrong_floor_assignment():
    """Verify error when a room's floor_number does not match its floor."""
    geom = Geometry(
        floor_number=1,
        rooms=[
            GeoRoom(id="r1", room_type="living", floor_number=2, built_polygon=[(0, 0), (4, 0), (4, 4), (0, 4)], usable_polygon=[(0.1, 0.1), (3.9, 0.1), (3.9, 3.9), (0.1, 3.9)], area_sqm=14.0),
        ],
    )

    val = RoomValidator()
    issues = val.validate_floor(geometry=geom)

    assert any(i.check == "wrong_floor_assignment" for i in issues)


def test_room_outside_asaa_allocation():
    """Verify error when room extends outside its assigned ASAA allocated region."""
    # ASAA allocated region is (0..4, 0..4)
    alloc_reg = AllocatedRegion(
        id="reg_liv",
        room_type="living",
        floor_number=1,
        polygon=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
    )
    alloc = Allocation(floor_number=1, allocated_regions=[alloc_reg])

    arch_design = ArchitecturalDesign(
        floor_number=1,
        rooms=[RoomDesign(id="des_liv", room_type="living", allocated_region_id="reg_liv")],
    )

    # Room was shifted to (2..7, 0..4) -> spills outside region
    geom = Geometry(
        floor_number=1,
        rooms=[
            GeoRoom(
                id="r_spill",
                room_type="living",
                architectural_room_id="des_liv",
                built_polygon=[(2.0, 0.0), (7.0, 0.0), (7.0, 4.0), (2.0, 4.0)],
                usable_polygon=[(2.1, 0.1), (6.9, 0.1), (6.9, 3.9), (2.1, 3.9)],
                area_sqm=18.0,
            )
        ],
    )

    val = RoomValidator()
    issues = val.validate_floor(geometry=geom, allocation=alloc, floor_design=arch_design)

    assert any(i.check == "allocation_containment" for i in issues)


def test_broken_traceability_detected():
    """Verify error when room has no architectural_room_id reference."""
    alloc_reg = AllocatedRegion(id="reg_1", room_type="bedroom", polygon=[(0, 0), (4, 0), (4, 4), (0, 4)])
    alloc = Allocation(floor_number=1, allocated_regions=[alloc_reg])
    arch_design = ArchitecturalDesign(floor_number=1, rooms=[RoomDesign(id="des_1", room_type="bedroom")])

    geom = Geometry(
        floor_number=1,
        rooms=[
            GeoRoom(
                id="r_no_ref",
                room_type="bedroom",
                architectural_room_id=None,  # Missing!
                built_polygon=[(0, 0), (4, 0), (4, 4), (0, 4)],
                usable_polygon=[(0.1, 0.1), (3.9, 0.1), (3.9, 3.9), (0.1, 3.9)],
                area_sqm=14.0,
            )
        ],
    )

    val = RoomValidator()
    issues = val.validate_floor(geometry=geom, allocation=alloc, floor_design=arch_design)

    assert any(i.check == "missing_architectural_reference" for i in issues)

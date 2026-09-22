"""Serialization/deserialization round-trip tests for Phase-1 data contracts.

All Phase-1 models are Python dataclasses.  These tests verify that every model
can be converted to a plain-dict representation (via dataclasses.asdict) and
that the dict round-trips back to the original object structure without data
loss.  No external serialization libraries are required.
"""

import json
from dataclasses import asdict
from datetime import datetime

from app.models.requirements import RoomRequirement, FloorRequirement, Requirements
from app.models.planning import RoomSpec, FloorPlanSpec, PlanningSpec
from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
from app.models.doors import DoorIntent
from app.models.windows import WindowIntent
from app.models.staircase import StaircaseIntent
from app.models.architectural_design import RoomDesign, ArchitecturalDesign, ArchitecturalDesignSet
from app.models.geometry import GeoRoom, GeoWall, GeoDoor, GeoWindow, GeoStaircase, Geometry, GeometrySet
from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.models.validation import ValidationIssue, ValidationResult, ValidationReport
from app.models.events import Event, EventLog


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _to_json_and_back(obj) -> dict:
    """Serialise a dataclass to dict then JSON-encode/decode for round-trip."""
    d = asdict(obj)
    # Verify JSON-safe (raises if any non-serializable field leaks in)
    # datetime is not JSON-natively serialisable; convert manually.
    json_str = json.dumps(d, default=str)
    return json.loads(json_str)


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------

def test_room_requirement_serialization():
    """RoomRequirement serialises to a dict with all key fields preserved."""
    req = RoomRequirement(
        room_type="master_bedroom",
        min_count=1,
        preferred_area_sqm=20.0,
        adjacency=["walk_in_closet"],
        separation=["garage"],
        source="user",
    )
    d = _to_json_and_back(req)
    assert d["room_type"] == "master_bedroom"
    assert d["preferred_area_sqm"] == 20.0
    assert d["adjacency"] == ["walk_in_closet"]
    assert d["separation"] == ["garage"]
    assert d["source"] == "user"
    assert "id" in d


def test_requirements_full_serialization():
    """Requirements with nested FloorRequirement/RoomRequirement serialises correctly."""
    rr = RoomRequirement(room_type="bedroom", min_count=2, min_area_sqm=12.0)
    fr = FloorRequirement(floor_number=1, room_requirements=[rr])
    reqs = Requirements(
        project_name="Test Villa",
        plot_area_sqm=200.0,
        plot_dimensions=(10.0, 20.0),
        setbacks={"front": 3.0},
        orientation="north",
        floors=[fr],
    )
    d = _to_json_and_back(reqs)
    assert d["project_name"] == "Test Villa"
    assert d["plot_area_sqm"] == 200.0
    assert len(d["floors"]) == 1
    floor_d = d["floors"][0]
    assert floor_d["floor_number"] == 1
    assert len(floor_d["room_requirements"]) == 1
    room_d = floor_d["room_requirements"][0]
    assert room_d["room_type"] == "bedroom"
    assert room_d["min_count"] == 2


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def test_room_spec_serialization():
    """RoomSpec serialises and preserves all scheduling fields."""
    spec = RoomSpec(
        room_type="kitchen",
        room_category="service",
        floor_number=1,
        target_area_sqm=14.0,
        priority="high",
        adjacency=["dining"],
        avoid=["bedroom"],
    )
    d = _to_json_and_back(spec)
    assert d["room_type"] == "kitchen"
    assert d["room_category"] == "service"
    assert d["priority"] == "high"
    assert d["adjacency"] == ["dining"]


def test_planning_spec_serialization():
    """PlanningSpec with nested floors and room specs serialises correctly."""
    r = RoomSpec(room_type="living", target_area_sqm=25.0)
    f = FloorPlanSpec(floor_number=1, room_specs=[r])
    plan = PlanningSpec(project_name="Serialization Test", floors=[f])
    d = _to_json_and_back(plan)
    assert d["project_name"] == "Serialization Test"
    assert len(d["floors"]) == 1
    assert len(d["floors"][0]["room_specs"]) == 1


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------

def test_allocated_region_serialization():
    """AllocatedRegion serialises spatial fields including polygon and centroid."""
    region = AllocatedRegion(
        room_type="living",
        floor_number=1,
        area_sqm=20.0,
        polygon=[(0.0, 0.0), (4.0, 0.0), (4.0, 5.0), (0.0, 5.0)],
        centroid=(2.0, 2.5),
        zone_type="room",
    )
    d = _to_json_and_back(region)
    assert d["room_type"] == "living"
    assert d["area_sqm"] == 20.0
    assert d["centroid"] == [2.0, 2.5]  # tuples become lists after JSON round-trip
    assert len(d["polygon"]) == 4


def test_allocation_set_serialization():
    """AllocationSet with multi-floor allocations serialises correctly."""
    r1 = AllocatedRegion(room_type="bedroom")
    a1 = Allocation(floor_number=1, allocated_regions=[r1], score=85.0)
    a2 = Allocation(floor_number=2, score=75.0)
    aset = AllocationSet(allocations=[a1, a2], staircase_aligned=True)
    d = _to_json_and_back(aset)
    assert len(d["allocations"]) == 2
    assert d["staircase_aligned"] is True
    assert d["allocations"][0]["floor_number"] == 1
    assert len(d["allocations"][0]["allocated_regions"]) == 1


# ---------------------------------------------------------------------------
# Architectural Intent (Doors / Windows / Stairs)
# ---------------------------------------------------------------------------

def test_door_intent_serialization():
    """DoorIntent serialises with connection and dimension fields intact."""
    door = DoorIntent(
        connects_from="living",
        connects_to="dining",
        wall_orientation="north",
        door_type="interior",
        recommended_width=0.9,
        floor_number=1,
    )
    d = _to_json_and_back(door)
    assert d["connects_from"] == "living"
    assert d["connects_to"] == "dining"
    assert d["wall_orientation"] == "north"
    assert d["recommended_width"] == 0.9


def test_window_intent_serialization():
    """WindowIntent serialises with room, orientation, and sill height fields."""
    win = WindowIntent(
        room_id="bedroom_01",
        wall_orientation="east",
        window_type="standard",
        sill_height=0.9,
    )
    d = _to_json_and_back(win)
    assert d["room_id"] == "bedroom_01"
    assert d["wall_orientation"] == "east"
    assert d["sill_height"] == 0.9


def test_staircase_intent_serialization():
    """StaircaseIntent serialises with from/to floor and stair type fields."""
    stair = StaircaseIntent(
        from_floor=1,
        to_floor=2,
        stair_type="l_shaped",
        recommended_width=1.1,
        connects_to_rooms=["hallway"],
    )
    d = _to_json_and_back(stair)
    assert d["from_floor"] == 1
    assert d["to_floor"] == 2
    assert d["stair_type"] == "l_shaped"
    assert d["connects_to_rooms"] == ["hallway"]


# ---------------------------------------------------------------------------
# Architectural Design
# ---------------------------------------------------------------------------

def test_room_design_serialization():
    """RoomDesign serialises nested DoorIntent and WindowIntent correctly."""
    door = DoorIntent(connects_from="bedroom", connects_to="hallway")
    win = WindowIntent(room_id="bedroom", wall_orientation="south")
    room = RoomDesign(
        room_type="bedroom",
        intended_dimensions=(3.5, 4.0),
        intended_area_sqm=14.0,
        doors=[door],
        windows=[win],
    )
    d = _to_json_and_back(room)
    assert d["room_type"] == "bedroom"
    assert d["intended_area_sqm"] == 14.0
    assert len(d["doors"]) == 1
    assert len(d["windows"]) == 1
    assert d["doors"][0]["connects_from"] == "bedroom"


def test_architectural_design_set_serialization():
    """ArchitecturalDesignSet with two floors serialises correctly."""
    r1 = RoomDesign(room_type="living")
    r2 = RoomDesign(room_type="bedroom")
    d1 = ArchitecturalDesign(floor_number=1, rooms=[r1])
    d2 = ArchitecturalDesign(floor_number=2, rooms=[r2])
    ads = ArchitecturalDesignSet(designs=[d1, d2])
    d = _to_json_and_back(ads)
    assert len(d["designs"]) == 2
    assert d["designs"][0]["floor_number"] == 1
    assert d["designs"][1]["floor_number"] == 2


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def test_geo_room_serialization():
    """GeoRoom serialises dual polygon fields without data loss."""
    room = GeoRoom(
        room_type="living",
        usable_polygon=[(0.2, 0.2), (3.8, 0.2), (3.8, 3.8), (0.2, 3.8)],
        built_polygon=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
        area_sqm=12.96,
    )
    d = _to_json_and_back(room)
    assert d["room_type"] == "living"
    assert d["area_sqm"] == 12.96
    assert len(d["usable_polygon"]) == 4
    assert len(d["built_polygon"]) == 4


def test_geometry_set_serialization():
    """GeometrySet with nested Geometry and GeoRoom serialises correctly."""
    room = GeoRoom(room_type="kitchen", area_sqm=14.0)
    geom = Geometry(floor_number=1, rooms=[room])
    gset = GeometrySet(geometries=[geom])
    d = _to_json_and_back(gset)
    assert len(d["geometries"]) == 1
    assert d["geometries"][0]["floor_number"] == 1
    assert d["geometries"][0]["rooms"][0]["room_type"] == "kitchen"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_validation_result_serialization():
    """ValidationResult serialises issues, check lists, and validity flag."""
    val = ValidationResult(floor_number=1, is_valid=True, score=90.0)
    val.add_issue(ValidationIssue(severity="warning", category="dimension", message="Low clearance"))
    val.record_passed_check("boundary")
    d = _to_json_and_back(val)
    assert d["floor_number"] == 1
    assert d["is_valid"] is True
    assert d["score"] == 90.0
    assert len(d["issues"]) == 1
    assert d["issues"][0]["severity"] == "warning"
    assert "boundary" in d["checks_passed"]
    assert "dimension" in d["checks_warned"]


def test_validation_report_serialization():
    """ValidationReport with multiple floor results serialises correctly."""
    v1 = ValidationResult(floor_number=1, score=95.0)
    v2 = ValidationResult(floor_number=2, score=80.0)
    report = ValidationReport(results=[v1, v2], iteration=1)
    d = _to_json_and_back(report)
    assert len(d["results"]) == 2
    assert d["iteration"] == 1
    assert d["results"][0]["score"] == 95.0


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

def test_event_serialization():
    """Event serialises stage, type, data payload, and execution time."""
    event = Event(
        stage="asaa",
        event_type="REGIONS_ALLOCATED",
        message="Allocated 3 regions",
        data={"floor": 1, "count": 3},
        execution_time_ms=55.2,
    )
    d = _to_json_and_back(event)
    assert d["stage"] == "asaa"
    assert d["event_type"] == "REGIONS_ALLOCATED"
    assert d["data"]["count"] == 3
    assert d["execution_time_ms"] == 55.2


def test_event_log_serialization():
    """EventLog with multiple events serialises correctly."""
    log = EventLog()
    log.add_event("REQUIREMENTS_PARSED", "requirement", "Parsed user brief")
    log.add_event("REGIONS_ALLOCATED", "asaa", "Allocated floor 1")
    d = _to_json_and_back(log)
    assert len(d["events"]) == 2
    assert d["events"][0]["event_type"] == "REQUIREMENTS_PARSED"
    assert d["events"][1]["stage"] == "asaa"


# ---------------------------------------------------------------------------
# Floor Plan
# ---------------------------------------------------------------------------

def test_floor_plan_set_serialization():
    """FloorPlanSet serialises plot boundaries, floors, and generation metadata."""
    g = Geometry(floor_number=1, rooms=[GeoRoom(room_type="studio", area_sqm=35.0)])
    v = ValidationResult(floor_number=1, is_valid=True)
    fp = FloorPlan(floor_number=1, geometry=g, validation=v, is_valid=True)
    fps = FloorPlanSet(
        project_name="Serialization Project",
        plot_boundary=[(0.0, 0.0), (10.0, 0.0), (10.0, 15.0), (0.0, 15.0)],
        floor_plans=[fp],
        generation_metadata={"version": "1.0"},
    )
    d = _to_json_and_back(fps)
    assert d["project_name"] == "Serialization Project"
    assert len(d["plot_boundary"]) == 4
    assert len(d["floor_plans"]) == 1
    assert d["generation_metadata"]["version"] == "1.0"

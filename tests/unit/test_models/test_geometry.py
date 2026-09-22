"""Unit tests for deterministic Geometry data contracts."""

from app.models.geometry import (
    GeoWall,
    GeoDoor,
    GeoWindow,
    GeoStaircase,
    GeoRoom,
    Geometry,
    GeometrySet,
)


def test_geo_wall():
    """Test GeoWall attributes and footprint polygon."""
    wall = GeoWall(
        start=(0.0, 0.0),
        end=(5.0, 0.0),
        thickness=0.2,
        height=3.0,
        type="exterior",
        polygon=[(0.0, -0.1), (5.0, -0.1), (5.0, 0.1), (0.0, 0.1)],
        room_ids=["room_01"],
    )
    assert wall.id is not None
    assert wall.thickness == 0.2
    assert len(wall.polygon) == 4
    assert wall.type == "exterior"


def test_geo_door_with_swing_arc():
    """Test GeoDoor with swing arc coordinates and intent linkage."""
    door = GeoDoor(
        wall_id="wall_01",
        position=(2.5, 0.0),
        width=0.9,
        height=2.1,
        swing_arc=[(2.5, 0.0), (3.4, 0.0), (3.4, 0.9)],
        intent_id="door_intent_01",
    )
    assert door.id is not None
    assert door.position == (2.5, 0.0)
    assert door.intent_id == "door_intent_01"
    assert door.swing_arc is not None


def test_geo_window():
    """Test GeoWindow with sill height and intent linkage."""
    window = GeoWindow(
        wall_id="wall_02",
        position=(1.0, 5.0),
        width=1.2,
        height=1.2,
        sill_height=0.9,
        intent_id="window_intent_01",
    )
    assert window.id is not None
    assert window.sill_height == 0.9
    assert window.intent_id == "window_intent_01"


def test_geo_staircase():
    """Test GeoStaircase with tread/riser specs and footprint polygon."""
    stair = GeoStaircase(
        polygon=[(0.0, 0.0), (2.0, 0.0), (2.0, 3.0), (0.0, 3.0)],
        from_floor=1,
        to_floor=2,
        riser_count=16,
        tread_depth=0.28,
        intent_id="stair_intent_01",
    )
    assert stair.id is not None
    assert stair.riser_count == 16
    assert stair.tread_depth == 0.28
    assert len(stair.polygon) == 4


def test_geo_room_dual_polygons():
    """Test GeoRoom dual usable and built polygon representations."""
    room = GeoRoom(
        room_type="bedroom",
        usable_polygon=[(0.2, 0.2), (3.8, 0.2), (3.8, 3.8), (0.2, 3.8)],
        built_polygon=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
        area_sqm=12.96,
        walls=["wall_1", "wall_2", "wall_3", "wall_4"],
        doors=["door_1"],
        windows=["window_1"],
        architectural_room_id="room_design_01",
    )
    assert room.id is not None
    assert len(room.usable_polygon) == 4
    assert len(room.built_polygon) == 4
    # Backward compatibility property
    assert room.polygon == room.usable_polygon


def test_geometry_and_geometry_set():
    """Test Geometry single-floor lookups and GeometrySet multi-floor query."""
    room = GeoRoom(id="room_living", room_type="living", area_sqm=25.0)
    wall = GeoWall(id="wall_01")
    door = GeoDoor(id="door_01")

    geom_f1 = Geometry(
        floor_number=1,
        rooms=[room],
        walls=[wall],
        doors=[door],
        plot_polygon=[(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)],
        buildable_polygon=[(2.0, 2.0), (18.0, 2.0), (18.0, 18.0), (2.0, 18.0)],
    )

    geom_f2 = Geometry(floor_number=2)

    geom_set = GeometrySet(geometries=[geom_f1, geom_f2])

    assert geom_f1.get_room("room_living") == room
    assert geom_f1.get_wall("wall_01") == wall
    assert geom_f1.get_door("door_01") == door
    assert geom_f1.total_usable_area() == 25.0
    assert len(geom_f1.buildable_polygon) == 4

    assert geom_set.get_geometry(1) == geom_f1
    assert geom_set.get_geometry(2) == geom_f2
    assert geom_set.get_geometry(3) is None

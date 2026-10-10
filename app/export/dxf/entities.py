"""Deterministic CAD vector entity generation for PlanForge DXF export.

Converts validated PlanForge geometry objects into standard CAD entities:
- Closed LWPOLYLINE for plot, buildable, room boundaries, and wall thickness polygons
- LINE and ARC entities for doors, swing trajectories, and windows
- Treads and risers for staircases
- Centered MTEXT labels with representative-point interior placement
- Linear DIMENSION entities for bounding measurements
"""

from __future__ import annotations
import math
from typing import List, Optional, Tuple
import ezdxf
from shapely.geometry import Polygon

from app.models.geometry import GeoDoor, GeoRoom, GeoStaircase, GeoWall, GeoWindow

Point2D = Tuple[float, float]


def add_polygon(
    msp: ezdxf.layouts.Modelspace,
    points: List[Point2D],
    layer: str,
    closed: bool = True,
) -> Optional[ezdxf.entities.LWPolyline]:
    """Add a 2D polyline entity preserving exact coordinate precision."""
    if not points or len(points) < 2:
        return None
    # Ensure all coordinate tuples are float
    coords = [(float(p[0]), float(p[1])) for p in points]
    return msp.add_lwpolyline(coords, close=closed, dxfattribs={"layer": layer})


def add_line(
    msp: ezdxf.layouts.Modelspace,
    start: Point2D,
    end: Point2D,
    layer: str,
) -> ezdxf.entities.Line:
    """Add a straight CAD line entity."""
    p1 = (float(start[0]), float(start[1]))
    p2 = (float(end[0]), float(end[1]))
    return msp.add_line(p1, p2, dxfattribs={"layer": layer})


def add_circle(
    msp: ezdxf.layouts.Modelspace,
    center: Point2D,
    radius: float,
    layer: str,
) -> ezdxf.entities.Circle:
    """Add a CAD circle entity."""
    c = (float(center[0]), float(center[1]))
    return msp.add_circle(c, radius=float(radius), dxfattribs={"layer": layer})


def add_wall_entity(
    msp: ezdxf.layouts.Modelspace,
    wall: GeoWall,
    exterior_layer: str,
    interior_layer: str,
) -> None:
    """Export a constructed wall segment with geometric accuracy.

    If wall footprint polygon is present, exports the closed polygon
    representing actual wall thickness. Otherwise exports the centerline.
    """
    layer = exterior_layer if wall.type == "exterior" else interior_layer

    if wall.polygon and len(wall.polygon) >= 3:
        add_polygon(msp, wall.polygon, layer, closed=True)
    elif wall.start and wall.end:
        add_line(msp, wall.start, wall.end, layer)


def add_door_entity(
    msp: ezdxf.layouts.Modelspace,
    door: GeoDoor,
    door_layer: str,
    swing_layer: str,
) -> None:
    """Export door opening, leaf geometry, and swing arc."""
    # Door marker / position indicator
    px, py = float(door.position[0]), float(door.position[1])
    add_circle(msp, (px, py), radius=0.06, layer=door_layer)

    if door.swing_arc and len(door.swing_arc) >= 2:
        # Swing arc vertices: [hinge, arc_pt_1, ..., arc_pt_N]
        hinge = door.swing_arc[0]
        # Door leaf line connecting hinge to the initial arc point
        open_leaf_end = door.swing_arc[1]
        add_line(msp, hinge, open_leaf_end, door_layer)

        # 90-degree swing arc trajectory
        arc_points = door.swing_arc[1:]
        add_polygon(msp, arc_points, swing_layer, closed=False)
    else:
        # Simple door opening threshold segment
        w2 = (door.width or 0.9) / 2.0
        add_line(msp, (px - w2, py), (px + w2, py), door_layer)


def add_window_entity(
    msp: ezdxf.layouts.Modelspace,
    window: GeoWindow,
    window_layer: str,
    wall: Optional[GeoWall] = None,
) -> None:
    """Export window opening, sills, and glazing line."""
    px, py = float(window.position[0]), float(window.position[1])
    w_half = (window.width or 1.2) / 2.0

    if wall and wall.start and wall.end:
        dx = wall.end[0] - wall.start[0]
        dy = wall.end[1] - wall.start[1]
        length = math.hypot(dx, dy)
        if length > 1e-6:
            ux, uy = dx / length, dy / length
            nx, ny = -uy, ux
            t_half = (wall.thickness or 0.2) / 2.0

            p1 = (px - ux * w_half, py - uy * w_half)
            p2 = (px + ux * w_half, py + uy * w_half)

            # Window outer frame box
            frame_box = [
                (p1[0] - nx * t_half, p1[1] - ny * t_half),
                (p2[0] - nx * t_half, p2[1] - ny * t_half),
                (p2[0] + nx * t_half, p2[1] + ny * t_half),
                (p1[0] + nx * t_half, p1[1] + ny * t_half),
            ]
            add_polygon(msp, frame_box, window_layer, closed=True)

            # Glass centerline
            add_line(msp, p1, p2, window_layer)
            return

    # Fallback standard horizontal opening segment
    add_line(msp, (px - w_half, py), (px + w_half, py), window_layer)


def add_staircase_entity(
    msp: ezdxf.layouts.Modelspace,
    stair: GeoStaircase,
    stair_layer: str,
    label_layer: Optional[str] = None,
) -> None:
    """Export staircase footprint, treads, risers, and direction label."""
    if not stair.polygon or len(stair.polygon) < 3:
        return

    # Footprint boundary
    add_polygon(msp, stair.polygon, stair_layer, closed=True)

    # Calculate bounding extents for tread distribution
    s_min_x = min(p[0] for p in stair.polygon)
    s_max_x = max(p[0] for p in stair.polygon)
    s_min_y = min(p[1] for p in stair.polygon)
    s_max_y = max(p[1] for p in stair.polygon)
    rc = max(stair.riser_count, 8)

    # Draw tread lines
    if (s_max_y - s_min_y) >= (s_max_x - s_min_x):
        step = (s_max_y - s_min_y) / rc
        for i in range(1, rc):
            y_line = s_min_y + i * step
            add_line(msp, (s_min_x, y_line), (s_max_x, y_line), stair_layer)
    else:
        step = (s_max_x - s_min_x) / rc
        for i in range(1, rc):
            x_line = s_min_x + i * step
            add_line(msp, (x_line, s_min_y), (x_line, s_max_y), stair_layer)

    # Staircase direction label
    target_layer = label_layer or stair_layer
    stair_label = f"Staircase (F{stair.from_floor}->F{stair.to_floor})"
    cx = (s_min_x + s_max_x) / 2.0
    cy = (s_min_y + s_max_y) / 2.0
    try:
        mt = msp.add_mtext(stair_label, dxfattribs={"layer": target_layer, "char_height": 0.22})
        mt.dxf.attachment_point = 5  # Middle-Center
        mt.set_location((cx, cy))
    except Exception:
        msp.add_text(stair_label, dxfattribs={"layer": target_layer, "height": 0.22}).set_placement((cx, cy))


def add_room_entity(
    msp: ezdxf.layouts.Modelspace,
    room: GeoRoom,
    room_layer: str,
    corridor_layer: Optional[str] = None,
) -> None:
    """Export room boundary polygon, differentiating corridors if specified."""
    poly_coords = room.usable_polygon or room.built_polygon
    if not poly_coords or len(poly_coords) < 3:
        return

    is_circulation = room.is_corridor or room.room_type.lower() in (
        "corridor", "hallway", "circulation", "passage", "entry_hall",
    )
    layer = corridor_layer if (is_circulation and corridor_layer) else room_layer
    add_polygon(msp, poly_coords, layer, closed=True)


def add_room_label_entity(
    msp: ezdxf.layouts.Modelspace,
    room: GeoRoom,
    label_layer: str,
    floor_number: Optional[int] = None,
) -> None:
    """Add centered, formatted CAD room label with representative-point interior placement.

    Formats:
    <Room Name>
    <Area> m²
    """
    poly_coords = room.usable_polygon or room.built_polygon
    if not poly_coords or len(poly_coords) < 3:
        return

    # Compute interior representative point to prevent labels on L-shaped rooms
    # from falling outside the boundary
    try:
        poly = Polygon(poly_coords)
        if poly.is_valid and not poly.is_empty:
            rp = poly.representative_point()
            lx, ly = rp.x, rp.y
        else:
            xs = [p[0] for p in poly_coords]
            ys = [p[1] for p in poly_coords]
            lx, ly = sum(xs) / len(xs), sum(ys) / len(ys)
    except Exception:
        xs = [p[0] for p in poly_coords]
        ys = [p[1] for p in poly_coords]
        lx, ly = sum(xs) / len(xs), sum(ys) / len(ys)

    display_name = room.room_type.replace("_", " ").title()
    lines = [display_name]
    if room.area_sqm > 0:
        lines.append(f"{room.area_sqm:.1f} m²")

    mtext_content = "\\P".join(lines)
    try:
        mt = msp.add_mtext(mtext_content, dxfattribs={"layer": label_layer, "char_height": 0.28})
        mt.dxf.attachment_point = 5  # Middle-Center
        mt.set_location((lx, ly))
    except Exception:
        # Fallback to stacked simple text
        msp.add_text(lines[0], dxfattribs={"layer": label_layer, "height": 0.28}).set_placement((lx, ly + 0.15))
        if len(lines) > 1:
            msp.add_text(lines[1], dxfattribs={"layer": label_layer, "height": 0.22}).set_placement((lx, ly - 0.15))


def add_linear_dimensions(
    msp: ezdxf.layouts.Modelspace,
    bounds: Tuple[float, float, float, float],
    dim_layer: str,
) -> None:
    """Add overall bounding dimensions derived from actual geometry extents."""
    min_x, min_y, max_x, max_y = bounds
    width = max_x - min_x
    depth = max_y - min_y

    if width <= 0.5 or depth <= 0.5:
        return

    offset = max(min(width, depth) * 0.05, 0.8)

    # 1. Width Dimension along Bottom
    base_bottom = ((min_x + max_x) / 2.0, min_y - offset)
    p1_w = (min_x, min_y)
    p2_w = (max_x, min_y)
    text_w = f"{width:.2f} m"

    try:
        dim_w = msp.add_linear_dim(
            base=base_bottom,
            p1=p1_w,
            p2=p2_w,
            text=text_w,
            dxfattribs={"layer": dim_layer},
        )
        dim_w.render()
    except Exception:
        # Fallback explicit CAD dimension geometry
        _draw_explicit_dim(msp, p1_w, p2_w, base_bottom[1], text_w, dim_layer, is_horizontal=True)

    # 2. Depth Dimension along Left
    base_left = (min_x - offset, (min_y + max_y) / 2.0)
    p1_d = (min_x, min_y)
    p2_d = (min_x, max_y)
    text_d = f"{depth:.2f} m"

    try:
        dim_d = msp.add_linear_dim(
            base=base_left,
            p1=p1_d,
            p2=p2_d,
            angle=90,
            text=text_d,
            dxfattribs={"layer": dim_layer},
        )
        dim_d.render()
    except Exception:
        _draw_explicit_dim(msp, p1_d, p2_d, base_left[0], text_d, dim_layer, is_horizontal=False)


def _draw_explicit_dim(
    msp: ezdxf.layouts.Modelspace,
    p1: Point2D,
    p2: Point2D,
    offset_coord: float,
    label: str,
    layer: str,
    is_horizontal: bool = True,
) -> None:
    """Helper to draw explicit dimension lines and ticks if DIMENSION rendering fails."""
    tick_len = 0.2
    if is_horizontal:
        y = offset_coord
        # Dimension line
        add_line(msp, (p1[0], y), (p2[0], y), layer)
        # Extension lines
        add_line(msp, (p1[0], p1[1]), (p1[0], y - tick_len), layer)
        add_line(msp, (p2[0], p2[1]), (p2[0], y - tick_len), layer)
        # Ticks
        add_line(msp, (p1[0], y - tick_len), (p1[0], y + tick_len), layer)
        add_line(msp, (p2[0], y - tick_len), (p2[0], y + tick_len), layer)
        # Text
        cx = (p1[0] + p2[0]) / 2.0
        try:
            mt = msp.add_mtext(label, dxfattribs={"layer": layer, "char_height": 0.22})
            mt.dxf.attachment_point = 8  # Bottom-Center
            mt.set_location((cx, y - 0.35))
        except Exception:
            msp.add_text(label, dxfattribs={"layer": layer, "height": 0.22}).set_placement((cx, y - 0.35))
    else:
        x = offset_coord
        # Dimension line
        add_line(msp, (x, p1[1]), (x, p2[1]), layer)
        # Extension lines
        add_line(msp, (p1[0], p1[1]), (x - tick_len, p1[1]), layer)
        add_line(msp, (p2[0], p2[1]), (x - tick_len, p2[1]), layer)
        # Ticks
        add_line(msp, (x - tick_len, p1[1]), (x + tick_len, p1[1]), layer)
        add_line(msp, (x - tick_len, p2[1]), (x + tick_len, p2[1]), layer)
        # Text
        cy = (p1[1] + p2[1]) / 2.0
        try:
            mt = msp.add_mtext(label, dxfattribs={"layer": layer, "char_height": 0.22})
            mt.dxf.attachment_point = 4  # Middle-Left
            mt.set_location((x - 0.5, cy))
        except Exception:
            msp.add_text(label, dxfattribs={"layer": layer, "height": 0.22}).set_placement((x - 0.5, cy))

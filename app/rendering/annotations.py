"""Annotation rendering utilities for room labels, north arrow, and dimensions."""

from __future__ import annotations
import math
from typing import Optional, Tuple, Any
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from shapely.geometry import Polygon, Point

from app.rendering.options import RenderOptions


def get_label_point(polygon_coords: list[tuple[float, float]]) -> tuple[float, float]:
    """Calculate a reliable interior point for placing text inside a room polygon.

    Uses Shapely's representative_point() so labels on L-shaped or non-convex
    rooms always fall safely inside the polygon rather than outside.
    """
    if len(polygon_coords) < 3:
        if polygon_coords:
            return polygon_coords[0]
        return (0.0, 0.0)

    try:
        poly = Polygon(polygon_coords)
        if poly.is_valid and not poly.is_empty:
            rp = poly.representative_point()
            return (rp.x, rp.y)
    except Exception:
        pass

    # Fallback to arithmetic mean
    xs = [p[0] for p in polygon_coords]
    ys = [p[1] for p in polygon_coords]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def draw_room_label(
    ax: plt.Axes,
    room_type: str,
    area_sqm: float,
    polygon_coords: list[tuple[float, float]],
    options: RenderOptions,
    room_id: Optional[str] = None,
    text_color: str = "#2C3E50",
) -> None:
    """Draw a centered, clear label inside a room with name, area, and optional ID."""
    x, y = get_label_point(polygon_coords)

    # Format room name
    display_name = room_type.replace("_", " ").title()

    lines = [display_name]
    if options.show_room_areas and area_sqm > 0:
        lines.append(f"{area_sqm:.1f} m²")
    if options.show_room_ids and room_id:
        lines.append(f"[{room_id}]")

    label_text = "\n".join(lines)
    ax.text(
        x,
        y,
        label_text,
        ha="center",
        va="center",
        fontsize=8.5 if options.publication_mode else 9.0,
        fontweight="bold" if len(lines) == 1 else "normal",
        color=text_color,
        zorder=20,
        bbox=dict(
            boxstyle="round,pad=0.2",
            facecolor="white",
            alpha=0.75 if not options.publication_mode else 0.9,
            edgecolor="none",
        ),
    )


def draw_north_arrow(
    ax: plt.Axes,
    orientation: str,
    bounds: Tuple[float, float, float, float],
    options: RenderOptions,
) -> None:
    """Draw a professional architectural north arrow in the upper right margin.

    Strict invariant: Rendered ONLY when orientation is explicitly provided.
    Never fabricated.
    """
    if not orientation:
        return

    min_x, min_y, max_x, max_y = bounds
    width = max_x - min_x
    height = max_y - min_y

    # Place in top-right corner with margin
    arrow_center_x = max_x - width * 0.08
    arrow_center_y = max_y - height * 0.08
    arrow_len = min(width, height) * 0.07

    # Angles in degrees (standard compass: North=90 deg upward, East=0 deg, etc.)
    # In PlanForge, "north" means plot orientation faces north (upwards along +Y axis).
    orient_norm = orientation.lower().strip()
    angle_map = {
        "north": 90.0,
        "south": 270.0,
        "east": 0.0,
        "west": 180.0,
        "north_east": 45.0,
        "north_west": 135.0,
        "south_east": 315.0,
        "south_west": 225.0,
    }
    angle_deg = angle_map.get(orient_norm, 90.0)
    rad = math.radians(angle_deg)

    dx = arrow_len * math.cos(rad)
    dy = arrow_len * math.sin(rad)

    # Arrow stem & head
    ax.annotate(
        "",
        xy=(arrow_center_x + dx, arrow_center_y + dy),
        xytext=(arrow_center_x - dx * 0.4, arrow_center_y - dy * 0.4),
        arrowprops=dict(
            arrowstyle="-|>",
            color="#2C3E50" if not options.publication_mode else "#000000",
            lw=2.0,
            mutation_scale=15,
        ),
        zorder=30,
    )

    # "N" label slightly past the arrow head
    label_offset_x = arrow_center_x + dx * 1.35
    label_offset_y = arrow_center_y + dy * 1.35
    ax.text(
        label_offset_x,
        label_offset_y,
        "N",
        ha="center",
        va="center",
        fontsize=10,
        fontweight="bold",
        color="#2C3E50" if not options.publication_mode else "#000000",
        zorder=30,
    )


def draw_bounding_dimensions(
    ax: plt.Axes,
    bounds: Tuple[float, float, float, float],
    options: RenderOptions,
) -> None:
    """Draw subtle overall dimension annotations along bottom and left exterior edges."""
    if not options.show_dimensions:
        return

    min_x, min_y, max_x, max_y = bounds
    width = max_x - min_x
    height = max_y - min_y

    if width <= 0 or height <= 0:
        return

    dim_offset = min(width, height) * 0.04

    # Bottom horizontal dimension line (width)
    y_dim = min_y - dim_offset
    ax.plot([min_x, max_x], [y_dim, y_dim], color="#7F8C8D", lw=0.9, linestyle="-", zorder=15)
    # Ticks
    ax.plot([min_x, min_x], [y_dim - dim_offset * 0.2, y_dim + dim_offset * 0.2], color="#7F8C8D", lw=0.9, zorder=15)
    ax.plot([max_x, max_x], [y_dim - dim_offset * 0.2, y_dim + dim_offset * 0.2], color="#7F8C8D", lw=0.9, zorder=15)
    # Text
    ax.text(
        (min_x + max_x) / 2.0,
        y_dim - dim_offset * 0.4,
        f"{width:.2f} m",
        ha="center",
        va="top",
        fontsize=7.5,
        color="#5D6D7E",
        zorder=16,
    )

    # Left vertical dimension line (depth/length)
    x_dim = min_x - dim_offset
    ax.plot([x_dim, x_dim], [min_y, max_y], color="#7F8C8D", lw=0.9, linestyle="-", zorder=15)
    # Ticks
    ax.plot([x_dim - dim_offset * 0.2, x_dim + dim_offset * 0.2], [min_y, min_y], color="#7F8C8D", lw=0.9, zorder=15)
    ax.plot([x_dim - dim_offset * 0.2, x_dim + dim_offset * 0.2], [max_y, max_y], color="#7F8C8D", lw=0.9, zorder=15)
    # Text
    ax.text(
        x_dim - dim_offset * 0.4,
        (min_y + max_y) / 2.0,
        f"{height:.2f} m",
        ha="right",
        va="center",
        fontsize=7.5,
        rotation=90,
        color="#5D6D7E",
        zorder=16,
    )


def draw_title_block(
    ax: plt.Axes,
    project_name: str,
    floor_number: int,
    usable_area: float,
    bounds: Tuple[float, float, float, float],
    options: RenderOptions,
) -> None:
    """Draw a clean, professional header / title at top left."""
    if not options.show_title:
        return

    min_x, min_y, max_x, max_y = bounds
    width = max_x - min_x
    height = max_y - min_y

    title_x = min_x
    title_y = max_y + height * 0.04

    floor_str = f"Floor {floor_number}"
    proj_str = f" — {project_name}" if project_name else ""
    header = f"{floor_str}{proj_str}"
    sub = f"Total Usable Area: {usable_area:.1f} m²" if usable_area > 0 else ""

    ax.text(
        title_x,
        title_y,
        header,
        ha="left",
        va="bottom",
        fontsize=12,
        fontweight="bold",
        color="#1A252F" if not options.publication_mode else "#000000",
        zorder=25,
    )
    if sub:
        ax.text(
            title_x,
            title_y - height * 0.025,
            sub,
            ha="left",
            va="top",
            fontsize=8.5,
            color="#7F8C8D" if not options.publication_mode else "#333333",
            zorder=25,
        )

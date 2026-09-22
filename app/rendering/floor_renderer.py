"""Deterministic floor plan visualization using matplotlib."""

from __future__ import annotations
import math
import os
from pathlib import Path
from typing import Optional, Union, List, Tuple
import matplotlib
# Enforce headless Agg backend for pure offline execution
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from shapely.geometry import Polygon

from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.models.geometry import Geometry, GeoRoom, GeoWall, GeoDoor, GeoWindow, GeoStaircase
from app.rendering.errors import RenderingError, UnsupportedGeometryError, EmptyGeometryError
from app.rendering.options import RenderOptions, RenderedFloor
from app.rendering.styles import (
    COLOR_PALETTE,
    PUBLICATION_PALETTE,
    STYLE_PLOT_BOUNDARY,
    STYLE_BUILDABLE_BOUNDARY,
    STYLE_EXTERIOR_WALL,
    STYLE_INTERIOR_WALL,
    STYLE_DOOR_SWING,
    STYLE_ENTRANCE_DOOR,
    STYLE_WINDOW,
    STYLE_STAIRCASE_FOOTPRINT,
    STYLE_STAIRCASE_TREAD,
    get_room_category,
)
from app.rendering.annotations import (
    draw_room_label,
    draw_north_arrow,
    draw_bounding_dimensions,
    draw_title_block,
)


class FloorPlanRenderer:
    """Deterministic visual renderer for PlanForge floor plans.

    Renders actual physical geometry from the Geometry Engine without
    reconstructing or modifying shapes, positions, or walls.
    """

    def __init__(self, default_options: Optional[RenderOptions] = None) -> None:
        self.default_options = default_options or RenderOptions()

    def render_floor_plan(
        self,
        floor_plan: FloorPlan,
        output_path: Union[str, Path],
        options: Optional[RenderOptions] = None,
        orientation: Optional[str] = None,
        project_name: str = "",
        fallback_plot_boundary: Optional[list[tuple[float, float]]] = None,
        fallback_buildable_boundary: Optional[list[tuple[float, float]]] = None,
    ) -> RenderedFloor:
        """Render a single FloorPlan to an image file (PNG).

        Args:
            floor_plan: The validated or unvalidated FloorPlan model.
            output_path: Target image file path.
            options: RenderOptions configuration (uses defaults if None).
            orientation: Orientation string (e.g. "north", "south"). Never fabricated.
            project_name: Optional project title for header block.
            fallback_plot_boundary: Global plot boundary if missing on Geometry.
            fallback_buildable_boundary: Global buildable boundary if missing on Geometry.

        Returns:
            RenderedFloor metadata record.
        """
        opts = options or self.default_options
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        geom = floor_plan.geometry
        if geom is None:
            raise EmptyGeometryError(
                f"FloorPlan for floor {floor_plan.floor_number} contains no Geometry object."
            )

        fn = floor_plan.floor_number

        # 1. Gather all coordinate points to determine rendering bounding box
        plot_poly = geom.plot_polygon or fallback_plot_boundary or []
        build_poly = geom.buildable_polygon or fallback_buildable_boundary or []

        all_coords: list[tuple[float, float]] = []
        all_coords.extend(plot_poly)
        all_coords.extend(build_poly)

        for room in geom.rooms:
            poly = room.usable_polygon or room.built_polygon
            all_coords.extend(poly)

        for wall in geom.walls:
            if wall.polygon:
                all_coords.extend(wall.polygon)
            else:
                all_coords.extend([wall.start, wall.end])

        for stair in geom.staircases:
            all_coords.extend(stair.polygon)

        if not all_coords:
            raise EmptyGeometryError(f"No geometric entities found to render on Floor {fn}.")

        min_x = min(p[0] for p in all_coords)
        max_x = max(p[0] for p in all_coords)
        min_y = min(p[1] for p in all_coords)
        max_y = max(p[1] for p in all_coords)

        # Handle zero-span edge cases
        if max_x - min_x < 0.1:
            max_x = min_x + 10.0
        if max_y - min_y < 0.1:
            max_y = min_y + 10.0

        span_x = max_x - min_x
        span_y = max_y - min_y
        margin = max(span_x, span_y) * opts.margin_ratio

        # 2. Setup Figure & Axes
        fig, ax = plt.subplots(figsize=opts.figsize, dpi=opts.dpi)
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

        ax.set_xlim(min_x - margin, max_x + margin)
        ax.set_ylim(min_y - margin, max_y + margin)
        ax.set_aspect("equal", adjustable="box")

        if not opts.show_grid:
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
        else:
            ax.grid(True, linestyle=":", alpha=0.4, color="#CCCCCC")

        # 3. Layer 1: Plot & Buildable Boundary (True Polygons, preserving irregular/L-shaped plots)
        has_plot = False
        has_build = False

        if plot_poly and len(plot_poly) >= 3:
            plot_patch = patches.Polygon(plot_poly, **STYLE_PLOT_BOUNDARY)
            ax.add_patch(plot_patch)
            has_plot = True

        if build_poly and len(build_poly) >= 3:
            build_patch = patches.Polygon(build_poly, **STYLE_BUILDABLE_BOUNDARY)
            ax.add_patch(build_patch)
            has_build = True

        # 4. Layer 2: Rooms
        palette = PUBLICATION_PALETTE if opts.publication_mode else COLOR_PALETTE
        rendered_rooms = 0
        rendered_corridors = 0

        for room in geom.rooms:
            poly_coords = room.usable_polygon or room.built_polygon
            if not poly_coords or len(poly_coords) < 3:
                continue

            category = get_room_category(room.room_type)
            if room.is_corridor or category == "circulation":
                rendered_corridors += 1

            cat_style = palette.get(category, palette["other"])
            fill_color = cat_style["fill"]
            edge_color = cat_style["edge"]

            room_patch = patches.Polygon(
                poly_coords,
                facecolor=fill_color,
                edgecolor=edge_color,
                linewidth=0.8 if not opts.publication_mode else 0.5,
                zorder=3,
            )
            ax.add_patch(room_patch)
            rendered_rooms += 1

        # 5. Layer 3: Staircases
        rendered_staircases = 0
        if opts.show_staircases:
            for stair in geom.staircases:
                if stair.polygon and len(stair.polygon) >= 3:
                    stair_patch = patches.Polygon(stair.polygon, **STYLE_STAIRCASE_FOOTPRINT)
                    ax.add_patch(stair_patch)

                    # Draw horizontal tread lines inside staircase polygon
                    s_min_x = min(p[0] for p in stair.polygon)
                    s_max_x = max(p[0] for p in stair.polygon)
                    s_min_y = min(p[1] for p in stair.polygon)
                    s_max_y = max(p[1] for p in stair.polygon)
                    rc = max(stair.riser_count, 8)

                    # Determine primary staircase orientation
                    if (s_max_y - s_min_y) >= (s_max_x - s_min_x):
                        step = (s_max_y - s_min_y) / rc
                        for i in range(1, rc):
                            y_line = s_min_y + i * step
                            ax.plot([s_min_x, s_max_x], [y_line, y_line], **STYLE_STAIRCASE_TREAD)
                    else:
                        step = (s_max_x - s_min_x) / rc
                        for i in range(1, rc):
                            x_line = s_min_x + i * step
                            ax.plot([x_line, x_line], [s_min_y, s_max_y], **STYLE_STAIRCASE_TREAD)

                    # Staircase label
                    stair_label = f"Staircase (F{stair.from_floor}→F{stair.to_floor})"
                    ax.text(
                        (s_min_x + s_max_x) / 2.0,
                        (s_min_y + s_max_y) / 2.0,
                        stair_label,
                        ha="center",
                        va="center",
                        fontsize=7.0,
                        color="#2C3E50",
                        zorder=8,
                        bbox=dict(boxstyle="square,pad=0.1", facecolor="white", alpha=0.8, edgecolor="none"),
                    )
                    rendered_staircases += 1

        # 6. Layer 4: Walls
        rendered_walls = 0
        if opts.show_walls:
            for wall in geom.walls:
                style = STYLE_EXTERIOR_WALL if wall.type == "exterior" else STYLE_INTERIOR_WALL

                if wall.polygon and len(wall.polygon) >= 3:
                    # Draw filled wall footprint
                    wall_patch = patches.Polygon(
                        wall.polygon,
                        facecolor=style["color"],
                        edgecolor=style["color"],
                        linewidth=0.5,
                        zorder=style["zorder"],
                    )
                    ax.add_patch(wall_patch)
                    rendered_walls += 1
                elif wall.start and wall.end:
                    ax.plot(
                        [wall.start[0], wall.end[0]],
                        [wall.start[1], wall.end[1]],
                        color=style["color"],
                        linewidth=style["linewidth"],
                        solid_capstyle=style["solid_capstyle"],
                        zorder=style["zorder"],
                    )
                    rendered_walls += 1

        # 7. Layer 5: Doors
        rendered_doors = 0
        if opts.show_doors:
            for door in geom.doors:
                is_entrance = door.type == "entrance"
                style = STYLE_ENTRANCE_DOOR if is_entrance else STYLE_DOOR_SWING

                # Draw swing arc if present
                if door.swing_arc and len(door.swing_arc) >= 2:
                    xs = [p[0] for p in door.swing_arc]
                    ys = [p[1] for p in door.swing_arc]
                    ax.plot(xs, ys, color=style["color"], linewidth=style["linewidth"], zorder=style["zorder"])

                # Door position marker
                px, py = door.position
                ax.plot(px, py, marker="o", markersize=3.5, color=style["color"], zorder=style["zorder"] + 1)
                rendered_doors += 1

        # 8. Layer 6: Windows
        rendered_windows = 0
        if opts.show_windows:
            for win in geom.windows:
                px, py = win.position
                w_half = (win.width or 1.2) / 2.0

                # Window line oriented along wall or standard segment
                ax.plot(
                    [px - w_half, px + w_half],
                    [py, py],
                    color=STYLE_WINDOW["color"],
                    linewidth=STYLE_WINDOW["linewidth"],
                    solid_capstyle=STYLE_WINDOW["solid_capstyle"],
                    zorder=STYLE_WINDOW["zorder"],
                )
                rendered_windows += 1

        # 9. Layer 7: Dimensions
        if opts.show_dimensions:
            draw_bounding_dimensions(ax, (min_x, min_y, max_x, max_y), opts)

        # 10. Layer 8: Labels
        for room in geom.rooms:
            poly_coords = room.usable_polygon or room.built_polygon
            if not poly_coords or len(poly_coords) < 3:
                continue
            category = get_room_category(room.room_type)
            cat_style = palette.get(category, palette["other"])
            draw_room_label(
                ax,
                room.room_type,
                room.area_sqm,
                poly_coords,
                opts,
                room_id=room.id,
                text_color=cat_style["label"],
            )

        # 11. Layer 9: North Arrow (ONLY if orientation provided)
        if opts.show_orientation and orientation:
            draw_north_arrow(ax, orientation, (min_x, min_y, max_x, max_y), opts)

        # 12. Layer 10: Title Block
        if opts.show_title:
            draw_title_block(
                ax,
                project_name=project_name or floor_plan.project_name,
                floor_number=fn,
                usable_area=floor_plan.usable_area(),
                bounds=(min_x, min_y, max_x, max_y),
                options=opts,
            )

        # Save to file
        fig.savefig(
            out_p,
            dpi=opts.dpi,
            bbox_inches="tight",
            facecolor="white",
            edgecolor="none",
        )
        plt.close(fig)

        # Calculate actual image dimensions in pixels
        width_px = int(opts.figsize[0] * opts.dpi)
        height_px = int(opts.figsize[1] * opts.dpi)

        return RenderedFloor(
            floor_number=fn,
            output_path=str(out_p.resolve()),
            width_px=width_px,
            height_px=height_px,
            rendered_room_count=rendered_rooms,
            rendered_wall_count=rendered_walls,
            rendered_door_count=rendered_doors,
            rendered_window_count=rendered_windows,
            rendered_staircase_count=rendered_staircases,
            rendered_corridor_count=rendered_corridors,
            orientation=orientation,
            has_plot_boundary=has_plot,
            has_buildable_boundary=has_build,
        )

    def render_floor_plan_set(
        self,
        floor_plan_set: FloorPlanSet,
        output_dir: Union[str, Path],
        options: Optional[RenderOptions] = None,
        orientation: Optional[str] = None,
        project_name: str = "",
    ) -> List[RenderedFloor]:
        """Render a complete multi-floor plan set producing one independent image per floor.

        Invariant: Never combines floors into a single drawing. For N floors, produces
        N distinct image files (floor_1.png, floor_2.png, etc.).
        """
        out_d = Path(output_dir)
        out_d.mkdir(parents=True, exist_ok=True)
        results: List[RenderedFloor] = []

        proj = project_name or floor_plan_set.project_name

        for fp in floor_plan_set.floor_plans:
            fn = fp.floor_number
            out_file = out_d / f"floor_{fn}.png"
            rendered = self.render_floor_plan(
                floor_plan=fp,
                output_path=out_file,
                options=options,
                orientation=orientation,
                project_name=proj,
                fallback_plot_boundary=floor_plan_set.plot_boundary,
                fallback_buildable_boundary=floor_plan_set.buildable_boundary,
            )
            results.append(rendered)

        return results


# Backward-compatible alias
PlanForgeFloorPlanRenderer = FloorPlanRenderer

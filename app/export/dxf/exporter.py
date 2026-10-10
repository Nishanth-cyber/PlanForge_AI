"""Deterministic DXF Exporter for PlanForge floor plans and multi-floor sets.

Converts validated PlanForge FloorPlanSet geometry into publication-grade,
standard-compliant AutoCAD DXF files (R2018/R2013 ASCII DXF).

Guarantees:
- Direct consumption of authoritative Geometry Engine output (no re-inference)
- Exact preservation of polygon coordinates, plot shapes, setbacks, and wall footprints
- Proper layer separation (plot, buildable, exterior/interior walls, doors, swings, windows, stairs, labels, dimensions)
- Multi-floor project support with distinct floor-prefixed layers
- Deterministic output generation for reproducible research and audits
"""

from __future__ import annotations
from pathlib import Path
import re
from typing import List, Optional, Tuple, Union
import ezdxf

from app.export.errors import InvalidExportInputError, ExportError
from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.export.dxf.layers import (
    LAYER_PLOT_BOUNDARY,
    LAYER_BUILDABLE_BOUNDARY,
    LAYER_WALLS_EXTERIOR,
    LAYER_WALLS_INTERIOR,
    LAYER_ROOM_BOUNDARIES,
    LAYER_DOORS,
    LAYER_DOOR_SWINGS,
    LAYER_WINDOWS,
    LAYER_STAIRCASES,
    LAYER_CORRIDORS,
    LAYER_ROOM_LABELS,
    LAYER_DIMENSIONS,
    get_layer_name,
    setup_dxf_layers,
)
from app.export.dxf.entities import (
    add_polygon,
    add_wall_entity,
    add_door_entity,
    add_window_entity,
    add_staircase_entity,
    add_room_entity,
    add_room_label_entity,
    add_linear_dimensions,
)


def sanitize_project_name(name: str) -> str:
    """Sanitize project title into a safe, deterministic filename slug."""
    if not name:
        return ""
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    cleaned = re.sub(r'[\s]+', "_", cleaned.strip())
    cleaned = re.sub(r'[^a-zA-Z0-9_\-]', "", cleaned)
    return cleaned.strip("._-").lower()


def get_dxf_filename(project_name: str, is_multi_floor: bool = False) -> str:
    """Generate canonical DXF filename based on project name and floor multiplicity.

    Single-floor: <project_name>_floorplan.dxf (or floorplan.dxf)
    Multi-floor:  <project_name>_floorplans.dxf (or floorplans.dxf)
    """
    slug = sanitize_project_name(project_name)
    suffix = "floorplans.dxf" if is_multi_floor else "floorplan.dxf"
    if slug:
        return f"{slug}_{suffix}"
    return suffix


class DXFExporter:
    """Authoritative exporter generating standard DXF files from validated PlanForge geometry."""

    def __init__(self, dxf_version: str = "R2018") -> None:
        self.dxf_version = dxf_version

    def export_floor_plan_set(
        self,
        floor_plan_set: FloorPlanSet,
        output_path: Union[str, Path],
        project_name: str = "",
    ) -> Path:
        """Export a validated FloorPlanSet to a standard DXF drawing file.

        Args:
            floor_plan_set: Validated FloorPlanSet model.
            output_path: Destination DXF file path.
            project_name: Optional override project name for annotations and filename.

        Returns:
            Path to the generated DXF file.

        Raises:
            InvalidExportInputError: If floor plan set is invalid, missing geometry, or empty.
            ExportError: If file generation or writing fails.
        """
        if not floor_plan_set or not floor_plan_set.floor_plans:
            raise InvalidExportInputError("Cannot export empty FloorPlanSet: no floor plans present.")

        # Validation gate (Requirement 15)
        if floor_plan_set.validation_report is not None and not floor_plan_set.all_valid:
            raise InvalidExportInputError(
                "Floor plan set failed validation. DXF export is strictly permitted only for valid floor plans."
            )

        # Check geometry existence
        has_geometry = any(fp.geometry is not None for fp in floor_plan_set.floor_plans)
        if not has_geometry:
            raise InvalidExportInputError("Cannot export FloorPlanSet: no geometry found on any floor.")

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Initialize DXF Document
            doc = ezdxf.new(self.dxf_version)
            # DXF units: 6 = Meters (INSUNITS), 1 = Metric (MEASUREMENT)
            doc.header["$INSUNITS"] = 6
            doc.header["$MEASUREMENT"] = 1

            floor_numbers = [fp.floor_number for fp in floor_plan_set.floor_plans]
            is_multi_floor = len(floor_numbers) > 1

            # 2. Register all architectural layers with standard colors & lineweights
            setup_dxf_layers(doc, floor_numbers=floor_numbers)
            msp = doc.modelspace()

            # 3. Collect all coordinates to compute overall bounds for dimensions
            all_coords: List[Tuple[float, float]] = []

            plot_boundary = floor_plan_set.plot_boundary
            if not plot_boundary and floor_plan_set.floor_plans[0].geometry:
                plot_boundary = floor_plan_set.floor_plans[0].geometry.plot_polygon
            if plot_boundary:
                all_coords.extend(plot_boundary)

            buildable_boundary = floor_plan_set.buildable_boundary
            if not buildable_boundary and floor_plan_set.floor_plans[0].geometry:
                buildable_boundary = floor_plan_set.floor_plans[0].geometry.buildable_polygon
            if buildable_boundary:
                all_coords.extend(buildable_boundary)

            # 4. Export Global Site Boundaries (Plot & Buildable Envelope)
            if plot_boundary and len(plot_boundary) >= 3:
                add_polygon(msp, plot_boundary, LAYER_PLOT_BOUNDARY, closed=True)

            if buildable_boundary and len(buildable_boundary) >= 3:
                add_polygon(msp, buildable_boundary, LAYER_BUILDABLE_BOUNDARY, closed=True)

            # 5. Export Geometries for each floor
            # Sort floors deterministically
            sorted_floors = sorted(floor_plan_set.floor_plans, key=lambda f: f.floor_number)

            for fp in sorted_floors:
                geom = fp.geometry
                if geom is None:
                    continue

                fn = fp.floor_number
                # Resolve floor-specific or base layers
                ext_wall_layer = get_layer_name(LAYER_WALLS_EXTERIOR, fn, is_multi_floor)
                int_wall_layer = get_layer_name(LAYER_WALLS_INTERIOR, fn, is_multi_floor)
                room_layer = get_layer_name(LAYER_ROOM_BOUNDARIES, fn, is_multi_floor)
                corridor_layer = get_layer_name(LAYER_CORRIDORS, fn, is_multi_floor)
                door_layer = get_layer_name(LAYER_DOORS, fn, is_multi_floor)
                swing_layer = get_layer_name(LAYER_DOOR_SWINGS, fn, is_multi_floor)
                window_layer = get_layer_name(LAYER_WINDOWS, fn, is_multi_floor)
                stair_layer = get_layer_name(LAYER_STAIRCASES, fn, is_multi_floor)
                label_layer = get_layer_name(LAYER_ROOM_LABELS, fn, is_multi_floor)
                dim_layer = get_layer_name(LAYER_DIMENSIONS, fn, is_multi_floor)

                # Collect room coordinates
                for r in geom.rooms:
                    poly = r.usable_polygon or r.built_polygon
                    if poly:
                        all_coords.extend(poly)

                # Collect wall coordinates
                for w in geom.walls:
                    if w.polygon:
                        all_coords.extend(w.polygon)
                    elif w.start and w.end:
                        all_coords.extend([w.start, w.end])

                # Collect stair coordinates
                for s in geom.staircases:
                    if s.polygon:
                        all_coords.extend(s.polygon)

                # A. Rooms & Corridors (Sorted by ID for determinism)
                sorted_rooms = sorted(geom.rooms, key=lambda r: (r.room_type, r.id))
                for room in sorted_rooms:
                    add_room_entity(msp, room, room_layer, corridor_layer)
                    add_room_label_entity(msp, room, label_layer, floor_number=fn)

                # B. Walls (Exterior & Interior, sorted by ID)
                sorted_walls = sorted(geom.walls, key=lambda w: (w.type, w.id))
                for wall in sorted_walls:
                    add_wall_entity(msp, wall, ext_wall_layer, int_wall_layer)

                # C. Doors & Swing Arcs (Sorted by ID)
                sorted_doors = sorted(geom.doors, key=lambda d: d.id)
                for door in sorted_doors:
                    add_door_entity(msp, door, door_layer, swing_layer)

                # D. Windows (Sorted by ID)
                sorted_windows = sorted(geom.windows, key=lambda win: win.id)
                for win in sorted_windows:
                    wall = geom.get_wall(win.wall_id) if win.wall_id else None
                    add_window_entity(msp, win, window_layer, wall)

                # E. Staircases (Sorted by ID)
                sorted_stairs = sorted(geom.staircases, key=lambda s: s.id)
                for stair in sorted_stairs:
                    add_staircase_entity(msp, stair, stair_layer, label_layer)

                # F. Floor-specific Dimensions (if multi-floor)
                if is_multi_floor:
                    floor_coords: List[Tuple[float, float]] = []
                    for r in geom.rooms:
                        poly = r.usable_polygon or r.built_polygon
                        if poly:
                            floor_coords.extend(poly)
                    if floor_coords:
                        f_min_x = min(p[0] for p in floor_coords)
                        f_max_x = max(p[0] for p in floor_coords)
                        f_min_y = min(p[1] for p in floor_coords)
                        f_max_y = max(p[1] for p in floor_coords)
                        add_linear_dimensions(msp, (f_min_x, f_min_y, f_max_x, f_max_y), dim_layer)

            # 6. Overall Project Dimensions (Single-floor or Overall plot)
            if all_coords:
                min_x = min(p[0] for p in all_coords)
                max_x = max(p[0] for p in all_coords)
                min_y = min(p[1] for p in all_coords)
                max_y = max(p[1] for p in all_coords)
                overall_bounds = (min_x, min_y, max_x, max_y)
                add_linear_dimensions(msp, overall_bounds, LAYER_DIMENSIONS)

            # 7. Write DXF file deterministically
            doc.saveas(str(out_path), encoding="utf-8")
            return out_path

        except Exception as e:
            if isinstance(e, InvalidExportInputError):
                raise
            raise ExportError(f"Failed to export DXF to '{out_path}': {e}") from e

    def export_floor_plan(
        self,
        floor_plan: FloorPlan,
        output_path: Union[str, Path],
        fallback_plot_boundary: Optional[List[Tuple[float, float]]] = None,
        fallback_buildable_boundary: Optional[List[Tuple[float, float]]] = None,
        project_name: str = "",
    ) -> Path:
        """Export a single FloorPlan to DXF.

        Constructs a single-floor FloorPlanSet wrapper and delegates.
        """
        fps = FloorPlanSet(
            id=f"fps_{floor_plan.id}",
            project_name=project_name or floor_plan.project_name,
            plot_boundary=fallback_plot_boundary or (floor_plan.geometry.plot_polygon if floor_plan.geometry else []),
            buildable_boundary=fallback_buildable_boundary or (floor_plan.geometry.buildable_polygon if floor_plan.geometry else []),
            floor_plans=[floor_plan],
            validation_report=None,  # Pass through validation state from floor_plan
        )
        # If single floor plan has validation, reflect it
        if floor_plan.validation is not None:
            fps.floor_plans[0].is_valid = floor_plan.is_valid
        return self.export_floor_plan_set(fps, output_path, project_name=project_name)


def export_floor_plan_set_to_dxf(
    floor_plan_set: FloorPlanSet,
    output_path: Union[str, Path],
    project_name: str = "",
    dxf_version: str = "R2018",
) -> Path:
    """Convenience function to export a FloorPlanSet to DXF."""
    exporter = DXFExporter(dxf_version=dxf_version)
    return exporter.export_floor_plan_set(
        floor_plan_set=floor_plan_set,
        output_path=output_path,
        project_name=project_name,
    )

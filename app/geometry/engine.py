"""Geometry Engine for deterministic physical architectural geometry construction.

Converts ArchitecturalDesignSet and ASAA AllocationSet into exact physical geometry:
GeoRoom, GeoWall, GeoDoor, GeoWindow, GeoStaircase, Geometry, GeometrySet, and
assembles an unvalidated FloorPlanSet.
"""

from __future__ import annotations
import logging
import math
from typing import List, Optional, Tuple

from app.geometry.corridor_builder import CorridorBuilder
from app.geometry.door_builder import DoorBuilder
from app.geometry.exceptions import (
    DoorPlacementError,
    GeometryConstructionError,
    RoomOutOfBoundsError,
    WindowPlacementError,
)
from app.geometry.room_builder import RoomBuilder
from app.geometry.staircase_builder import StaircaseBuilder
from app.geometry.wall_builder import WallBuilder
from app.geometry.window_builder import WindowBuilder
from app.models.allocation import Allocation, AllocationSet
from app.models.architectural_design import (
    ArchitecturalDesign,
    ArchitecturalDesignSet,
)
from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.models.geometry import (
    GeoDoor,
    Geometry,
    GeometrySet,
    GeoRoom,
    GeoStaircase,
    GeoWall,
    GeoWindow,
)
from app.utils.ids import generate_id

Point2D = Tuple[float, float]

logger = logging.getLogger(__name__)


class GeometryEngine:
    """Deterministic physical geometry construction engine.

    Answers HOW MUCH EXACT PHYSICAL SPACE is constructed, realizing upstream
    WHERE (ASAA) and HOW (Architectural LLM) into concrete CAD geometry.
    """

    def __init__(
        self,
        exterior_wall_thickness: float = 0.20,
        interior_wall_thickness: float = 0.15,
        wall_height: float = 3.0,
    ):
        """Initialize GeometryEngine.

        Args:
            exterior_wall_thickness: Standard exterior wall thickness in meters.
            interior_wall_thickness: Standard interior partition thickness in meters.
            wall_height: Standard room and wall height in meters.
        """
        self.exterior_wall_thickness = exterior_wall_thickness
        self.interior_wall_thickness = interior_wall_thickness
        self.wall_height = wall_height

    def construct_floor(
        self,
        floor_design: ArchitecturalDesign,
        allocation: Allocation,
        plot_boundary: Optional[List[Point2D]] = None,
        buildable_boundary: Optional[List[Point2D]] = None,
    ) -> Geometry:
        """Construct exact physical geometry for a single floor.

        Args:
            floor_design: Architectural room, door, window, and stair proposals.
            allocation: Spatial regions allocated by ASAA for this floor.
            plot_boundary: Optional plot boundary coordinates.
            buildable_boundary: Optional buildable footprint coordinates.

        Returns:
            Geometry instance containing rooms, walls, doors, windows, staircases.

        Raises:
            GeometryConstructionError: If any construction violates geometry invariants.
        """
        constructed_rooms: List[GeoRoom] = []

        # 1. Construct physical rooms
        for r_design in floor_design.rooms:
            # Match allocated region by ID or room_type
            matched_region = None
            if r_design.allocated_region_id:
                matched_region = allocation.get_region_by_id(r_design.allocated_region_id)
            if not matched_region:
                matching_regions = allocation.get_regions_by_type(r_design.room_type)
                if matching_regions:
                    matched_region = matching_regions[0]

            if not matched_region:
                raise RoomOutOfBoundsError(
                    f"Room design '{r_design.room_type}' (id={r_design.id}) has no matching "
                    f"allocated region in floor {floor_design.floor_number} allocation"
                )

            geo_room = RoomBuilder.build_room(
                room_design=r_design,
                allocated_region=matched_region,
                wall_thickness=self.exterior_wall_thickness,
            )
            constructed_rooms.append(geo_room)

        # 2. Construct circulation / corridor rooms
        for circ_reg in allocation.get_circulation_regions():
            corridor_room = CorridorBuilder.build_corridor(
                circulation_region=circ_reg,
                floor_number=floor_design.floor_number,
                wall_thickness=self.interior_wall_thickness,
            )
            constructed_rooms.append(corridor_room)

        # 3. Construct walls (exterior and interior partitions)
        constructed_walls = WallBuilder.build_walls_for_rooms(
            rooms=constructed_rooms,
            floor_number=floor_design.floor_number,
            exterior_thickness=self.exterior_wall_thickness,
            interior_thickness=self.interior_wall_thickness,
            wall_height=self.wall_height,
        )

        # Map architectural_room_id -> constructed GeoRoom
        arch_to_georoom = {
            r.architectural_room_id: r
            for r in constructed_rooms
            if r.architectural_room_id
        }

        # 4. Construct doors from DoorIntents
        constructed_doors: List[GeoDoor] = []
        placed_door_intents: set[str] = set()
        connected_room_pairs: set[frozenset[str]] = set()

        def _is_door_duplicate_or_overlapping(candidate: GeoDoor) -> bool:
            """Check whether candidate door is a duplicate or overlaps an existing door."""
            if candidate.intent_id and candidate.intent_id in placed_door_intents:
                return True
            for existing in constructed_doors:
                if existing.wall_id == candidate.wall_id:
                    dist = math.hypot(
                        existing.position[0] - candidate.position[0],
                        existing.position[1] - candidate.position[1],
                    )
                    min_dist = max(0.4, min(existing.width, candidate.width) * 0.8)
                    if dist < min_dist:
                        return True
            return False

        def _register_door(door: GeoDoor) -> None:
            """Register constructed door and its room connection."""
            constructed_doors.append(door)
            if door.intent_id:
                placed_door_intents.add(door.intent_id)
            if door.connects_from and door.connects_to and door.connects_to not in {"exterior", "balcony"}:
                connected_room_pairs.add(frozenset({door.connects_from, door.connects_to}))

        for r_design in floor_design.rooms:
            geo_r = arch_to_georoom.get(r_design.id)
            for door_intent in r_design.doors:
                # Skip duplicate intent
                if door_intent.id in placed_door_intents:
                    continue

                # Skip duplicate reciprocal interior door between already connected rooms
                if door_intent.connects_to not in {"exterior", "balcony"}:
                    r_pair = frozenset({door_intent.connects_from, door_intent.connects_to})
                    if r_pair in connected_room_pairs:
                        logger.info(
                            "Door connection between '%s' and '%s' already satisfied by existing door; skipping duplicate intent.",
                            door_intent.connects_from,
                            door_intent.connects_to,
                        )
                        continue

                try:
                    geo_door = DoorBuilder.build_door(
                        door_intent=door_intent,
                        walls=constructed_walls,
                        rooms=constructed_rooms,
                        floor_number=floor_design.floor_number,
                        source_room_override=geo_r,
                    )
                    if not _is_door_duplicate_or_overlapping(geo_door):
                        _register_door(geo_door)
                    else:
                        logger.info(
                            "Skipping door %s: overlaps existing door on wall %s",
                            geo_door.id,
                            geo_door.wall_id,
                        )
                except DoorPlacementError as e:
                    logger.warning(
                        "Door placement between '%s' and '%s' failed: %s. Applying automatic circulation fallback.",
                        door_intent.connects_from,
                        door_intent.connects_to,
                        e,
                    )
                    # Automatic fallback: connect room to circulation/corridor partition
                    import dataclasses
                    fallback_intent = dataclasses.replace(door_intent, connects_to="circulation")
                    try:
                        geo_door = DoorBuilder.build_door(
                            door_intent=fallback_intent,
                            walls=constructed_walls,
                            rooms=constructed_rooms,
                            floor_number=floor_design.floor_number,
                            source_room_override=geo_r,
                        )
                        if not _is_door_duplicate_or_overlapping(geo_door):
                            _register_door(geo_door)
                        else:
                            logger.info(
                                "Fallback door %s overlaps existing door; skipping.",
                                geo_door.id,
                            )
                    except DoorPlacementError:
                        placed = False
                        if geo_r:
                            # Secondary fallback: find ANY adjacent room sharing an interior partition wall
                            shared_wall_candidates = [
                                w for w in constructed_walls
                                if geo_r.id in w.room_ids and w.type == "interior" and len(w.room_ids) > 1
                            ]
                            for sw in shared_wall_candidates:
                                other_ids = [rid for rid in sw.room_ids if rid != geo_r.id]
                                if other_ids:
                                    other_r = next((rm for rm in constructed_rooms if rm.id == other_ids[0]), None)
                                    if other_r:
                                        adj_intent = dataclasses.replace(door_intent, connects_to=other_r.id)
                                        try:
                                            geo_door = DoorBuilder.build_door(
                                                door_intent=adj_intent,
                                                walls=constructed_walls,
                                                rooms=constructed_rooms,
                                                floor_number=floor_design.floor_number,
                                                source_room_override=geo_r,
                                            )
                                            if not _is_door_duplicate_or_overlapping(geo_door):
                                                _register_door(geo_door)
                                                placed = True
                                                logger.info(
                                                    "Placed secondary fallback door between '%s' and adjacent room '%s'.",
                                                    geo_r.room_type,
                                                    other_r.room_type,
                                                )
                                                break
                                        except DoorPlacementError:
                                            continue
                        if not placed:
                            logger.warning(
                                "Skipping unplaceable door intent %s after circulation fallback.",
                                door_intent.id,
                            )

        # 5. Construct windows from WindowIntents
        constructed_windows: List[GeoWindow] = []
        for r_design in floor_design.rooms:
            geo_r = arch_to_georoom.get(r_design.id)
            for win_intent in r_design.windows:
                try:
                    geo_win = WindowBuilder.build_window(
                        window_intent=win_intent,
                        walls=constructed_walls,
                        rooms=constructed_rooms,
                        floor_number=floor_design.floor_number,
                        target_room_override=geo_r,
                    )
                    constructed_windows.append(geo_win)
                except WindowPlacementError as e:
                    logger.warning(
                        "Skipping window intent %s for room %s (no exterior wall): %s",
                        win_intent.id,
                        win_intent.room_id,
                        e,
                    )

        # 6. Construct staircase from StaircaseIntent
        constructed_staircases: List[GeoStaircase] = []
        if floor_design.staircase_intent:
            stair_reg = allocation.get_staircase_region()
            geo_stair = StaircaseBuilder.build_staircase(
                staircase_intent=floor_design.staircase_intent,
                staircase_region=stair_reg,
                floor_number=floor_design.floor_number,
            )
            constructed_staircases.append(geo_stair)

        # Assemble Geometry for floor
        geometry = Geometry(
            id=generate_id("geom"),
            floor_number=floor_design.floor_number,
            rooms=constructed_rooms,
            walls=constructed_walls,
            doors=constructed_doors,
            windows=constructed_windows,
            staircases=constructed_staircases,
            plot_polygon=plot_boundary or [],
            buildable_polygon=buildable_boundary or [],
        )

        return geometry

    def construct(
        self,
        design_set: ArchitecturalDesignSet,
        allocation_set: AllocationSet,
        plot_boundary: Optional[List[Point2D]] = None,
        buildable_boundary: Optional[List[Point2D]] = None,
        project_name: str = "PlanForge Project",
    ) -> FloorPlanSet:
        """Construct physical geometry across all floors and assemble an unvalidated FloorPlanSet.

        Args:
            design_set: Complete multi-floor architectural proposals (HOW).
            allocation_set: Complete multi-floor ASAA allocations (WHERE).
            plot_boundary: Optional plot boundary coordinates.
            buildable_boundary: Optional buildable envelope coordinates.
            project_name: Project name.

        Returns:
            FloorPlanSet with assembled Geometry per floor (is_valid=False).

        Raises:
            GeometryConstructionError: If any floor geometry construction fails.
        """
        geometry_set = GeometrySet(
            id=generate_id("geom_set"),
            architectural_design_id=design_set.id,
        )

        floor_plans: List[FloorPlan] = []

        for f_design in sorted(design_set.designs, key=lambda d: d.floor_number):
            alloc = allocation_set.get_allocation(f_design.floor_number)
            if not alloc:
                raise GeometryConstructionError(
                    f"No ASAA allocation found for floor {f_design.floor_number}"
                )

            floor_geom = self.construct_floor(
                floor_design=f_design,
                allocation=alloc,
                plot_boundary=plot_boundary,
                buildable_boundary=buildable_boundary,
            )

            geometry_set.geometries.append(floor_geom)

            # Metadata for explainability and traceability
            fp_meta = {
                "room_count": len([r for r in floor_geom.rooms if not r.is_corridor]),
                "corridor_count": len([r for r in floor_geom.rooms if r.is_corridor]),
                "wall_count": len(floor_geom.walls),
                "door_count": len(floor_geom.doors),
                "window_count": len(floor_geom.windows),
                "staircase_count": len(floor_geom.staircases),
                "total_usable_area_sqm": floor_geom.total_usable_area(),
                "allocation_id": alloc.id,
                "architectural_design_id": f_design.id,
            }

            # Assemble FloorPlan: validation is strictly Phase 7
            floor_plan = FloorPlan(
                id=generate_id("floorplan"),
                project_name=project_name,
                floor_number=f_design.floor_number,
                geometry=floor_geom,
                validation=None,
                is_valid=False,
                metadata=fp_meta,
                notes=f"Constructed physical geometry for Floor {f_design.floor_number}",
            )
            floor_plans.append(floor_plan)

        generation_metadata = {
            "geometry_set_id": geometry_set.id,
            "architectural_design_set_id": design_set.id,
            "allocation_set_id": allocation_set.id,
            "total_floors": len(floor_plans),
            "total_usable_area_sqm": sum(fp.usable_area() for fp in floor_plans),
            "exterior_wall_thickness": self.exterior_wall_thickness,
            "interior_wall_thickness": self.interior_wall_thickness,
        }

        return FloorPlanSet(
            id=generate_id("fpset"),
            project_name=project_name,
            plot_boundary=plot_boundary or [],
            buildable_boundary=buildable_boundary or [],
            floor_plans=floor_plans,
            validation_report=None,
            generation_metadata=generation_metadata,
        )

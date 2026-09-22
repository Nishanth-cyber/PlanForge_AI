"""Room Builder for constructing physical GeoRoom instances.

Maintains strict separation between interior usable polygon and exterior built polygon
with deterministic wall thickness offsets.
"""

from __future__ import annotations
from typing import Optional
from shapely.geometry import Polygon

from app.geometry.exceptions import (
    InvalidRoomGeometryError,
    RoomOutOfBoundsError,
)
from app.geometry.geometry_utils import (
    from_shapely_polygon,
    is_contained_in,
    offset_polygon,
    polygon_area,
    to_shapely_polygon,
    validate_polygon_coords,
)
from app.geometry.polygon_builder import PolygonBuilder
from app.models.allocation import AllocatedRegion
from app.models.architectural_design import RoomDesign
from app.models.geometry import GeoRoom
from app.utils.ids import generate_id


class RoomBuilder:
    """Constructs physical GeoRoom from RoomDesign and AllocatedRegion."""

    @staticmethod
    def build_room(
        room_design: RoomDesign,
        allocated_region: AllocatedRegion,
        wall_thickness: float = 0.20,
    ) -> GeoRoom:
        """Construct a physical GeoRoom with dual usable and built polygons.

        Args:
            room_design: Architectural room proposal (HOW).
            allocated_region: Assigned ASAA allocated spatial region (WHERE).
            wall_thickness: Standard wall thickness in meters.

        Returns:
            GeoRoom with constructed dual polygons and preserved traceability.

        Raises:
            RoomOutOfBoundsError: If constructed room geometry extends outside allocated region.
            InvalidRoomGeometryError: If constructed geometry is degenerate.
        """
        reg_coords = allocated_region.polygon
        if not reg_coords or len(reg_coords) < 3:
            raise InvalidRoomGeometryError(
                f"Allocated region {allocated_region.id} has invalid polygon: {reg_coords}"
            )

        # 1. Construct built boundary polygon from architectural intent
        built_coords = PolygonBuilder.construct_from_intent(
            shape=room_design.intended_shape,
            region_coords=reg_coords,
            intended_dimensions=room_design.intended_dimensions,
            intended_area=room_design.intended_area_sqm,
            proposed_boundary=room_design.proposed_boundary,
        )

        # 2. Strict containment check within allocated region
        if not is_contained_in(built_coords, reg_coords, tolerance=0.05):
            raise RoomOutOfBoundsError(
                f"Room '{room_design.room_type}' (id={room_design.id}) built polygon extends "
                f"outside its allocated region (id={allocated_region.id})"
            )

        validate_polygon_coords(built_coords)

        # 3. Derive usable polygon via inward buffer
        # Inward offset: half wall thickness from boundary / centerline
        inward_offset = -(wall_thickness / 2.0)
        usable_coords = offset_polygon(built_coords, inward_offset)

        # Ensure usable polygon is valid with positive area
        usable_area = polygon_area(usable_coords)
        if usable_area <= 0.1:
            # Fallback for very small spaces: gentle inward offset
            usable_coords = offset_polygon(built_coords, -0.05)
            usable_area = polygon_area(usable_coords)

        validate_polygon_coords(usable_coords)

        geo_room = GeoRoom(
            id=generate_id("georoom"),
            room_type=room_design.room_type,
            usable_polygon=usable_coords,
            built_polygon=built_coords,
            area_sqm=round(usable_area, 2),
            walls=[],
            doors=[],
            windows=[],
            floor_number=room_design.floor_number,
            architectural_room_id=room_design.id,
            is_corridor=False,
        )

        return geo_room

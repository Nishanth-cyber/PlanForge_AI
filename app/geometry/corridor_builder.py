"""Corridor Builder for constructing physical circulation and hallway geometry.

Converts ASAA circulation regions into physical GeoRoom instances tagged as corridors.
"""

from __future__ import annotations
from typing import Optional

from app.geometry.exceptions import CorridorConstructionError
from app.geometry.geometry_utils import (
    offset_polygon,
    polygon_area,
    validate_polygon_coords,
)
from app.models.allocation import AllocatedRegion
from app.models.geometry import GeoRoom
from app.utils.ids import generate_id


class CorridorBuilder:
    """Constructs physical circulation GeoRoom instances from circulation regions."""

    @staticmethod
    def build_corridor(
        circulation_region: AllocatedRegion,
        floor_number: int = 1,
        wall_thickness: float = 0.15,
    ) -> GeoRoom:
        """Construct physical corridor GeoRoom from ASAA circulation region.

        Args:
            circulation_region: Assigned ASAA circulation allocated region.
            floor_number: Floor number.
            wall_thickness: Partition wall thickness.

        Returns:
            GeoRoom with is_corridor=True.

        Raises:
            CorridorConstructionError: If circulation region is degenerate.
        """
        if not circulation_region.polygon or len(circulation_region.polygon) < 3:
            raise CorridorConstructionError(
                f"Circulation region {circulation_region.id} has invalid polygon: {circulation_region.polygon}"
            )

        built_coords = circulation_region.polygon
        validate_polygon_coords(built_coords)

        # Usable polygon is inset
        usable_coords = offset_polygon(built_coords, -(wall_thickness / 2.0))
        usable_area = polygon_area(usable_coords)
        if usable_area <= 0.05:
            # Gentle offset fallback
            usable_coords = offset_polygon(built_coords, -0.02)
            usable_area = polygon_area(usable_coords)

        validate_polygon_coords(usable_coords)

        return GeoRoom(
            id=generate_id("geocorridor"),
            room_type=circulation_region.room_type or "circulation",
            usable_polygon=usable_coords,
            built_polygon=built_coords,
            area_sqm=round(usable_area, 2),
            walls=[],
            doors=[],
            windows=[],
            floor_number=floor_number,
            architectural_room_id=None,
            is_corridor=True,
        )

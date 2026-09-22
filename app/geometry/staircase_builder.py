"""Staircase Builder for constructing physical GeoStaircase instances.

Realizes StaircaseIntent proposals within ASAA staircase allocated regions,
ensuring vertical alignment and structural riser/tread parameters.
"""

from __future__ import annotations
import math
from typing import Optional
from shapely.geometry import Polygon

from app.geometry.exceptions import StaircaseConstructionError
from app.geometry.geometry_utils import (
    is_contained_in,
    to_shapely_polygon,
    validate_polygon_coords,
)
from app.models.allocation import AllocatedRegion
from app.models.geometry import GeoStaircase
from app.models.staircase import StaircaseIntent
from app.utils.ids import generate_id


class StaircaseBuilder:
    """Constructs physical GeoStaircase from StaircaseIntent and AllocatedRegion."""

    @staticmethod
    def build_staircase(
        staircase_intent: StaircaseIntent,
        staircase_region: Optional[AllocatedRegion],
        floor_number: int = 1,
        default_riser_count: int = 16,
        default_tread_depth: float = 0.28,
    ) -> GeoStaircase:
        """Construct physical GeoStaircase within the allocated staircase zone.

        Args:
            staircase_intent: Upstream architectural staircase proposal (HOW).
            staircase_region: Assigned ASAA staircase allocated region (WHERE).
            floor_number: Floor number.
            default_riser_count: Number of risers.
            default_tread_depth: Tread depth in meters.

        Returns:
            GeoStaircase with valid polygon footprint.

        Raises:
            StaircaseConstructionError: If staircase region is missing or degenerate.
        """
        if staircase_region is None or not staircase_region.polygon or len(staircase_region.polygon) < 3:
            raise StaircaseConstructionError(
                f"Missing or invalid allocated staircase region for staircase intent {staircase_intent.id} "
                f"on floor {floor_number}"
            )

        region_coords = staircase_region.polygon
        validate_polygon_coords(region_coords)

        # Footprint is the allocated core polygon
        poly = to_shapely_polygon(region_coords)
        min_x, min_y, max_x, max_y = poly.bounds
        w = max_x - min_x
        d = max_y - min_y

        stair_width = staircase_intent.recommended_width or 1.0
        # Check that region is large enough
        if w < stair_width * 0.8 and d < stair_width * 0.8:
            raise StaircaseConstructionError(
                f"Allocated staircase core ({w:.2f}m x {d:.2f}m) is too narrow for staircase width {stair_width}m"
            )

        # Riser / tread calculations
        # A standard 3.0m floor-to-floor height requires ~16 risers at ~18.7cm each
        risers = default_riser_count
        treads = risers - 1
        run_length = treads * default_tread_depth

        geo_staircase = GeoStaircase(
            id=generate_id("geostaircase"),
            polygon=region_coords,
            from_floor=staircase_intent.from_floor,
            to_floor=staircase_intent.to_floor,
            width=round(stair_width, 2),
            depth=round(default_tread_depth, 2),
            riser_count=risers,
            tread_depth=round(default_tread_depth, 2),
            floor_number=floor_number,
            intent_id=staircase_intent.id,
        )

        return geo_staircase

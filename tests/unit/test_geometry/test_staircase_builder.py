"""Unit tests for StaircaseBuilder: footprint, risers, treads, and alignment."""

import pytest
from app.geometry.exceptions import StaircaseConstructionError
from app.geometry.staircase_builder import StaircaseBuilder
from app.models.allocation import AllocatedRegion
from app.models.staircase import StaircaseIntent


def test_build_staircase_success():
    """Verify GeoStaircase construction within staircase region."""
    stair_region = AllocatedRegion(
        id="reg_stair",
        room_type="staircase",
        zone_type="staircase",
        floor_number=1,
        polygon=[(0.0, 0.0), (2.0, 0.0), (2.0, 4.0), (0.0, 4.0)],
    )

    intent = StaircaseIntent(
        id="intent_stair_1",
        from_floor=1,
        to_floor=2,
        stair_type="straight",
        recommended_width=1.0,
        floor_number=1,
    )

    geo_stair = StaircaseBuilder.build_staircase(intent, stair_region, floor_number=1)

    assert geo_stair.id.startswith("geostaircase_")
    assert geo_stair.from_floor == 1
    assert geo_stair.to_floor == 2
    assert geo_stair.riser_count == 16
    assert geo_stair.tread_depth == 0.28
    assert geo_stair.polygon == stair_region.polygon


def test_build_staircase_missing_region():
    """Verify StaircaseConstructionError when staircase region is None."""
    intent = StaircaseIntent(id="intent_s", from_floor=1, to_floor=2)
    with pytest.raises(StaircaseConstructionError):
        StaircaseBuilder.build_staircase(intent, None)

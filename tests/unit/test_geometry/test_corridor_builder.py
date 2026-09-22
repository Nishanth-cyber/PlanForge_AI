"""Unit tests for CorridorBuilder: circulation geometry, usable polygons, and tags."""

import pytest
from app.geometry.corridor_builder import CorridorBuilder
from app.geometry.exceptions import CorridorConstructionError
from app.models.allocation import AllocatedRegion


def test_build_corridor_success():
    """Verify corridor GeoRoom construction."""
    circ_reg = AllocatedRegion(
        id="reg_circ",
        room_type="circulation",
        zone_type="circulation",
        floor_number=1,
        polygon=[(2.0, 0.0), (4.0, 0.0), (4.0, 8.0), (2.0, 8.0)],
    )

    geo_corridor = CorridorBuilder.build_corridor(circ_reg, floor_number=1)

    assert geo_corridor.is_corridor is True
    assert geo_corridor.room_type == "circulation"
    assert geo_corridor.floor_number == 1
    assert geo_corridor.area_sqm > 0
    assert len(geo_corridor.built_polygon) == 4
    assert len(geo_corridor.usable_polygon) == 4


def test_build_corridor_invalid_polygon():
    """Verify CorridorConstructionError for degenerate polygon."""
    circ_reg = AllocatedRegion(
        id="reg_circ_bad",
        polygon=[(0.0, 0.0), (1.0, 1.0)],
    )
    with pytest.raises(CorridorConstructionError):
        CorridorBuilder.build_corridor(circ_reg)

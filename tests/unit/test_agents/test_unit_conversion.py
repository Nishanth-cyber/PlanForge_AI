"""Unit tests for app.utils.units — area and dimension conversion utilities."""

import pytest
from app.utils.units import parse_area_sqm, parse_dimension_m


# ---------------------------------------------------------------------------
# parse_area_sqm
# ---------------------------------------------------------------------------

class TestParseAreaSqm:

    def test_sqm_passthrough_integer(self):
        assert parse_area_sqm("200 sqm") == pytest.approx(200.0)

    def test_sqm_passthrough_float(self):
        assert parse_area_sqm("185.5 sqm") == pytest.approx(185.5)

    def test_sqm_abbreviated_m2(self):
        assert parse_area_sqm("150m²") == pytest.approx(150.0)

    def test_sqm_long_form(self):
        assert parse_area_sqm("300 square metres") == pytest.approx(300.0)

    def test_sqft_conversion(self):
        result = parse_area_sqm("2000 sqft")
        assert result == pytest.approx(2000 * 0.09290304, rel=1e-4)

    def test_sqft_space(self):
        result = parse_area_sqm("2152 sq ft")
        assert result == pytest.approx(2152 * 0.09290304, rel=1e-4)

    def test_marla_single(self):
        result = parse_area_sqm("1 marla")
        assert result == pytest.approx(20.9032, rel=1e-3)

    def test_marla_five(self):
        result = parse_area_sqm("5 marla")
        assert result == pytest.approx(5 * 20.9032, rel=1e-3)

    def test_marla_plural(self):
        result = parse_area_sqm("10 marlas")
        assert result == pytest.approx(10 * 20.9032, rel=1e-3)

    def test_kanal(self):
        result = parse_area_sqm("1 kanal")
        assert result == pytest.approx(418.064, rel=1e-3)

    def test_acre(self):
        result = parse_area_sqm("0.5 acres")
        assert result == pytest.approx(0.5 * 4046.8564, rel=1e-3)

    def test_hectare(self):
        result = parse_area_sqm("1 hectare")
        assert result == pytest.approx(10_000.0, rel=1e-3)

    def test_ha_abbreviation(self):
        result = parse_area_sqm("0.25 ha")
        assert result == pytest.approx(2500.0, rel=1e-3)

    def test_sqyd_conversion(self):
        result = parse_area_sqm("100 sq yd")
        assert result == pytest.approx(100 * 0.83612736, rel=1e-4)

    def test_unrecognised_string_returns_none(self):
        assert parse_area_sqm("unknown measurement") is None

    def test_empty_string_returns_none(self):
        assert parse_area_sqm("") is None

    def test_embedded_in_sentence(self):
        result = parse_area_sqm("The plot area is 300 sqm with setbacks")
        assert result == pytest.approx(300.0)

    def test_sqft_in_context(self):
        result = parse_area_sqm("plot size: 1800 sq ft")
        assert result == pytest.approx(1800 * 0.09290304, rel=1e-4)


# ---------------------------------------------------------------------------
# parse_dimension_m
# ---------------------------------------------------------------------------

class TestParseDimensionM:

    def test_metres_passthrough_integer(self):
        assert parse_dimension_m("15m") == pytest.approx(15.0)

    def test_metres_passthrough_float(self):
        assert parse_dimension_m("15.5 m") == pytest.approx(15.5)

    def test_metres_long_form(self):
        assert parse_dimension_m("20 meters") == pytest.approx(20.0)

    def test_metres_long_form_british(self):
        assert parse_dimension_m("20 metres") == pytest.approx(20.0)

    def test_feet_conversion(self):
        result = parse_dimension_m("50 ft")
        assert result == pytest.approx(50 * 0.3048, rel=1e-4)

    def test_feet_long_form(self):
        result = parse_dimension_m("60 feet")
        assert result == pytest.approx(60 * 0.3048, rel=1e-4)

    def test_feet_apostrophe(self):
        result = parse_dimension_m("30'")
        assert result == pytest.approx(30 * 0.3048, rel=1e-4)

    def test_cm_conversion(self):
        result = parse_dimension_m("300 cm")
        assert result == pytest.approx(3.0, rel=1e-4)

    def test_inches_only(self):
        result = parse_dimension_m("6 in")
        assert result == pytest.approx(6 * 0.0254, rel=1e-4)

    def test_unrecognised_returns_none(self):
        assert parse_dimension_m("no dimension here") is None

    def test_empty_returns_none(self):
        assert parse_dimension_m("") is None

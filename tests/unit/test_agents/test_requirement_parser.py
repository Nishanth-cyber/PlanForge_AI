"""Unit tests for app.agents.requirement_agent.parser — RequirementParser."""

import pytest
from app.agents.requirement_agent.parser import RequirementParser


@pytest.fixture
def parser():
    return RequirementParser()


class TestPlotParsing:
    def test_dimensions_metres_x(self, parser):
        reqs = parser.parse("Plot size 15m x 20m, north-facing, 2 floors")
        assert reqs.plot_dimensions == (15.0, 20.0)
        assert reqs.plot_area_sqm == pytest.approx(300.0)

    def test_dimensions_feet_by(self, parser):
        reqs = parser.parse("30 feet by 40 feet plot, single storey")
        assert reqs.plot_dimensions is not None
        w, d = reqs.plot_dimensions
        assert w == pytest.approx(30 * 0.3048, rel=1e-3)
        assert d == pytest.approx(40 * 0.3048, rel=1e-3)

    def test_dimensions_apostrophe_notation(self, parser):
        reqs = parser.parse("25' x 50' plot")
        assert reqs.plot_dimensions is not None
        w, d = reqs.plot_dimensions
        assert w == pytest.approx(25 * 0.3048, rel=1e-3)
        assert d == pytest.approx(50 * 0.3048, rel=1e-3)

    def test_standalone_area_sqm(self, parser):
        reqs = parser.parse("Plot area: 250 sqm, single storey")
        assert reqs.plot_area_sqm == pytest.approx(250.0)

    def test_standalone_area_marla(self, parser):
        reqs = parser.parse("5 marla plot, 2 floors")
        assert reqs.plot_area_sqm == pytest.approx(5 * 20.9032, rel=1e-3)

    def test_orientation_extraction(self, parser):
        assert parser.parse("north-facing house").orientation == "north"
        assert parser.parse("facing east on plot").orientation == "east"
        assert parser.parse("southwest facing plot").orientation == "southwest"

    def test_entrance_facing(self, parser):
        assert parser.parse("main entrance facing north").entrance_facing == "north"
        assert parser.parse("entrance from the east").entrance_facing == "east"

    def test_entrance_room_type(self, parser):
        assert parser.parse("entrance leads to living room").entrance_room_type == "living"
        assert parser.parse("main entrance to foyer").entrance_room_type == "circulation"

    def test_setbacks_extraction(self, parser):
        reqs = parser.parse("front setback: 3m, rear setback: 2m, left setback: 1.5m")
        assert reqs.setbacks.get("front") == 3.0
        assert reqs.setbacks.get("rear") == 2.0
        assert reqs.setbacks.get("left") == 1.5

    def test_plot_polygon_coordinates(self, parser):
        text = "Plot shape: (0, 0), (15, 0), (15, 20), (0, 20)"
        reqs = parser.parse(text)
        assert reqs.plot_shape == ((0.0, 0.0), (15.0, 0.0), (15.0, 20.0), (0.0, 20.0))


class TestFloorCountParsing:
    def test_g_plus_one(self, parser):
        assert parser.extract_target_floors("G+1 house with 3 bedrooms") == 2

    def test_g_plus_two(self, parser):
        assert parser.extract_target_floors("G+2 villa") == 3

    def test_two_storey(self, parser):
        assert parser.extract_target_floors("two-storey building") == 2
        assert parser.extract_target_floors("2 storey home") == 2
        assert parser.extract_target_floors("double storey house") == 2

    def test_single_storey(self, parser):
        assert parser.extract_target_floors("single-storey bungalow") == 1

    def test_floors_digit_and_word(self, parser):
        assert parser.extract_target_floors("3 floors total") == 3
        assert parser.extract_target_floors("two floors") == 2


class TestRoomExtractionAndAreaIsolation:
    def test_multiple_rooms_with_different_areas(self, parser):
        text = """
        Master bedroom 150 sq ft
        Bedroom 120 sq ft
        Study 80 sq ft
        """
        rooms = parser._extract_rooms_from_text(text)
        room_dict = {r.room_type: r for r in rooms}

        assert "master_bedroom" in room_dict
        assert "bedroom" in room_dict
        assert "study" in room_dict

        # Crucial bug fix: 150 sq ft must NOT bleed to other rooms!
        sqft_to_sqm = 0.09290304
        assert room_dict["master_bedroom"].preferred_area_sqm == pytest.approx(150 * sqft_to_sqm, rel=1e-3)
        assert room_dict["bedroom"].preferred_area_sqm == pytest.approx(120 * sqft_to_sqm, rel=1e-3)
        assert room_dict["study"].preferred_area_sqm == pytest.approx(80 * sqft_to_sqm, rel=1e-3)

    def test_area_range_extraction(self, parser):
        text = "Living room between 200 and 300 sq ft"
        rooms = parser._extract_rooms_from_text(text)
        assert len(rooms) == 1
        lr = rooms[0]
        sqft_to_sqm = 0.09290304
        assert lr.min_area_sqm == pytest.approx(200 * sqft_to_sqm, rel=1e-3)
        assert lr.max_area_sqm == pytest.approx(300 * sqft_to_sqm, rel=1e-3)
        assert lr.preferred_area_sqm == pytest.approx(250 * sqft_to_sqm, rel=1e-3)

    def test_min_and_max_area(self, parser):
        text = "Kitchen min 100 sq ft, Dining max 150 sq ft"
        rooms = parser._extract_rooms_from_text(text)
        room_dict = {r.room_type: r for r in rooms}
        sqft_to_sqm = 0.09290304
        assert room_dict["kitchen"].min_area_sqm == pytest.approx(100 * sqft_to_sqm, rel=1e-3)
        assert room_dict["dining"].max_area_sqm == pytest.approx(150 * sqft_to_sqm, rel=1e-3)

    def test_attached_bathroom_linkage(self, parser):
        text = "Master bedroom with attached bathroom"
        rooms = parser._extract_rooms_from_text(text)
        room_dict = {r.room_type: r for r in rooms}
        assert "master_bedroom" in room_dict
        assert "bathroom" in room_dict
        assert room_dict["bathroom"].attached_to == "master_bedroom"
        assert "bathroom" in room_dict["master_bedroom"].adjacency

    def test_bhk_expansion(self, parser):
        reqs = parser.parse("3BHK house, 20m x 30m plot")
        assert len(reqs.floors) == 1
        f1_rooms = {r.room_type: r.min_count for r in reqs.floors[0].room_requirements}
        assert f1_rooms.get("bedroom") == 3
        assert f1_rooms.get("living") == 1
        assert f1_rooms.get("kitchen") == 1


class TestRelationships:
    def test_adjacency_and_separation(self, parser):
        text = "Kitchen next to dining. Garage away from bedroom."
        rooms = parser._extract_rooms_from_text(text)
        room_dict = {r.room_type: r for r in rooms}
        assert "dining" in room_dict["kitchen"].adjacency
        assert "kitchen" in room_dict["dining"].adjacency
        assert "bedroom" in room_dict["garage"].separation
        assert "garage" in room_dict["bedroom"].separation

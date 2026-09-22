"""Unit tests for app.agents.requirement_agent.normalizer — RequirementNormalizer."""

import pytest
from app.agents.requirement_agent.normalizer import RequirementNormalizer


@pytest.fixture
def normalizer():
    return RequirementNormalizer()


class TestSynonymNormalization:
    def test_bedroom_synonyms(self, normalizer):
        assert normalizer.canonical_room_type("bed") == "bedroom"
        assert normalizer.canonical_room_type("bedroom") == "bedroom"
        assert normalizer.canonical_room_type("bed room") == "bedroom"
        assert normalizer.canonical_room_type("guest room") == "bedroom"
        assert normalizer.canonical_room_type("kids room") == "bedroom"

    def test_master_bedroom_synonyms(self, normalizer):
        assert normalizer.canonical_room_type("master bed") == "master_bedroom"
        assert normalizer.canonical_room_type("master bedroom") == "master_bedroom"
        assert normalizer.canonical_room_type("primary bedroom") == "master_bedroom"

    def test_bathroom_synonyms(self, normalizer):
        assert normalizer.canonical_room_type("washroom") == "bathroom"
        assert normalizer.canonical_room_type("toilet") == "bathroom"
        assert normalizer.canonical_room_type("wc") == "bathroom"
        assert normalizer.canonical_room_type("bath room") == "bathroom"
        assert normalizer.canonical_room_type("attached bath") == "bathroom"
        assert normalizer.canonical_room_type("powder room") == "bathroom"

    def test_living_synonyms(self, normalizer):
        assert normalizer.canonical_room_type("drawing room") == "living"
        assert normalizer.canonical_room_type("lounge") == "living"
        assert normalizer.canonical_room_type("living room") == "living"
        assert normalizer.canonical_room_type("sitting room") == "living"

    def test_study_synonyms(self, normalizer):
        assert normalizer.canonical_room_type("study") == "study"
        assert normalizer.canonical_room_type("study room") == "study"
        assert normalizer.canonical_room_type("home office") == "study"
        assert normalizer.canonical_room_type("library") == "study"


class TestFloorNormalization:
    def test_ground_floor(self, normalizer):
        assert normalizer.normalize_floor_number("ground") == 1
        assert normalizer.normalize_floor_number("ground floor") == 1
        assert normalizer.normalize_floor_number("gf") == 1
        assert normalizer.normalize_floor_number("first") == 1
        assert normalizer.normalize_floor_number("1st") == 1
        assert normalizer.normalize_floor_number("1st floor") == 1
        assert normalizer.normalize_floor_number("floor 1") == 1

    def test_second_floor(self, normalizer):
        assert normalizer.normalize_floor_number("second") == 2
        assert normalizer.normalize_floor_number("second floor") == 2
        assert normalizer.normalize_floor_number("2nd") == 2
        assert normalizer.normalize_floor_number("2nd floor") == 2
        assert normalizer.normalize_floor_number("floor 2") == 2
        assert normalizer.normalize_floor_number("upper floor") == 2
        assert normalizer.normalize_floor_number("upstairs") == 2

    def test_third_floor(self, normalizer):
        assert normalizer.normalize_floor_number("third") == 3
        assert normalizer.normalize_floor_number("3rd floor") == 3
        assert normalizer.normalize_floor_number("floor 3") == 3


class TestNumberWordNormalization:
    def test_word_numbers(self, normalizer):
        assert normalizer.normalize_count("one") == 1
        assert normalizer.normalize_count("two") == 2
        assert normalizer.normalize_count("three") == 3
        assert normalizer.normalize_count("four") == 4
        assert normalizer.normalize_count("a") == 1
        assert normalizer.normalize_count("an") == 1
        assert normalizer.normalize_count("5") == 5

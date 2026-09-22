"""Unit tests for Event and EventLog data contracts."""

from app.models.events import Event, EventLog


def test_event_creation():
    """Test Event attributes across stage, type, and execution time."""
    event = Event(
        stage="asaa",
        event_type="REGIONS_ALLOCATED",
        message="Allocated 5 spatial regions on Floor 1",
        data={"floor_number": 1, "region_count": 5},
        execution_time_ms=42.5,
    )
    assert event.id is not None
    assert event.stage == "asaa"
    assert event.event_type == "REGIONS_ALLOCATED"
    assert event.data["region_count"] == 5
    assert event.execution_time_ms == 42.5


def test_event_log_filtering_and_clear():
    """Test EventLog addition, stage filtering, type filtering, and clearing."""
    log = EventLog()
    log.add_event(event_type="REQUIREMENTS_PARSED", stage="requirement", message="Parsed brief")
    log.add_event(event_type="REGIONS_ALLOCATED", stage="asaa", message="Allocated regions")
    log.add_event(event_type="DESIGN_PROPOSED", stage="architectural_llm", message="Proposed doors and windows")
    log.add_event(event_type="REGIONS_ALLOCATED", stage="asaa", message="Allocated floor 2")

    assert len(log.events) == 4
    asaa_events = log.get_events_by_stage("asaa")
    assert len(asaa_events) == 2

    llm_events = log.get_events_by_stage("architectural_llm")
    assert len(llm_events) == 1

    alloc_events = log.get_events_by_type("REGIONS_ALLOCATED")
    assert len(alloc_events) == 2

    log.clear()
    assert len(log.events) == 0

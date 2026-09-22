"""Unit tests for explainability data contracts, events, and serialization."""

import json
import pytest

from app.explainability.models import (
    AlternativeTrace,
    DecisionEvent,
    DecisionTrace,
    DecisionType,
    EntityTraceChain,
    ProvenanceSource,
    StageName,
    StageTrace,
)


def test_decision_trace_creation():
    """Verify DecisionTrace initialization with defaults and custom properties."""
    trace = DecisionTrace(project_name="Sunset Villa")
    assert trace.project_name == "Sunset Villa"
    assert trace.trace_id.startswith("trace_")
    assert len(trace.stages) == 0
    assert len(trace.alternatives) == 0
    assert len(trace.entity_chains) == 0


def test_decision_event_creation():
    """Verify DecisionEvent fields and defaults."""
    evt = DecisionEvent(
        stage=StageName.PLANNING.value,
        event_type=DecisionType.ROOM_CLASSIFIED.value,
        source=ProvenanceSource.PLANNING_AGENT.value,
        entity_id="room_101",
        entity_type="room",
        floor_number=1,
        reason="Categorized as social space",
        evidence={"room_type": "living", "category": "social"},
        status="success",
    )
    assert evt.event_id.startswith("evt_")
    assert evt.stage == "planning"
    assert evt.event_type == "room_classified"
    assert evt.source == "planning_agent"
    assert evt.entity_id == "room_101"
    assert evt.status == "success"


def test_stage_classification():
    """Verify all 9 pipeline stages exist in StageName enum."""
    expected = [
        "requirement",
        "planning",
        "asaa_allocation",
        "architectural_design",
        "geometry",
        "validation",
        "refinement",
        "diversity",
        "final_selection",
    ]
    for s in expected:
        assert StageName(s) is not None


def test_provenance_source_classification():
    """Verify all authoritative decision sources exist in ProvenanceSource enum."""
    expected = [
        "user",
        "rule",
        "planning_agent",
        "asaa",
        "architectural_llm",
        "geometry_engine",
        "validator",
        "refinement_llm",
        "diversity_engine",
        "system_derived",
    ]
    for src in expected:
        assert ProvenanceSource(src) is not None


def test_json_serialization_and_deserialization():
    """Verify round-trip serialization of DecisionTrace to/from dict and JSON."""
    evt1 = DecisionEvent(
        stage=StageName.REQUIREMENT.value,
        event_type=DecisionType.REQUIREMENT_PARSED.value,
        source=ProvenanceSource.USER.value,
        entity_id="room_req_1",
        entity_type="room",
        floor_number=1,
        reason="User requested 1 living room",
        evidence={"room_type": "living", "min_count": 1},
    )
    stage = StageTrace(
        stage_name=StageName.REQUIREMENT.value,
        events=[evt1],
        summary="Requirements summary",
    )
    alt = AlternativeTrace(
        alternative_id="alt_1",
        index=1,
        strategy="social_centric",
        status="validated",
        characteristics=["direct social sequence", "spacious living"],
    )
    chain = EntityTraceChain(
        entity_id="room_req_1",
        entity_type="room",
        room_type="living",
        floor_number=1,
        events=[evt1],
    )
    trace = DecisionTrace(
        project_name="Highland Home",
        stages=[stage],
        alternatives=[alt],
        entity_chains={"room_req_1": chain},
    )

    # 1. to_dict / from_dict
    d = trace.to_dict()
    assert isinstance(d, dict)
    assert d["project_name"] == "Highland Home"
    assert len(d["stages"]) == 1
    assert len(d["alternatives"]) == 1
    assert "room_req_1" in d["entity_chains"]

    reconstructed = DecisionTrace.from_dict(d)
    assert reconstructed.project_name == trace.project_name
    assert len(reconstructed.stages) == 1
    assert reconstructed.stages[0].events[0].entity_id == "room_req_1"

    # 2. to_json / from_json
    json_str = trace.to_json()
    assert isinstance(json_str, str)
    from_json_trace = DecisionTrace.from_json(json_str)
    assert from_json_trace.project_name == "Highland Home"
    assert len(from_json_trace.alternatives) == 1
    assert from_json_trace.alternatives[0].strategy == "social_centric"


def test_model_dump_pydantic_aliases():
    """Verify model_dump and model_dump_json Pydantic convention aliases."""
    trace = DecisionTrace(project_name="Model Dump Test")
    d = trace.model_dump()
    assert isinstance(d, dict)
    assert d["project_name"] == "Model Dump Test"

    j = trace.model_dump_json()
    assert isinstance(j, str)
    assert "Model Dump Test" in j


def test_no_hidden_chain_of_thought_storage():
    """Verify that events strictly reject or omit internal CoT keys."""
    forbidden_keys = {"chain_of_thought", "cot", "scratchpad", "deliberation", "internal_reasoning", "raw_prompt_tokens"}
    evt = DecisionEvent(
        stage=StageName.ARCHITECTURAL_DESIGN.value,
        event_type=DecisionType.ROOM_SHAPE_SELECTED.value,
        source=ProvenanceSource.ARCHITECTURAL_LLM.value,
        entity_id="room_1",
        reason="Rectangular room proportion suited to social zone region.",
        evidence={"shape": "rectangular", "dims": (4.0, 5.0)},
    )
    d = evt.to_dict()
    for fk in forbidden_keys:
        assert fk not in d
        assert fk not in d["evidence"]
        assert fk not in d["constraints"]


def test_incomplete_trace_handling():
    """Verify DecisionTrace handles empty or partial stages without errors."""
    trace = DecisionTrace()
    assert trace.get_stage("requirement") is None
    assert trace.get_events_by_stage("planning") == []
    assert trace.get_events_by_entity("unknown_id") == []
    assert trace.get_events_by_type("door_intent_created") == []
    assert trace.get_entity_chain("unknown_id") is None
    assert trace.to_json() is not None

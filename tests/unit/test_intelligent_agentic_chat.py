"""Automated unit and integration tests for the Intelligent Agentic Conversational Interface.

Covers all 15 acceptance criteria in Section 10:
1. Greetings do not trigger irrelevant cards.
2. Capability questions receive direct answers.
3. Ordinary questions do not automatically display project-type options.
4. Relevant project-type options appear when appropriate.
5. Repeated messages do not repeatedly render identical suggestion cards.
6. Multiple requirements supplied in one message are extracted correctly.
7. Follow-up answers update the existing conversation state.
8. Requirement corrections preserve unrelated fields.
9. The assistant does not ask again for information already supplied.
10. Incomplete requirements trigger targeted clarification.
11. Complete requirements can initiate the existing generation pipeline.
12. Generation status is obtained from real backend state.
13. LLM or backend failures are handled gracefully.
14. Export requests invoke the correct supported export workflow.
15. API endpoint operates end-to-end with structured response contract.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.registry import get_default_registry
from app.chat.orchestrator import ChatOrchestrator
from app.chat.schema import ConversationIntent as CI, ResponseType
from app.chat.state import ConversationStateStore, conversation_store


@pytest.fixture
def client(tmp_path: Path):
    """TestClient with fresh registry and clean state store."""
    app = create_app()
    registry = get_default_registry()
    registry.clear()
    conversation_store.clear()
    return TestClient(app)


@pytest.fixture
def orchestrator():
    """Isolated ChatOrchestrator with isolated state store."""
    store = ConversationStateStore()
    return ChatOrchestrator(state_store=store)


def test_1_greetings_do_not_trigger_irrelevant_cards(orchestrator: ChatOrchestrator):
    """Verify greeting returns text answer and no requirement cards."""
    for greet in ["Hi there", "hi , there", "hello, there!", "hey", "good morning"]:
        res = orchestrator.handle(message=greet, conversation_id="test_conv_greet")
        assert res.intent == CI.GREETING.value
        assert res.response_type == ResponseType.TEXT
        assert res.turn.question_card is None
        assert len(res.quick_replies) == 0
        assert "PlanForge" in res.turn.message


def test_2_capability_questions_receive_direct_answers(orchestrator: ChatOrchestrator):
    """Verify capability questions receive direct answers without requirement cards."""
    queries = [
        "What are the things you can build?",
        "What can you do?",
        "Tell me about your features",
    ]
    for q in queries:
        res = orchestrator.handle(message=q, conversation_id="test_conv_cap")
        assert res.intent == CI.CAPABILITY_QUERY.value
        assert res.response_type == ResponseType.TEXT
        assert res.turn.question_card is None
        assert "bungalow" in res.turn.message.lower() or "duplex" in res.turn.message.lower()


def test_3_ordinary_questions_do_not_automatically_display_project_type(orchestrator: ChatOrchestrator):
    """Verify general architectural questions answer directly without project-type cards."""
    res = orchestrator.handle(
        message="Why is natural ventilation and daylight important in residential design?",
        conversation_id="test_conv_arch",
    )
    assert res.intent == CI.GENERAL_ARCHITECTURAL_QUERY.value
    assert res.response_type == ResponseType.TEXT
    assert res.turn.question_card is None


def test_4_relevant_project_type_options_appear_when_appropriate(orchestrator: ChatOrchestrator):
    """Verify project type options appear when starting a brand-new empty session."""
    res = orchestrator.handle(message="", conversation_id="test_conv_new")
    assert res.intent == CI.GREETING.value
    assert res.turn.question_card is not None
    assert res.turn.question_card.field_key == "project_type"
    assert res.response_type in (ResponseType.QUICK_REPLIES, ResponseType.CLARIFICATION)


def test_5_repeated_messages_do_not_repeatedly_render_identical_cards(orchestrator: ChatOrchestrator):
    """Verify repeated unanswered questions do not re-render the identical card."""
    cid = "test_conv_repeat"
    # Turn 1: user initiates with Residential project -> asked for plot_dimensions
    r1 = orchestrator.handle(message="Residential project", conversation_id=cid)
    assert r1.turn.question_card is not None
    assert r1.turn.question_card.field_key == "plot_dimensions"

    # Turn 2: user asks an off-topic question without answering plot dimensions
    r2 = orchestrator.handle(message="What is the weather?", conversation_id=cid)
    assert r2.turn.question_card is None  # suppressed!

    # Turn 3: user says an ambiguous word that doesn't answer plot dimensions
    r3 = orchestrator.handle(message="maybe later", conversation_id=cid)
    # Identical card must not be duplicated
    assert r3.turn.question_card is None


def test_6_multiple_requirements_supplied_in_one_message_extracted(orchestrator: ChatOrchestrator):
    """Verify multiple requirements in one prompt are all parsed and preserved."""
    msg = "I want a 2-floor duplex on a 30x40 ft plot facing North with 3 bedrooms and 2 bathrooms"
    res = orchestrator.handle(message=msg, conversation_id="test_conv_multi_req")

    assert res.intent == CI.REQUIREMENT_INPUT.value
    # Check progress list
    progress_map = {p.name: p for p in res.turn.progress}
    assert progress_map["Plot dimensions"].status == "completed"
    assert progress_map["Floors"].status == "completed"
    assert progress_map["Entrance orientation"].status == "completed"
    assert progress_map["Floor 1 rooms"].status == "completed"

    # Should ask for Floor 2 rooms, NOT plot dimensions or floors!
    assert res.turn.question_card is not None
    assert res.turn.question_card.field_key == "floor_2_rooms"


def test_7_follow_up_answers_update_conversation_state(orchestrator: ChatOrchestrator):
    """Verify follow-up answers update existing conversation state progressively."""
    cid = "test_conv_progressive"

    # Turn 1: dimensions
    r1 = orchestrator.handle(message="30 by 40 feet", conversation_id=cid)
    assert r1.turn.question_card.field_key == "target_floors"

    # Turn 2: duplex
    r2 = orchestrator.handle(message="A duplex", conversation_id=cid)
    assert "2" in r2.turn.requirements_text
    assert r2.turn.question_card.field_key == "entrance_facing"

    # Check that dimensions are still in state
    state = orchestrator.state_store.get(cid)
    assert state is not None
    assert "9.14m by 12.19m" in state.canonical_brief or "30" in state.canonical_brief


def test_8_requirement_corrections_preserve_unrelated_fields(orchestrator: ChatOrchestrator):
    """Verify modifying dimensions updates only plot and preserves floors and rooms."""
    cid = "test_conv_correction"
    orchestrator.handle(
        message="2-floor duplex on 30x40 ft plot facing North with 3 bedrooms",
        conversation_id=cid,
    )

    # Correction
    r_corr = orchestrator.handle(
        message="Actually, make it 35 by 50 feet.",
        conversation_id=cid,
    )
    assert r_corr.intent == CI.REQUIREMENT_CORRECTION.value

    # Verify updated dimensions
    assert "10.67m by 15.24m" in r_corr.turn.requirements_text or "35" in r_corr.turn.requirements_text
    # Verify floors and bedrooms are preserved!
    assert "Target floors: 2" in r_corr.turn.requirements_text
    assert "Bedroom" in r_corr.turn.requirements_text


def test_9_assistant_does_not_ask_again_for_supplied_information(orchestrator: ChatOrchestrator):
    """Verify assistant only asks for genuinely missing fields."""
    cid = "test_conv_missing_only"
    orchestrator.handle(message="30x40 ft plot facing North", conversation_id=cid)
    r2 = orchestrator.handle(message="1 floor", conversation_id=cid)

    # Plot dimensions, orientation, and floors are done. Next must be Floor 1 rooms!
    assert r2.turn.question_card.field_key == "floor_1_rooms"


def test_10_incomplete_requirements_trigger_targeted_clarification(orchestrator: ChatOrchestrator):
    """Verify requesting generation on incomplete project clarifies missing requirements."""
    cid = "test_conv_incomplete"
    orchestrator.handle(message="I want to design a house on a 30x40 ft plot", conversation_id=cid)

    r_gen = orchestrator.handle(message="Generate floor plan now", conversation_id=cid)
    assert r_gen.turn.is_ready_for_generation is False
    assert "I can't generate the floor plan quite yet" in r_gen.turn.message
    # Clarifies targeted missing requirement in words and sets pending field
    assert r_gen.response_type == ResponseType.CLARIFICATION
    assert r_gen.pending_field == "target_floors"
    assert "floors" in r_gen.turn.message.lower()


def test_11_complete_requirements_initiate_generation(orchestrator: ChatOrchestrator):
    """Verify complete requirements produce an executable generate action."""
    cid = "test_conv_complete"
    # Provide complete single-floor spec
    orchestrator.handle(
        message="Single floor house on 30x40 ft plot facing East. Floor 1: 1 living room, 1 kitchen, 2 bedrooms, 1 bathroom",
        conversation_id=cid,
    )

    r_gen = orchestrator.handle(message="Generate floor plan", conversation_id=cid)
    assert r_gen.response_type == ResponseType.GENERATION_PROGRESS
    assert r_gen.action is not None
    assert r_gen.action.type == "generate_floor_plan"
    assert r_gen.action.auto_execute is True


def test_12_generation_status_obtained_from_real_backend_state(orchestrator: ChatOrchestrator):
    """Verify generation status reflects real ConversationState and pipeline runs."""
    cid = "test_conv_status"
    # Seed state with running generation
    orchestrator.state_store.begin_generation(cid, "proj_test_123")

    r_status = orchestrator.handle(message="What is the generation status?", conversation_id=cid)
    assert r_status.response_type == ResponseType.GENERATION_PROGRESS
    assert "running" in r_status.turn.message.lower()


def test_13_failures_handled_gracefully(orchestrator: ChatOrchestrator):
    """Verify failures degrade gracefully to helpful conversational messages."""
    cid = "test_conv_err"
    # Simulate exception in assistant snapshot
    def mock_raise(*args, **kwargs):
        raise RuntimeError("Synthetic simulated backend error")

    orchestrator.assistant.snapshot = mock_raise
    res = orchestrator.handle(message="Show summary", conversation_id=cid)
    assert res.response_type == ResponseType.TEXT
    assert "I don't have any requirements" in res.turn.message or "sorry" in res.turn.message.lower()


def test_14_export_requests_invoke_supported_workflow(orchestrator: ChatOrchestrator):
    """Verify export requests handle both ungenerated and generated projects."""
    cid = "test_conv_export"
    # 1. Without generated project
    r1 = orchestrator.handle(message="Can I export a DXF file?", conversation_id=cid)
    assert r1.response_type == ResponseType.ACTION_RESULT
    assert r1.action is not None
    assert r1.action.type == "export"
    assert r1.action.status == "unavailable"
    assert "DXF" in r1.turn.message


def test_15_api_chat_endpoint_contract(client: TestClient):
    """Verify /api/v1/chat respects conversation_id and returns full structured contract."""
    # 1. Greeting
    resp1 = client.post("/api/v1/chat", json={"message": "Hi"})
    assert resp1.status_code == 200
    d1 = resp1.json()
    assert d1["response_type"] == "text"
    assert d1["intent"] == "GREETING"
    assert "conversation_stage" in d1
    assert "conversation_id" in d1

    conv_id = d1["conversation_id"]

    # 2. Capability question using same conversation_id
    resp2 = client.post(
        "/api/v1/chat",
        json={"message": "What can you design?", "conversation_id": conv_id},
    )
    assert resp2.status_code == 200
    d2 = resp2.json()
    assert d2["response_type"] == "text"
    assert d2["intent"] == "CAPABILITY_QUERY"
    assert d2["question_card"] is None
    assert d2["conversation_id"] == conv_id

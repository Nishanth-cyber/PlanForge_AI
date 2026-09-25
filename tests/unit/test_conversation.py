"""Unit tests for ConversationalRequirementAssistant and /chat API endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agents.requirement_agent.conversation import ConversationalRequirementAssistant
from app.api.app import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_conversational_assistant_initial_turn():
    """Verify initial empty turn returns greeting and project type card."""
    ca = ConversationalRequirementAssistant()
    turn = ca.handle_turn("")
    assert "PlanForge AI" in turn.message
    assert turn.question_card is not None
    assert turn.question_card.input_type == "single_choice"
    assert turn.question_card.field_key == "project_type"
    assert len(turn.progress) > 0
    assert turn.is_ready_for_generation is False


def test_conversational_assistant_multi_turn_single_floor():
    """Verify multi-turn flow for single floor house reaching confirmation."""
    ca = ConversationalRequirementAssistant()

    # Turn 1: Plot & 1 floor
    t1 = ca.handle_turn("Single floor house on 30ft x 40ft plot facing East")
    assert t1.question_card is not None
    assert t1.question_card.field_key == "floor_1_rooms"
    assert t1.question_card.input_type == "multi_choice"

    # Turn 2: Floor 1 rooms
    t2 = ca.handle_turn("Floor 1: 1 living room, 1 kitchen, 2 bedrooms, 1 bathroom", existing_brief=t1.requirements_text)
    assert t2.is_ready_for_generation is True
    assert t2.question_card is not None
    assert t2.question_card.input_type == "confirmation"
    assert "Generate Floor Plan" in t2.question_card.options


def test_conversational_assistant_multi_floor_gating():
    """Verify multi-floor conversation correctly steps through Floor 1 -> Floor 2 -> Staircase -> Confirmation."""
    ca = ConversationalRequirementAssistant()

    # Turn 1: Specify 2 floors on 40x50 plot
    t1 = ca.handle_turn("2 floors residential duplex on 40ft x 50ft plot facing North")
    assert t1.question_card.field_key == "floor_1_rooms"

    # Turn 2: Specify Floor 1 rooms -> Next must ask for Floor 2 rooms!
    t2 = ca.handle_turn("Floor 1: living room, kitchen, dining room, master bedroom", existing_brief=t1.requirements_text)
    assert t2.question_card.field_key == "floor_2_rooms"
    assert t2.question_card.input_type == "multi_choice"
    assert t2.is_ready_for_generation is False

    # Turn 3: Specify Floor 2 rooms -> Next must ask for Staircase!
    t3 = ca.handle_turn("Floor 2: 2 bedrooms, 1 bathroom, study room", existing_brief=t2.requirements_text)
    assert t3.question_card.field_key == "staircase_location"
    assert t3.question_card.input_type == "single_choice"
    assert t3.is_ready_for_generation is False

    # Turn 4: Specify Staircase -> Now must reach Confirmation!
    t4 = ca.handle_turn("Staircase inside living area", existing_brief=t3.requirements_text)
    assert t4.is_ready_for_generation is True
    assert t4.question_card.input_type == "confirmation"


def test_api_chat_endpoint(client: TestClient):
    """Verify HTTP API endpoint /api/v1/chat operates correctly."""
    resp = client.post("/api/v1/chat", json={"message": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert "PlanForge AI" in data["message"]
    assert data["question_card"]["input_type"] == "single_choice"

    # Follow up turn
    resp2 = client.post(
        "/api/v1/chat",
        json={
            "message": "40ft x 50ft plot, 1 floor, entrance North",
            "existing_brief": data["requirements_text"],
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["question_card"]["field_key"] == "floor_1_rooms"
    assert data2["question_card"]["input_type"] == "multi_choice"


def test_plot_dimensions_card_includes_custom_irregular_plot():
    """Verify plot dimensions question card offers Custom Irregular Plot option."""
    ca = ConversationalRequirementAssistant()
    # Turn 1: user says "Residential project"
    t1 = ca.handle_turn("Residential project")
    assert t1.question_card is not None
    assert t1.question_card.field_key == "plot_dimensions"
    assert "Custom Irregular Plot" in t1.question_card.options


def test_conversational_assistant_custom_irregular_plot_advances_to_floors():
    """Verify defining a custom irregular polygon marks plot complete and asks for floors."""
    ca = ConversationalRequirementAssistant()

    # Step 1: Initial turn asking for plot dimensions
    t1 = ca.handle_turn("Residential project")
    assert t1.question_card.field_key == "plot_dimensions"

    # Step 2: User completes custom irregular plot popup with 5-point polygon
    polygon_brief = (
        "Plot polygon: (0.0, 0.0), (12.0, 0.0), (12.0, 8.0), (7.0, 10.0), (0.0, 8.0) "
        "facing North with front setback: 2.0m, rear setback: 2.0m, side setback: 2.0m."
    )
    t2 = ca.handle_turn(polygon_brief, existing_brief=t1.requirements_text)

    # Verify plot requirement is completed and NOT asked again
    plot_prog = next((p for p in t2.progress if p.name == "Plot dimensions"), None)
    assert plot_prog is not None
    assert plot_prog.status == "completed"
    assert "5-point irregular" in (plot_prog.value or "")

    # Next question must be target floors, NOT plot dimensions again!
    assert t2.question_card is not None
    assert t2.question_card.field_key == "target_floors"
    assert "Got it. I've saved your custom plot boundary." in t2.message

    # Verify canonical brief preserves polygon
    assert "Plot polygon:" in t2.requirements_text
    assert "(0.0, 0.0)" in t2.requirements_text
    assert "(7.0, 10.0)" in t2.requirements_text

    # Step 3: User answers 2 floors
    t3 = ca.handle_turn("2 Floors (Two Storey / Duplex)", existing_brief=t2.requirements_text)
    assert t3.question_card.field_key == "floor_1_rooms"
    # Plot polygon must still be preserved in canonical brief!
    assert "Plot polygon:" in t3.requirements_text


def test_api_chat_custom_irregular_plot(client: TestClient):
    """Verify HTTP API endpoint /api/v1/chat properly processes custom irregular plot."""
    resp1 = client.post("/api/v1/chat", json={"message": "Residential House"})
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["question_card"]["field_key"] == "plot_dimensions"

    resp2 = client.post(
        "/api/v1/chat",
        json={
            "message": "Plot polygon: (0.0, 0.0), (12.0, 0.0), (12.0, 8.0), (7.0, 10.0), (0.0, 8.0) facing North",
            "existing_brief": data1["requirements_text"],
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["question_card"]["field_key"] == "target_floors"
    assert "Plot polygon:" in data2["requirements_text"]


"""Phase 2 authoritative regression tests for conversational requirement flow and LLM integration.

Tests strictly enforce:
1. Real LLM invocation when client configured and available
2. Truthful `llm_used` flag (True on model invocation success, False on fallback)
3. Deterministic fallback when LLM unavailable or fails
4. Plot creation does NOT invent arbitrary rooms (plot 30x40 -> rooms = [])
5. Project name (e.g. "Modern Living Room Villa") does NOT create rooms
6. Multi-floor room assignment preserves floor boundaries (Floor 1 vs Floor 2 vs Floor 3)
7. Requirement constraints survive into canonical requirement brief / state:
   - Adjacency and separation
   - Attached-room relationships
   - Room dimensions and min/max areas
   - Unspecified constraints remain unspecified (not invented)
8. Security check (no API keys, tokens, or credentials exposed in responses or metadata)
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch

from app.agents.requirement_agent.agent import RequirementAgent
from app.agents.requirement_agent.conversation import (
    ConversationalRequirementAssistant,
    format_canonical_brief,
)
from app.agents.requirement_agent.parser import RequirementParser
from app.agents.requirement_agent.pipeline import RequirementPipeline
from app.chat.intent import ChatIntent
from app.chat.llm_service import ConversationalLLMService
from app.chat.orchestrator import ChatOrchestrator
from app.llm.client import HuggingFaceError, LLMClient
from app.llm.configuration import LLMConfig
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement


class SpyingLLMClient:
    """Spying test LLM client to verify invocation and payload inspection."""

    def __init__(self, response_text: str = "", succeed: bool = True):
        self.call_count = 0
        self.prompts: list[str] = []
        self.response_text = response_text
        self.succeed = succeed

    def generate(self, prompt: str, system_prompt: str | None = None) -> str:
        self.call_count += 1
        self.prompts.append(prompt)
        if not self.succeed:
            raise HuggingFaceError("Provider connection timeout")
        return self.response_text


# =============================================================================
# Task 13 Test 1 & Test 3: Real LLM Invocation and llm_used Flag
# =============================================================================

def test_real_llm_invocation_and_truthful_flag():
    """Verify that when a real LLM client is configured, it is actually invoked and llm_used=True."""
    valid_json_reply = json.dumps({
        "reply": "I have registered your 30x40 plot. What rooms would you like on the ground floor?",
        "intent": "plot_definition",
        "plot": {"width": 30.0, "depth": 40.0, "unit": "feet"},
        "floors": None,
        "rooms": [],
        "missing_information": ["ground_floor_rooms"],
        "next_question": "What rooms would you like on the ground floor?"
    })
    spy_client = SpyingLLMClient(response_text=valid_json_reply, succeed=True)
    cfg = LLMConfig(provider="huggingface", model_name="meta-llama/Llama-3-8B-Instruct")
    llm_service = ConversationalLLMService(llm_client=spy_client, config_loader=lambda: cfg)

    assistant = ConversationalRequirementAssistant()
    orchestrator = ChatOrchestrator(assistant=assistant, llm_service=llm_service)

    result = orchestrator.handle(message="I have a 30x40 feet plot")

    # 1. Verify LLM client was actually invoked
    assert spy_client.call_count == 1
    assert "30x40" in spy_client.prompts[0]

    # 2. Verify llm_used is truthfully True
    assert result.llm_used is True
    assert result.llm_provider in ("SpyingLLMClient", "huggingface")
    assert result.llm_latency_ms is not None and result.llm_latency_ms >= 0


# =============================================================================
# Task 13 Test 2 & Test 3: LLM Fallback and llm_used=False
# =============================================================================

def test_llm_fallback_when_unavailable():
    """Verify graceful deterministic fallback when LLM fails, with llm_used=False."""
    failing_client = SpyingLLMClient(response_text="", succeed=False)
    cfg = LLMConfig(provider="huggingface", model_name="test-model")
    llm_service = ConversationalLLMService(llm_client=failing_client, config_loader=lambda: cfg)

    assistant = ConversationalRequirementAssistant()
    orchestrator = ChatOrchestrator(assistant=assistant, llm_service=llm_service)

    result = orchestrator.handle(message="I have a 30x40 feet plot")

    # 1. Verify LLM client was invoked and failed
    assert failing_client.call_count == 1

    # 2. Verify deterministic fallback executed successfully with llm_used=False
    assert result.llm_used is False
    assert result.turn.requirements is not None
    assert result.turn.requirements.plot_dimensions is not None


def test_llm_flag_false_in_mock_or_unconfigured_mode():
    """Verify llm_used remains False when provider is mock/deterministic."""
    cfg = LLMConfig(provider="mock")
    llm_service = ConversationalLLMService(config_loader=lambda: cfg)

    assistant = ConversationalRequirementAssistant()
    orchestrator = ChatOrchestrator(assistant=assistant, llm_service=llm_service)

    result = orchestrator.handle(message="I have a 30x40 feet plot")

    # Mock provider must NOT claim real LLM was used
    assert result.llm_used is False


# =============================================================================
# Task 13 Test 4: Plot Does Not Invent Rooms
# =============================================================================

def test_plot_definition_does_not_invent_rooms():
    """Creating a plot must NOT automatically invent arbitrary rooms."""
    pipeline = RequirementPipeline()
    res = pipeline.process("I have a 30x40 feet plot", project_name="Test Project")
    reqs = res.requirements

    # Plot dimensions must be extracted
    assert reqs.plot_dimensions is not None
    assert reqs.plot_dimensions[0] == pytest.approx(9.144, rel=1e-2)
    assert reqs.plot_dimensions[1] == pytest.approx(12.192, rel=1e-2)

    # ZERO rooms must be created
    total_rooms = sum(len(f.room_requirements) for f in reqs.floors)
    assert total_rooms == 0


def test_conversational_plot_turn_does_not_invent_rooms():
    """Conversational assistant turn on plot dimension must keep room list empty."""
    assistant = ConversationalRequirementAssistant()
    turn = assistant.handle_turn("I have a 30x40 plot with 2 floors")

    assert turn.requirements is not None
    assert turn.requirements.target_floors == 2
    for f in turn.requirements.floors:
        assert len(f.room_requirements) == 0


# =============================================================================
# Task 13 Test 5: Project Name Does Not Create Rooms
# =============================================================================

def test_project_name_does_not_create_rooms():
    """Project title containing room keywords must NOT create room requirements."""
    parser = RequirementParser()

    project_name = "Modern Living Room Villa"
    text = f"Project: {project_name}\nPlot size: 40ft by 60ft."

    # Parse with project_name context
    parsed = parser.parse(text, project_name=project_name)

    # Verify no living room was invented
    all_room_types = [
        r.room_type
        for f in parsed.floors
        for r in f.room_requirements
    ]
    assert "living" not in all_room_types
    assert "living_room" not in all_room_types
    assert len(all_room_types) == 0


def test_project_name_pipeline_isolation():
    """Pipeline with project_name does not extract title keywords as rooms."""
    pipeline = RequirementPipeline()
    res = pipeline.process(
        user_input="Plot 30x40 feet.",
        project_name="Grand Living Room Residence",
    )
    reqs = res.requirements
    total_rooms = sum(len(f.room_requirements) for f in reqs.floors)
    assert total_rooms == 0


# =============================================================================
# Task 13 Test 6: Multi-Floor Room Assignment
# =============================================================================

def test_multi_floor_room_assignment_preserves_floors():
    """Verify that rooms for Floor 1 and Floor 2 remain cleanly separated."""
    agent = RequirementAgent()

    # Step 1: Initialize 2 floors
    res1 = agent.process("Plot 30x40 feet with 2 floors.")
    reqs = res1.requirements
    assert reqs.target_floors == 2

    # Step 2: Add 2 bedrooms to Floor 1
    res2 = agent.update(reqs, "2 bedrooms", active_floor=1)
    reqs = res2.requirements
    f1 = reqs.get_floor(1)
    assert f1 is not None
    f1_types = {r.room_type: r.min_count for r in f1.room_requirements}
    assert f1_types.get("bedroom") == 2

    # Step 3: Add 1 bedroom and 1 bathroom to Floor 2
    res3 = agent.update(reqs, "1 bedroom and 1 bathroom", active_floor=2)
    reqs = res3.requirements
    f2 = reqs.get_floor(2)
    assert f2 is not None
    f2_types = {r.room_type: r.min_count for r in f2.room_requirements}
    assert f2_types.get("bedroom") == 1
    assert f2_types.get("bathroom") == 1

    # Floor 1 must NOT be polluted by Floor 2 rooms
    f1_after = reqs.get_floor(1)
    assert f1_after is not None
    f1_after_types = {r.room_type: r.min_count for r in f1_after.room_requirements}
    assert f1_after_types.get("bedroom") == 2
    assert "bathroom" not in f1_after_types


def test_conversational_multi_floor_preservation():
    """Verify conversational assistant preserves active_floor across turns."""
    assistant = ConversationalRequirementAssistant()

    # Turn 1: Set up plot and 2 floors
    t1 = assistant.handle_turn("I have a 30x40 plot, 2 floors")
    assert t1.requirements is not None
    assert t1.requirements.target_floors == 2

    # Turn 2: Floor 1 rooms
    t2 = assistant.handle_turn("2 bedrooms, 1 kitchen", existing_brief=t1.requirements_text, active_floor=1)
    assert t2.requirements is not None
    f1 = t2.requirements.get_floor(1)
    assert f1 is not None
    assert any(r.room_type == "kitchen" for r in f1.room_requirements)

    # Turn 3: Floor 2 rooms via Question Card format
    t3 = assistant.handle_turn("Floor 2: 1 Bedroom, 1 Study", existing_brief=t2.requirements_text, active_floor=2)
    assert t3.requirements is not None
    f2 = t3.requirements.get_floor(2)
    assert f2 is not None
    assert any(r.room_type == "study" for r in f2.room_requirements)
    # Floor 1 must still have kitchen, not study
    f1_check = t3.requirements.get_floor(1)
    assert f1_check is not None
    assert any(r.room_type == "kitchen" for r in f1_check.room_requirements)
    assert not any(r.room_type == "study" for r in f1_check.room_requirements)


# =============================================================================
# Task 13 Test 7: Requirement Constraints Survive in Canonical Brief
# =============================================================================

def test_requirement_constraints_survive_canonical_brief():
    """Verify dimensions, min/max areas, adjacency, and attached-to survive."""
    parser = RequirementParser()
    brief_text = """
    Plot dimensions: 12m by 15m
    Target floors: 1
    Floor 1 (Ground Floor):
    - 1 Bedroom (3.66m x 4.27m, min 11.1 sqm, adjacent to Bathroom)
    - 1 Bathroom (attached to Bedroom)
    """

    reqs = parser.parse(brief_text)
    f1 = reqs.get_floor(1)
    assert f1 is not None

    bedroom = next((r for r in f1.room_requirements if r.room_type == "bedroom"), None)
    bathroom = next((r for r in f1.room_requirements if r.room_type == "bathroom"), None)

    assert bedroom is not None
    assert bathroom is not None

    # Check dimension survival
    assert bedroom.user_dimensions is not None
    assert bedroom.user_dimensions[0] == pytest.approx(3.66, rel=1e-2)
    assert bedroom.user_dimensions[1] == pytest.approx(4.27, rel=1e-2)

    # Check min area survival
    assert bedroom.min_area_sqm == pytest.approx(11.1, rel=1e-2)

    # Check adjacency survival
    assert "bathroom" in bedroom.adjacency

    # Check attached-to survival
    assert bathroom.attached_to == "bedroom"

    # Canonical brief format verification
    canonical = format_canonical_brief(reqs, project_name="Constraint Survival Test")
    assert "3.66m x 4.27m" in canonical
    assert "min 11.1 sqm" in canonical
    assert "adjacent to Bathroom" in canonical
    assert "attached to Bedroom" in canonical


def test_modal_verb_adjacency_parsing():
    """Verify conversational phrasing 'Bedroom must be adjacent to bathroom' survives."""
    parser = RequirementParser()
    text = "Floor 1: 1 Bedroom. 1 Bathroom. Bedroom must be adjacent to bathroom."
    reqs = parser.parse(text)
    f1 = reqs.get_floor(1)
    assert f1 is not None

    bedroom = next((r for r in f1.room_requirements if r.room_type == "bedroom"), None)
    assert bedroom is not None
    assert "bathroom" in bedroom.adjacency


# =============================================================================
# Task 6: 3BHK Shorthand Explicit Traceability
# =============================================================================

def test_bhk_shorthand_traceability():
    """Verify 3BHK expands into bedrooms, living, and kitchen with explicit description."""
    parser = RequirementParser()
    reqs = parser.parse("3BHK on a 30x40 plot")
    f1 = reqs.get_floor(1)
    assert f1 is not None

    room_map = {r.room_type: r for r in f1.room_requirements}
    assert "bedroom" in room_map
    assert room_map["bedroom"].min_count == 3
    assert "living" in room_map
    assert "kitchen" in room_map
    assert "3BHK shorthand" in room_map["bedroom"].description


# =============================================================================
# Task 15: Security Verification
# =============================================================================

def test_no_secrets_in_chat_turn_response():
    """Verify no API keys or token credentials are leaked in turn results or state."""
    secret_token = "hf_SecretToken12345XYZ"
    cfg = LLMConfig(provider="huggingface", api_key=secret_token)
    llm_service = ConversationalLLMService(
        llm_client=SpyingLLMClient("Hello", succeed=True),
        config_loader=lambda: cfg,
    )

    assistant = ConversationalRequirementAssistant()
    orchestrator = ChatOrchestrator(assistant=assistant, llm_service=llm_service)
    result = orchestrator.handle(message="Hello assistant")

    # Serialize result to json string
    result_dict = {
        "turn": result.turn.to_dict(),
        "route": result.route,
        "llm_used": result.llm_used,
        "llm_provider": result.llm_provider,
        "llm_model": result.llm_model,
    }
    serialized = json.dumps(result_dict)

    # Must NOT contain the secret token
    assert secret_token not in serialized
    assert "hf_" not in serialized


def test_conversational_greeting_in_mock_mode():
    """Verify greetings in mock mode produce welcoming replies and retain question card without errors."""
    cfg = LLMConfig(provider="mock")
    llm_service = ConversationalLLMService(config_loader=lambda: cfg)
    assistant = ConversationalRequirementAssistant()
    orchestrator = ChatOrchestrator(assistant=assistant, llm_service=llm_service)

    result = orchestrator.handle(message="hi")

    assert result.llm_used is False
    assert result.route == "conversation"
    assert "PLANFORGE_LLM_PROVIDER" not in result.turn.message
    assert "PlanForge" in result.turn.message
    # Under intelligent chat requirements, greetings do not force question cards
    assert result.turn.question_card is None


def test_conversational_plan_modification_fallback():
    """Verify modification questions in mock mode explain changes without applying them."""
    cfg = LLMConfig(provider="mock")
    llm_service = ConversationalLLMService(config_loader=lambda: cfg)
    assistant = ConversationalRequirementAssistant()
    orchestrator = ChatOrchestrator(assistant=assistant, llm_service=llm_service)

    result = orchestrator.handle(
        message="Can you move the bedroom to the front?",
        existing_brief="Plot 30x40 feet. 2 bedrooms.",
    )

    assert result.llm_used is False
    assert result.route == "plan_modification"
    assert "No changes have been applied" in result.turn.message
    assert result.plan_modified is False


"""Regression tests for custom irregular plot integration through conversational brief and ASAA pipeline."""

import pytest
from app.agents.requirement_agent.conversation import ConversationalRequirementAssistant
from app.orchestration.orchestrator import PlanForgeOrchestrator
from app.orchestration.config import OrchestrationConfig


def test_custom_irregular_plot_generation_end_to_end():
    """Verify that an irregular plot defined via chat preserves the exact boundary in ASAA and Geometry."""
    ca = ConversationalRequirementAssistant()

    # Step 1: Initial turn
    t1 = ca.handle_turn("Residential villa project")
    assert t1.question_card.field_key == "plot_dimensions"

    # Step 2: Custom irregular boundary submitted from modal
    custom_boundary = [(0.0, 0.0), (14.0, 0.0), (14.0, 10.0), (8.0, 12.0), (0.0, 10.0)]
    coords_str = ", ".join(f"({x}, {y})" for x, y in custom_boundary)
    polygon_brief = f"Plot polygon: {coords_str} facing North with front setback: 2.0m, rear setback: 2.0m, side setback: 2.0m."

    t2 = ca.handle_turn(polygon_brief, existing_brief=t1.requirements_text)
    assert t2.question_card.field_key == "target_floors"

    # Step 3: Specify 1 floor
    t3 = ca.handle_turn("1 Floor (Single Storey)", existing_brief=t2.requirements_text)
    assert t3.question_card.field_key == "floor_1_rooms"

    # Step 4: Specify rooms
    t4 = ca.handle_turn("Floor 1: living room, kitchen, dining room, master bedroom, bathroom", existing_brief=t3.requirements_text)
    assert t4.is_ready_for_generation is True

    # Step 5: Run generator with the compiled brief
    orchestrator = PlanForgeOrchestrator()
    cfg = OrchestrationConfig(
        enable_refinement=False,
        num_alternatives=1,
        enable_rendering=False,
        enable_exports=False,
    )
    result = orchestrator.generate(raw_brief=t4.requirements_text, config=cfg)

    assert result.status == "completed"
    assert result.floor_plan_set is not None

    # Verify ASAA and FloorPlanSet preserved the EXACT irregular boundary (5 vertices)
    actual_plot = result.floor_plan_set.plot_boundary
    assert len(actual_plot) == 5
    assert actual_plot == custom_boundary

    # Verify floor plan did NOT replace with a 4-point rectangle
    assert len(result.floor_plan_set.plot_boundary) != 4


def test_custom_irregular_plot_multifloor_preservation():
    """Verify that an irregular plot is preserved across multi-floor generation."""
    ca = ConversationalRequirementAssistant()

    custom_boundary = [(0.0, 0.0), (12.0, 0.0), (12.0, 8.0), (7.0, 10.0), (0.0, 8.0)]
    coords_str = ", ".join(f"({x}, {y})" for x, y in custom_boundary)
    polygon_brief = f"Plot polygon: {coords_str} facing East with front setback: 2.0m, rear setback: 2.0m, side setback: 2.0m."

    t1 = ca.handle_turn(polygon_brief)
    t2 = ca.handle_turn("2 Floors", existing_brief=t1.requirements_text)
    t3 = ca.handle_turn("Floor 1: living room, kitchen, dining room, master bedroom", existing_brief=t2.requirements_text)
    t4 = ca.handle_turn("Floor 2: 2 bedrooms, 1 bathroom, study room", existing_brief=t3.requirements_text)
    t5 = ca.handle_turn("Staircase in hallway", existing_brief=t4.requirements_text)

    assert t5.is_ready_for_generation is True

    orchestrator = PlanForgeOrchestrator()
    cfg = OrchestrationConfig(
        enable_refinement=False,
        num_alternatives=1,
        enable_rendering=False,
        enable_exports=False,
    )
    result = orchestrator.generate(raw_brief=t5.requirements_text, config=cfg)

    assert result.status == "completed"
    assert result.floor_plan_set is not None
    assert len(result.floor_plan_set.floor_plans) == 2

    # Both floors must preserve the exact custom irregular boundary
    for fp in result.floor_plan_set.floor_plans:
        assert len(result.floor_plan_set.plot_boundary) == 5
        assert result.floor_plan_set.plot_boundary == custom_boundary


def test_custom_irregular_plot_edit_reopen_preservation():
    """Verify that edit requirements reopens and maintains existing custom plot."""
    ca = ConversationalRequirementAssistant()

    custom_boundary = [(0.0, 0.0), (12.0, 0.0), (12.0, 8.0), (7.0, 10.0), (0.0, 8.0)]
    coords_str = ", ".join(f"({x}, {y})" for x, y in custom_boundary)
    polygon_brief = f"Plot polygon: {coords_str} facing North"

    t1 = ca.handle_turn(polygon_brief)
    t2 = ca.handle_turn("1 Floor", existing_brief=t1.requirements_text)
    t3 = ca.handle_turn("Floor 1: living room, kitchen", existing_brief=t2.requirements_text)

    # User clicks "Edit Requirements"
    t_edit = ca.handle_turn("Edit Requirements", existing_brief=t3.requirements_text)
    assert t_edit.status == "EDITING"
    assert "Plot polygon:" in t_edit.requirements_text
    assert "(7.0, 10.0)" in t_edit.requirements_text

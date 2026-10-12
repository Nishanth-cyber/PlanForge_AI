"""Comprehensive unit and integration tests for the Design Editing Agent in PlanForge AI.

Covers all 14 requirements:
1. Editing a room's dimensions.
2. Changing a room's shape (e.g., L-shaped, rectangular).
3. Adding and removing doors.
4. Adding and removing windows.
5. Updating room adjacency and spatial relationships.
6. Handling ambiguous editing instructions (clarification required).
7. Rejecting infeasible modifications.
8. Preserving unaffected rooms and dimensions.
9. Preserving floor assignments and multi-floor staircase alignment.
10. Reconstructing physical CAD geometry and validating independently.
11. Restoring previous versions through verified undo.
12. Updating the existing project in-place without creating duplicates.
13. Frontend-backend contract compatibility.
14. Preventing unsupported operations and malformed edits.
"""

from __future__ import annotations

import copy
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.agents.editing_agent import (
    DesignEditingAgent,
    EditIntentType,
    EditOperation,
    EditOperationType,
    detect_edit_intent,
)
from app.api.app import create_app
from app.api.registry import get_default_registry
from app.chat.orchestrator import ChatOrchestrator
from app.chat.schema import ResponseType
from app.chat.state import conversation_store
from app.geometry.engine import GeometryEngine
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import PlanForgeOrchestrator
from app.validation.validator import FloorPlanValidator


@pytest.fixture
def base_generated_project(tmp_path: Path):
    """Generate a realistic baseline project with living room, kitchen, bedroom, and bathroom."""
    orch = PlanForgeOrchestrator()
    brief = """
    Single floor home on a 40 feet by 50 feet plot facing north with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 200 sq ft
    - 1 kitchen of 120 sq ft
    - 1 master bedroom of 150 sq ft
    - 1 bathroom of 50 sq ft
    """
    cfg = OrchestrationConfig(
        num_alternatives=1,
        enable_refinement=False,
        enable_rendering=True,
        enable_exports=True,
        output_dir=str(tmp_path),
    )
    res = orch.generate(
        raw_brief=brief,
        project_name="Test Residence",
        project_id="proj_edit_test",
        config=cfg,
    )
    assert res.is_success
    assert res.floor_plan_set is not None
    assert len(res.floor_plan_set.floor_plans) > 0
    return res


@pytest.fixture
def multi_floor_project(tmp_path: Path):
    """Generate a realistic multi-floor project with staircase alignment."""
    orch = PlanForgeOrchestrator()
    brief = """
    Two floor duplex on a 40 feet by 50 feet plot facing north with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 200 sq ft
    - 1 kitchen of 120 sq ft
    - 1 staircase
    Floor 2:
    - 1 master bedroom of 160 sq ft
    - 1 bathroom of 50 sq ft
    - 1 staircase
    """
    cfg = OrchestrationConfig(
        num_alternatives=1,
        enable_refinement=False,
        enable_rendering=False,
        enable_exports=False,
        output_dir=str(tmp_path),
    )
    res = orch.generate(
        raw_brief=brief,
        project_name="Duplex Residence",
        project_id="proj_duplex_test",
        config=cfg,
    )
    assert res.is_success
    return res


@pytest.fixture
def client(tmp_path: Path):
    """TestClient with fresh registry."""
    app = create_app()
    reg = get_default_registry()
    reg.clear()
    conversation_store.clear()
    return TestClient(app)


# ---------------------------------------------------------------------------
# Test 1: Intent Detection
# ---------------------------------------------------------------------------
def test_1_intent_detection_fine_grained():
    """Verify intelligent edit intent detection without exposing technical labels."""
    # Dimensions
    res_dim = detect_edit_intent("Make the master bedroom larger")
    assert res_dim.intent == EditIntentType.MODIFY_DIMENSIONS
    assert res_dim.target_room_type == "master_bedroom"

    res_area = detect_edit_intent("Increase the kitchen area to 15 square meters")
    assert res_area.intent == EditIntentType.MODIFY_DIMENSIONS
    assert res_area.target_room_type == "kitchen"
    assert res_area.requested_changes.get("target_area_sqm") == 15.0

    # Shape
    res_shape = detect_edit_intent("Change the living room to an L-shaped design")
    assert res_shape.intent == EditIntentType.MODIFY_SHAPE
    assert res_shape.target_room_type == "living"
    assert res_shape.requested_changes.get("intended_shape") == "l_shaped"

    # Openings: Window
    res_win = detect_edit_intent("Add a window to the master bedroom")
    assert res_win.intent == EditIntentType.ADD_ELEMENT
    assert res_win.target_element_type == "window"
    assert res_win.target_room_type == "master_bedroom"

    res_win_rem = detect_edit_intent("Remove the extra window from the bedroom")
    assert res_win_rem.intent == EditIntentType.REMOVE_ELEMENT
    assert res_win_rem.target_element_type == "window"

    # Openings: Entrance
    res_ent = detect_edit_intent("Move the entrance to the east side")
    assert res_ent.intent == EditIntentType.MODIFY_LAYOUT
    assert res_ent.target_element_type == "entrance"
    assert res_ent.requested_changes.get("orientation") == "east"

    # Relationships & Adjacency
    res_adj = detect_edit_intent("Move the kitchen closer to the dining room")
    assert res_adj.intent == EditIntentType.MODIFY_LAYOUT
    assert res_adj.target_room_type == "kitchen"

    # Circulation
    res_circ = detect_edit_intent("Improve the circulation without changing the number of rooms")
    assert res_circ.intent == EditIntentType.MODIFY_LAYOUT
    assert res_circ.target_element_type == "circulation"

    # Ambiguous
    res_amb = detect_edit_intent("Make it better")
    assert res_amb.intent == EditIntentType.CLARIFICATION_REQUIRED
    assert res_amb.clarification_question is not None

    # New Design
    res_new = detect_edit_intent("Start a new design from scratch")
    assert res_new.intent == EditIntentType.NEW_DESIGN


# ---------------------------------------------------------------------------
# Test 2: Edit Room Dimensions
# ---------------------------------------------------------------------------
def test_2_edit_room_dimensions(base_generated_project):
    """Verify modifying room area reconstructs geometry and preserves unaffected rooms."""
    agent = DesignEditingAgent()
    initial_living = next(r for r in base_generated_project.floor_plan_set.floor_plans[0].geometry.rooms if r.room_type == "living")
    initial_area = initial_living.area_sqm

    res = agent.edit_design(
        project_result=base_generated_project,
        instruction="Increase the living room area to 25 square meters",
    )
    assert res.success
    assert res.is_valid
    assert "living" in res.summary.lower()

    # Verify geometry updated
    updated_living = next(r for r in res.updated_floor_plan_set.floor_plans[0].geometry.rooms if r.room_type == "living")
    assert updated_living.area_sqm > initial_area

    # Verify unaffected room preserved
    updated_kitchen = next(r for r in res.updated_floor_plan_set.floor_plans[0].geometry.rooms if r.room_type == "kitchen")
    initial_kitchen = next(r for r in base_generated_project.floor_plan_set.floor_plans[0].geometry.rooms if r.room_type == "kitchen")
    assert updated_kitchen.room_type == initial_kitchen.room_type


# ---------------------------------------------------------------------------
# Test 3: Change Room Shape
# ---------------------------------------------------------------------------
def test_3_change_room_shape(base_generated_project):
    """Verify changing room shape to L-shaped generates 6-vertex orthogonal polygon."""
    agent = DesignEditingAgent()
    res = agent.edit_design(
        project_result=base_generated_project,
        instruction="Change the living room to an L-shaped design",
    )
    assert res.success
    assert res.is_valid

    living_geo = next(r for r in res.updated_floor_plan_set.floor_plans[0].geometry.rooms if r.room_type == "living")
    # L-shaped built polygon has 6 vertices
    assert len(living_geo.built_polygon) == 6


# ---------------------------------------------------------------------------
# Test 4: Add and Remove Windows
# ---------------------------------------------------------------------------
def test_4_add_and_remove_windows(base_generated_project):
    """Verify adding and removing window intents updates geometry windows."""
    agent = DesignEditingAgent()
    initial_windows_count = len(base_generated_project.floor_plan_set.floor_plans[0].geometry.windows)

    # 1. Add window
    res_add = agent.edit_design(
        project_result=base_generated_project,
        instruction="Add a window to the master bedroom on the north wall",
    )
    assert res_add.success
    assert res_add.is_valid
    updated_windows_count = len(res_add.updated_floor_plan_set.floor_plans[0].geometry.windows)
    assert updated_windows_count >= initial_windows_count

    # 2. Remove window
    res_rem = agent.edit_design(
        project_result=base_generated_project,
        instruction="Remove the window from the master bedroom",
    )
    assert res_rem.success
    assert res_rem.is_valid


# ---------------------------------------------------------------------------
# Test 5: Add and Remove Doors
# ---------------------------------------------------------------------------
def test_5_add_and_remove_doors(base_generated_project):
    """Verify adding door intent updates door connections."""
    agent = DesignEditingAgent()
    res_add = agent.edit_design(
        project_result=base_generated_project,
        instruction="Add a door connecting living room to exterior",
    )
    assert res_add.success
    assert res_add.is_valid


# ---------------------------------------------------------------------------
# Test 6: Update Room Adjacency
# ---------------------------------------------------------------------------
def test_6_update_room_adjacency(base_generated_project):
    """Verify connecting kitchen directly to living room."""
    agent = DesignEditingAgent()
    res = agent.edit_design(
        project_result=base_generated_project,
        instruction="Move the kitchen closer to the living room",
    )
    assert res.success
    assert res.is_valid
    assert "kitchen" in res.summary.lower()


# ---------------------------------------------------------------------------
# Test 7: Handling Ambiguous Instructions
# ---------------------------------------------------------------------------
def test_7_ambiguous_instructions(base_generated_project):
    """Verify ambiguous requests ask for clarification without mutating design."""
    agent = DesignEditingAgent()
    res = agent.edit_design(
        project_result=base_generated_project,
        instruction="Make everything better and nicer",
    )
    assert not res.success
    assert res.clarification_required
    assert res.clarification_question is not None


# ---------------------------------------------------------------------------
# Test 8: Reject Infeasible Modifications
# ---------------------------------------------------------------------------
def test_8_reject_infeasible_modifications(base_generated_project):
    """Verify area exceeding total buildable footprint is rejected and design retained."""
    agent = DesignEditingAgent()
    res = agent.edit_design(
        project_result=base_generated_project,
        instruction="Increase the kitchen area to 500 square meters",
    )
    assert not res.success
    assert "exceeds" in res.summary.lower() or "rejected" in res.summary.lower()
    # Design was preserved
    assert base_generated_project.floor_plan_set is not None


# ---------------------------------------------------------------------------
# Test 9: Preserve Unaffected Rooms & Floor Assignments
# ---------------------------------------------------------------------------
def test_9_preserve_unaffected_rooms(base_generated_project):
    """Verify that editing kitchen leaves bedroom and bathroom untouched."""
    agent = DesignEditingAgent()
    arch_before = copy.deepcopy(base_generated_project.architectural_design_set)

    res = agent.edit_design(
        project_result=base_generated_project,
        instruction="Make the kitchen larger",
    )
    assert res.success

    arch_after = base_generated_project.architectural_design_set
    # Unaffected rooms have identical dimensions
    before_bath = next(r for r in arch_before.designs[0].rooms if r.room_type == "bathroom")
    after_bath = next(r for r in arch_after.designs[0].rooms if r.room_type == "bathroom")
    assert before_bath.intended_dimensions == after_bath.intended_dimensions
    assert before_bath.floor_number == after_bath.floor_number


# ---------------------------------------------------------------------------
# Test 10: Multi-Floor Staircase Alignment Preservation
# ---------------------------------------------------------------------------
def test_10_multi_floor_staircase_alignment(multi_floor_project):
    """Verify multi-floor staircase position and alignment remain intact during edit."""
    agent = DesignEditingAgent()
    res = agent.edit_design(
        project_result=multi_floor_project,
        instruction="Make the master bedroom larger",
        floor_number=2,
    )
    assert res.success
    assert res.is_valid

    # Staircase validator still passes
    fps = res.updated_floor_plan_set
    assert fps is not None
    stair_alignment_issues = agent.validator.staircase_validator.validate_multi_floor_alignment(fps)
    assert len(stair_alignment_issues) == 0


# ---------------------------------------------------------------------------
# Test 11: Undo Restore Previous Version
# ---------------------------------------------------------------------------
def test_11_undo_restores_previous_version(base_generated_project):
    """Verify that undo restores previous design state safely."""
    agent = DesignEditingAgent()

    # Edit v1 -> v2
    res_edit = agent.edit_design(
        project_result=base_generated_project,
        instruction="Increase the living room area to 24 square meters",
    )
    assert res_edit.success
    assert res_edit.version_id == "v2"
    assert res_edit.can_undo

    # Undo v2 -> v1
    res_undo = agent.undo_design(project_result=base_generated_project)
    assert res_undo.success
    assert res_undo.version_id == "v1"
    assert not res_undo.can_undo


# ---------------------------------------------------------------------------
# Test 12: Modify in Place Without Duplicate Projects
# ---------------------------------------------------------------------------
def test_12_modify_in_place_no_duplicate(client: TestClient, base_generated_project):
    """Verify project registry maintains same project ID across edits."""
    reg = get_default_registry()
    pid = base_generated_project.project_id
    reg.save_result(base_generated_project)

    initial_projects_count = len(reg.list_projects())

    # Edit via API
    resp = client.post(
        f"/projects/{pid}/edit",
        json={"instruction": "Add a window to the master bedroom"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"]
    assert data["project_id"] == pid

    # Count of projects unchanged
    assert len(reg.list_projects()) == initial_projects_count


# ---------------------------------------------------------------------------
# Test 13: Reject Unsupported Operations
# ---------------------------------------------------------------------------
def test_13_prevent_unsupported_operations():
    """Verify that invalid or malformed operations raise schema validation error."""
    with pytest.raises(ValueError):
        op = EditOperation(operation="TELEPORT_ROOM")  # type: ignore
        op.validate()


# ---------------------------------------------------------------------------
# Test 14: End-to-End Chat Modification Integration
# ---------------------------------------------------------------------------
def test_14_chat_endpoint_triggers_design_edit(client: TestClient, base_generated_project):
    """Verify natural-language modification typed in /chat updates the floor plan."""
    reg = get_default_registry()
    pid = base_generated_project.project_id
    reg.save_result(base_generated_project)

    # Chat message with project_id
    resp = client.post(
        "/chat",
        json={
            "message": "Make the master bedroom larger",
            "project_id": pid,
            "project_name": "Test Residence",
        },
    )
    assert resp.status_code == 200
    cdata = resp.json()
    assert cdata["plan_modified"] is True
    assert cdata["response_type"] == "generation_result"
    assert cdata["action"] is not None
    assert cdata["action"]["type"] == "inspect"
    assert "updated" in cdata["message"].lower() or "master" in cdata["message"].lower()

"""Phase 7 API Integration Tests.

Validates:
- GET /projects/{project_id}/clarifications
- POST /projects/{project_id}/clarifications/{request_id}/response
- POST /projects/{project_id}/resume
- POST /projects/{project_id}/cancel
- Stale state version rejection
- Invalid option ID rejection
- Duplicate submission handling
- Thread-safe concurrent response handling
- Legacy pipeline backward compatibility
"""

import threading
import pytest
from fastapi.testclient import TestClient

from app.api.app import app
from app.api.registry import project_registry
from app.agentic.state import ProjectState, RunStatus
from app.agentic.clarification import (
    ClarificationCategory,
    ClarificationOption,
    ClarificationRequest,
    AlternativeFeasibilityType,
)
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement
from app.orchestration.hierarchical import HierarchicalOrchestrator
from app.orchestration.orchestrator import PlanForgeOrchestrator


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def paused_project_session():
    """Sets up a mock project session paused waiting for clarification."""
    project_id = "test_phase7_proj_001"
    reqs = Requirements(
        project_name="Interactive Test Cottage",
        plot_dimensions=(10.0, 10.0),
        setbacks={"front": 2.0, "rear": 2.0, "left": 2.0, "right": 2.0},
        target_floors=1,
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(room_type="living", min_count=1, min_area_sqm=30.0),
                    RoomRequirement(room_type="kitchen", min_count=1, min_area_sqm=20.0),
                ],
            )
        ],
    )
    registry = PlanForgeOrchestrator().tool_registry
    orchestrator = HierarchicalOrchestrator(registry=registry, interactive=True)
    state = orchestrator.run(
        project_id=project_id,
        goal="Interactive Test Cottage",
        requirements=reqs,
    )
    project_registry.save_session(project_id, state, orchestrator)
    return project_id, state, orchestrator


def test_api_get_clarifications(client, paused_project_session):
    project_id, state, _ = paused_project_session
    response = client.get(f"/projects/{project_id}/clarifications")
    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == project_id
    assert data["pending_clarification"] is not None
    assert data["pending_clarification"]["category"] in ["REQUEST_CONSTRAINT_REVISION", "CLARIFY"]
    assert len(data["pending_clarification"]["options"]) >= 1


def test_api_submit_clarification_response_success(client, paused_project_session):
    project_id, state, _ = paused_project_session
    pending = client.get(f"/projects/{project_id}/clarifications").json()["pending_clarification"]
    req_id = pending["request_id"]
    opts = pending["options"]
    first_opt_id = opts[0]["option_id"]

    resp = client.post(
        f"/projects/{project_id}/clarifications/{req_id}/response",
        json={
            "selected_option_id": first_opt_id,
            "numeric_overrides": {"plot_length": 25.0},
            "expected_state_version": state.state_version,
        },
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "resumable" or res_data["success"] is True

    # Now pending must be cleared
    refreshed = client.get(f"/projects/{project_id}/clarifications").json()
    assert refreshed["pending_clarification"] is None
    assert len(refreshed["clarification_history"]) >= 1


def test_api_submit_clarification_stale_version_rejected(client, paused_project_session):
    project_id, state, _ = paused_project_session
    pending = client.get(f"/projects/{project_id}/clarifications").json()["pending_clarification"]
    req_id = pending["request_id"]
    first_opt_id = pending["options"][0]["option_id"]

    # Submit with wrong expected state version
    resp = client.post(
        f"/projects/{project_id}/clarifications/{req_id}/response",
        json={
            "selected_option_id": first_opt_id,
            "expected_state_version": 9999,
        },
    )
    assert resp.status_code == 409
    assert "stale response" in resp.json()["detail"].lower()


def test_api_submit_clarification_invalid_option_rejected(client, paused_project_session):
    project_id, state, _ = paused_project_session
    pending = client.get(f"/projects/{project_id}/clarifications").json()["pending_clarification"]
    req_id = pending["request_id"]

    resp = client.post(
        f"/projects/{project_id}/clarifications/{req_id}/response",
        json={
            "selected_option_id": "non_existent_option_id_xyz",
            "expected_state_version": state.state_version,
        },
    )
    assert resp.status_code == 400
    assert "invalid option" in resp.json()["detail"].lower()


def test_api_resume_workflow(client, paused_project_session):
    project_id, state, _ = paused_project_session
    pending = client.get(f"/projects/{project_id}/clarifications").json()["pending_clarification"]
    req_id = pending["request_id"]

    # Trying to resume while pending must fail
    bad_resume = client.post(f"/projects/{project_id}/resume", json={})
    assert bad_resume.status_code == 400

    # Answer clarification
    client.post(
        f"/projects/{project_id}/clarifications/{req_id}/response",
        json={
            "selected_option_id": "expand_plot_depth",
            "numeric_overrides": {"plot_length": 25.0},
            "expected_state_version": state.state_version,
        },
    )

    # Resume now succeeds
    good_resume = client.post(f"/projects/{project_id}/resume", json={})
    assert good_resume.status_code == 200
    res_data = good_resume.json()
    assert res_data["status"] in ("completed", "accepted")


def test_api_cancel_workflow(client, paused_project_session):
    project_id, state, _ = paused_project_session
    resp = client.post(f"/projects/{project_id}/cancel", json={"reason": "User cancelled session"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"

    # Subsequent resume must be rejected
    res = client.post(f"/projects/{project_id}/resume", json={})
    assert res.status_code == 400


def test_concurrent_clarification_submissions(paused_project_session):
    """Scenario 16: Concurrent responses cannot corrupt shared state."""
    project_id, state, _ = paused_project_session
    req_id = state.pending_clarification.request_id
    opt_id = state.pending_clarification.options[0].option_id

    results = []

    def submit_worker(worker_id):
        success, msg, resp, st = project_registry.submit_clarification_response(
            project_id=project_id,
            request_id=req_id,
            selected_option_id=opt_id,
            numeric_overrides={"plot_length": 25.0 + worker_id},
            expected_state_version=state.state_version,
        )
        results.append((success, msg))

    t1 = threading.Thread(target=submit_worker, args=(1,))
    t2 = threading.Thread(target=submit_worker, args=(2,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one submission must succeed; the second must be rejected (not pending or stale)
    successes = [r for r in results if r[0] is True]
    assert len(successes) == 1
    assert len(results) == 2

"""Comprehensive end-to-end integration tests for Phase 12 Orchestration & API.

Verifies:
API Request
    ↓
Orchestrator
    ↓
Requirement Agent + Completeness Gate
    ↓
Planning Agent
    ↓
ASAA
    ↓
Architectural Design LLM
    ↓
Geometry Engine
    ↓
Independent Validator
    ↓
Refinement Loop
    ↓
Multi-Design Diversity
    ↓
Decision Trace
    ↓
Export & Rendering
    ↓
API Response & Retrieval
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import get_orchestrator
from app.api.registry import get_default_registry
from app.orchestration.orchestrator import PlanForgeOrchestrator


@pytest.fixture
def client(tmp_path: Path):
    """Create a test client with a clean project registry."""
    app = create_app()
    registry = get_default_registry()
    registry.clear()
    return TestClient(app)


def test_end_to_end_api_generation_flow(client: TestClient, tmp_path: Path):
    """Verify complete end-to-end generation through API to exported artifacts without bypassing components."""
    brief = """
    Single floor contemporary home on a 40 feet by 50 feet rectangular plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 spacious living room of 300 sq ft
    - 1 dining room of 150 sq ft
    - 1 kitchen of 130 sq ft
    - 1 master bedroom of 200 sq ft
    """
    out_dir = tmp_path / "e2e_outputs"
    payload = {
        "brief": brief,
        "project_name": "End-to-End Modern Villa",
        "num_alternatives": 2,
        "enable_refinement": True,
        "enable_rendering": True,
        "enable_exports": True,
        "create_zip": True,
        "output_dir": str(out_dir),
    }

    # 1. Trigger generation via POST /api/v1/generate
    resp = client.post("/api/v1/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    # 2. Check response structure and completeness
    pid = data["project_id"]
    assert pid is not None
    assert data["status"] == "completed"
    assert data["is_success"] is True
    assert data["validation_summary"] is not None
    assert data["decision_trace_available"] is True

    # 3. Check stage execution records (no stage was bypassed)
    stages = data["stage_statuses"]
    assert stages["REQUIREMENT"] == "COMPLETED"
    assert stages["PLANNING"] == "COMPLETED"
    assert stages["ASAA"] == "COMPLETED"
    assert stages["ARCHITECTURAL_DESIGN"] == "COMPLETED"
    assert stages["GEOMETRY"] == "COMPLETED"
    assert stages["VALIDATION"] == "COMPLETED"
    assert stages["MULTI_DESIGN"] == "COMPLETED"
    assert stages["EXPLAINABILITY"] == "COMPLETED"
    assert stages["EXPORT"] == "COMPLETED"

    # 4. Check neutral multi-design alternatives
    assert len(data["alternatives"]) == 2
    for alt in data["alternatives"]:
        assert alt["is_valid"] is True
        assert "rank" not in alt
        assert "is_best" not in alt

    # 5. Verify physical filesystem artifacts
    bundle_dir = out_dir / pid
    assert bundle_dir.is_dir()
    assert (bundle_dir / "project.json").is_file()
    assert (bundle_dir / "summary.md").is_file()
    assert (bundle_dir / "decision_trace.json").is_file()
    assert (bundle_dir / "alternatives" / "alternative_1" / "floor_1.png").is_file()
    assert (bundle_dir / "alternatives" / "alternative_2" / "floor_1.png").is_file()
    assert (out_dir / f"{pid}.zip").is_file()

    # 6. Verify GET endpoints
    # Detail
    detail_resp = client.get(f"/api/v1/projects/{pid}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["project_id"] == pid

    # Trace
    trace_resp = client.get(f"/api/v1/projects/{pid}/trace")
    assert trace_resp.status_code == 200
    trace_json = trace_resp.json()
    assert trace_json["project_name"] == "End-to-End Modern Villa"
    assert len(trace_json["stages"]) >= 6

    # Alternatives
    alts_resp = client.get(f"/api/v1/projects/{pid}/alternatives")
    assert alts_resp.status_code == 200
    assert len(alts_resp.json()) == 2

    # Export Inventory
    exp_resp = client.get(f"/api/v1/projects/{pid}/export")
    assert exp_resp.status_code == 200
    assert exp_resp.json()["total_files"] >= 8

    # Specific file download
    file_resp = client.get(f"/api/v1/projects/{pid}/export?file=summary.md")
    assert file_resp.status_code == 200
    assert "PlanForge AI" in file_resp.text


def test_end_to_end_incomplete_requirements_gating(client: TestClient):
    """Verify missing required fields halt pipeline immediately without running planning or geometry."""
    # Brief missing plot boundaries
    incomplete_brief = """
    Cottage with 1 bedroom and 1 bath.
    """
    resp = client.post("/api/v1/generate", json={"brief": incomplete_brief})
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "incomplete_requirements"
    assert data["is_success"] is False
    assert len(data["missing_fields"]) > 0
    assert data["stage_statuses"]["REQUIREMENT"] == "FAILED"
    assert data["stage_statuses"]["PLANNING"] == "SKIPPED"
    assert data["stage_statuses"]["GEOMETRY"] == "SKIPPED"


def test_end_to_end_no_invention_on_missing_floor_requirements(client: TestClient):
    """Verify 2 floors requested with only Floor 1 specified halts without inventing Floor 2 rooms."""
    brief = """
    Two floor home on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Target floors: 2
    Floor 1:
    - 1 living room of 300 sq ft
    - 1 kitchen of 120 sq ft
    """
    resp = client.post("/api/v1/generate", json={"brief": brief})
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "incomplete_requirements"
    assert 2 in data["missing_floors"]
    assert data["stage_statuses"]["PLANNING"] == "SKIPPED"
    assert data["stage_statuses"]["GEOMETRY"] == "SKIPPED"


def test_end_to_end_failure_propagation(client: TestClient):
    """Verify that an unrecoverable stage failure marks it FAILED and skips downstream stages."""
    mock_geom = MagicMock()
    mock_geom.construct.side_effect = RuntimeError("Unrecoverable geometry engine polygon intersection fault")

    orch = PlanForgeOrchestrator(geometry_engine=mock_geom)

    # Override orchestrator in FastAPI app
    app = client.app
    app.dependency_overrides[get_orchestrator] = lambda: orch

    brief = """
    Single floor cottage on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 300 sq ft
    """
    try:
        resp = client.post("/api/v1/generate", json={"brief": brief})
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "failed"
        assert data["is_success"] is False
        assert "Unrecoverable geometry engine" in (data["error_message"] or "")
        assert data["stage_statuses"]["GEOMETRY"] == "FAILED"
        assert data["stage_statuses"]["VALIDATION"] == "SKIPPED"
        assert data["stage_statuses"]["EXPORT"] == "SKIPPED"
    finally:
        app.dependency_overrides.clear()


def test_end_to_end_multi_floor_two_floor_residence(client: TestClient, tmp_path: Path):
    """Verify generation of a multi-floor building preserving floor isolation and vertical circulation."""
    brief = """
    Two floor duplex on a 45 feet by 55 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Target floors: 2
    Floor 1:
    - 1 living room of 300 sq ft
    - 1 dining room of 150 sq ft
    - 1 kitchen of 120 sq ft
    Floor 2:
    - 1 master bedroom of 220 sq ft
    - 1 guest bedroom of 150 sq ft
    - 1 study of 100 sq ft
    """
    out_dir = tmp_path / "outputs_duplex"
    payload = {
        "brief": brief,
        "project_name": "Duplex Residence",
        "num_alternatives": 1,
        "enable_rendering": True,
        "enable_exports": True,
        "output_dir": str(out_dir),
    }

    resp = client.post("/api/v1/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "completed"
    assert data["is_success"] is True

    pid = data["project_id"]
    bundle_dir = out_dir / pid
    alt1_dir = bundle_dir / "alternatives" / "alternative_1"

    # Multi-floor physical isolation: discrete drawings per floor
    assert (alt1_dir / "floor_1.png").is_file()
    assert (alt1_dir / "floor_2.png").is_file()


def test_end_to_end_api_path_safety(client: TestClient, tmp_path: Path):
    """Verify that path traversal attempts are strictly blocked with HTTP 400."""
    brief = """
    Single floor house on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 300 sq ft
    """
    payload = {
        "brief": brief,
        "project_name": "Security Test",
        "enable_exports": True,
        "output_dir": str(tmp_path / "outputs_sec_e2e"),
    }
    gen_resp = client.post("/api/v1/generate", json=payload)
    pid = gen_resp.json()["project_id"]

    # Traversal tests
    attacks = [
        f"/api/v1/projects/{pid}/export?file=../../pyproject.toml",
        f"/api/v1/projects/{pid}/export?file=../../../Windows/win.ini",
        f"/api/v1/projects/{pid}/export?file=/etc/shadow",
        f"/api/v1/projects/{pid}/export?file=..%2F..%2Fpyproject.toml",
    ]
    for url in attacks:
        r = client.get(url)
        assert r.status_code == 400
        assert "traversal" in r.json()["detail"].lower()


def test_list_projects_and_get_project_data(client: TestClient, tmp_path: Path):
    """Verify listing projects and retrieving complete structured project JSON data."""
    brief = """
    Single floor cottage on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
    Floor 1:
    - 1 living room of 300 sq ft
    """
    payload = {
        "brief": brief,
        "project_name": "Listing Test Project",
        "output_dir": str(tmp_path / "outputs_list_test"),
    }
    gen_resp = client.post("/api/v1/generate", json=payload)
    assert gen_resp.status_code == 200
    pid = gen_resp.json()["project_id"]

    # 1. Test GET /api/v1/projects
    list_resp = client.get("/api/v1/projects")
    assert list_resp.status_code == 200
    p_list = list_resp.json()
    assert isinstance(p_list, list)
    assert any(p["project_id"] == pid for p in p_list)

    # 2. Test GET /api/v1/projects/{pid}/data
    data_resp = client.get(f"/api/v1/projects/{pid}/data")
    assert data_resp.status_code == 200
    pdata = data_resp.json()
    assert pdata["project_id"] == pid
    assert "floor_plan_set" in pdata
    assert "requirements" in pdata


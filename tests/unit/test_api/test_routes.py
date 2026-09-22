"""Unit tests for PlanForge REST API endpoints and path traversal security."""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.registry import ProjectRegistry, get_default_registry


@pytest.fixture
def client(tmp_path: Path):
    """Create a test client with a clean project registry."""
    app = create_app()
    registry = get_default_registry()
    registry.clear()
    return TestClient(app)


def test_health_endpoint(client: TestClient):
    """Verify health endpoint returns status 200 and system metadata."""
    # Test both /health and /api/v1/health
    for ep in ("/health", "/api/v1/health"):
        resp = client.get(ep)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "PlanForge AI"
        assert "version" in data
        assert "llm_provider" in data


def test_generate_endpoint_success(client: TestClient, tmp_path: Path):
    """Verify POST /generate with valid brief produces a complete project."""
    payload = {
        "brief": """
        Single floor modern residence on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 300 sq ft
        - 1 kitchen of 150 sq ft
        """,
        "project_name": "API Success Test",
        "num_alternatives": 1,
        "enable_rendering": True,
        "enable_exports": True,
        "output_dir": str(tmp_path / "outputs_api"),
    }

    resp = client.post("/api/v1/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["project_id"] is not None
    assert data["status"] == "completed"
    assert data["is_success"] is True
    assert data["decision_trace_available"] is True
    assert "GEOMETRY" in data["stage_statuses"]
    assert data["stage_statuses"]["GEOMETRY"] == "COMPLETED"
    assert data["stage_statuses"]["VALIDATION"] == "COMPLETED"
    assert len(data["alternatives"]) >= 1


def test_generate_endpoint_incomplete_requirements(client: TestClient):
    """Verify POST /generate with missing requirements returns structured incomplete status."""
    payload = {
        "brief": "Living room and kitchen.",
        "project_name": "API Incomplete Test",
    }

    resp = client.post("/api/v1/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "incomplete_requirements"
    assert data["is_success"] is False
    assert len(data["missing_fields"]) > 0
    assert data["stage_statuses"]["PLANNING"] == "SKIPPED"


def test_get_project_detail_and_not_found(client: TestClient, tmp_path: Path):
    """Verify GET /projects/{project_id} retrieves project and returns 404 for unknown IDs."""
    # 1. 404 for unknown project
    resp_404 = client.get("/api/v1/projects/unknown_id_123")
    assert resp_404.status_code == 404

    # 2. Generate a project
    payload = {
        "brief": """
        Single floor house on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 300 sq ft
        """,
        "project_name": "Detail Test",
        "output_dir": str(tmp_path / "outputs_detail"),
    }
    gen_resp = client.post("/api/v1/generate", json=payload)
    pid = gen_resp.json()["project_id"]

    # 3. Retrieve detail
    get_resp = client.get(f"/api/v1/projects/{pid}")
    assert get_resp.status_code == 200
    detail = get_resp.json()
    assert detail["project_id"] == pid
    assert detail["status"] == "completed"


def test_get_project_trace_and_alternatives(client: TestClient, tmp_path: Path):
    """Verify GET /projects/{id}/trace and GET /projects/{id}/alternatives."""
    payload = {
        "brief": """
        Single floor home on a 45 feet by 55 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 280 sq ft
        - 1 dining room of 140 sq ft
        - 1 kitchen of 120 sq ft
        """,
        "project_name": "Trace & Alts Test",
        "num_alternatives": 2,
        "output_dir": str(tmp_path / "outputs_trace_alts"),
    }
    gen_resp = client.post("/api/v1/generate", json=payload)
    pid = gen_resp.json()["project_id"]

    # 1. Trace endpoint
    trace_resp = client.get(f"/api/v1/projects/{pid}/trace")
    assert trace_resp.status_code == 200
    trace_data = trace_resp.json()
    assert "trace_id" in trace_data
    assert "stages" in trace_data
    assert len(trace_data["stages"]) > 0

    # 2. Alternatives endpoint
    alts_resp = client.get(f"/api/v1/projects/{pid}/alternatives")
    assert alts_resp.status_code == 200
    alts_data = alts_resp.json()
    assert isinstance(alts_data, list)
    assert len(alts_data) == 2


def test_export_access_and_path_traversal_defense(client: TestClient, tmp_path: Path):
    """Verify export retrieval and strict protection against path traversal."""
    payload = {
        "brief": """
        Single floor house on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 300 sq ft
        """,
        "project_name": "Export Security Test",
        "enable_exports": True,
        "output_dir": str(tmp_path / "outputs_sec"),
    }
    gen_resp = client.post("/api/v1/generate", json=payload)
    pid = gen_resp.json()["project_id"]

    # 1. Inventory list (no file param)
    inv_resp = client.get(f"/api/v1/projects/{pid}/export")
    assert inv_resp.status_code == 200
    inv_data = inv_resp.json()
    assert inv_data["total_files"] > 0
    assert any(f["filename"] == "summary.md" for f in inv_data["files"])

    # 2. Safe file retrieval
    file_resp = client.get(f"/api/v1/projects/{pid}/export?file=summary.md")
    assert file_resp.status_code == 200
    assert "PlanForge AI" in file_resp.text

    # 3. Path traversal attack via ../
    attack1 = client.get(f"/api/v1/projects/{pid}/export?file=../../pyproject.toml")
    assert attack1.status_code == 400
    assert "traversal" in attack1.json()["detail"].lower()

    # 4. Path traversal attack via absolute path
    attack2 = client.get(f"/api/v1/projects/{pid}/export?file=/etc/passwd")
    assert attack2.status_code == 400
    assert "traversal" in attack2.json()["detail"].lower()

    # 5. Non-existent file inside bundle returns 404
    missing_resp = client.get(f"/api/v1/projects/{pid}/export?file=non_existent_file.xyz")
    assert missing_resp.status_code == 404


def test_generate_endpoint_with_irregular_plot_shape(client: TestClient, tmp_path: Path):
    """Verify POST /generate with explicit irregular polygon plot_shape succeeds and preserves vertices."""
    l_shape_polygon = [
        [0.0, 0.0],
        [20.0, 0.0],
        [20.0, 10.0],
        [10.0, 10.0],
        [10.0, 20.0],
        [0.0, 20.0],
    ]
    payload = {
        "brief": """
        Single floor residence with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 220 sq ft
        - 1 kitchen of 110 sq ft
        - 1 bedroom of 140 sq ft
        - 1 bathroom of 55 sq ft
        """,
        "plot_shape": l_shape_polygon,
        "project_name": "Irregular L-Shape API Test",
        "num_alternatives": 1,
        "enable_rendering": True,
        "enable_exports": True,
        "output_dir": str(tmp_path / "outputs_lshape"),
    }

    resp = client.post("/api/v1/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "completed"
    assert data["is_success"] is True
    assert data["stage_statuses"]["GEOMETRY"] == "COMPLETED"

    # Verify project data contains authoritative plot boundary
    proj_resp = client.get(f"/api/v1/projects/{data['project_id']}/data")
    assert proj_resp.status_code == 200
    p_data = proj_resp.json()
    assert len(p_data["floor_plan_set"]["plot_boundary"]) == 6
    assert p_data["requirements"]["plot_shape"] is not None
    assert len(p_data["requirements"]["plot_shape"]) == 6


def test_delete_project_endpoint(client: TestClient, tmp_path: Path):
    """Verify DELETE /projects/{project_id} deletes project from registry and returns 404 after deletion."""
    # 1. 404 for nonexistent project
    resp_404 = client.delete("/api/v1/projects/nonexistent_project_999")
    assert resp_404.status_code == 404

    # 2. Generate a project
    payload = {
        "brief": """
        Single floor house on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.
        Floor 1:
        - 1 living room of 300 sq ft
        """,
        "project_name": "Delete Test Project",
        "output_dir": str(tmp_path / "outputs_delete"),
    }
    gen_resp = client.post("/api/v1/generate", json=payload)
    assert gen_resp.status_code == 200
    pid = gen_resp.json()["project_id"]

    # 3. Confirm it exists
    assert client.get(f"/api/v1/projects/{pid}").status_code == 200

    # 4. Delete project
    del_resp = client.delete(f"/api/v1/projects/{pid}")
    assert del_resp.status_code == 200
    del_data = del_resp.json()
    assert del_data["status"] == "deleted"
    assert del_data["project_id"] == pid

    # 5. Confirm it no longer exists (404)
    assert client.get(f"/api/v1/projects/{pid}").status_code == 404


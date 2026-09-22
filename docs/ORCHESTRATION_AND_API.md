# PlanForge — Orchestration & API Reference (Phase 12)

This document provides a comprehensive guide to the PlanForge Orchestration Subsystem (`app/orchestration/`) and REST API Layer (`app/api/`), established in Phase 12.

---

## 1. System Overview

Phase 12 connects all completed PlanForge components into a coherent, deterministic, end-to-end pipeline and exposes it through a clean, synchronous FastAPI REST API.

```
                    +--------------------------------+
                    |        HTTP REST Client        |
                    +--------------------------------+
                                    |
                                    v
+------------------------------------------------------------------------+
|                          FastAPI API Layer                             |
|                           (app/api/)                                   |
|                                                                        |
|  - GET  /health                                                        |
|  - POST /generate (or /api/v1/generate)                                |
|  - GET  /projects/{id}                                                 |
|  - GET  /projects/{id}/trace                                           |
|  - GET  /projects/{id}/alternatives                                    |
|  - GET  /projects/{id}/export                                          |
|                                                                        |
|  [NO architectural, geometry, or allocation logic in API layer]        |
|  [Filesystem Path Traversal Defense] [In-Memory Project Registry]      |
+------------------------------------------------------------------------+
                                    |
                                    v
+------------------------------------------------------------------------+
|                      Orchestration Subsystem                           |
|                        (app/orchestration/)                            |
|                                                                        |
|                       PlanForgeOrchestrator                            |
|                                                                        |
|  Stage 1:  Requirement Agent      --> Requirements                     |
|  Stage 2:  Planning Agent         --> PlanningSpec                     |
|  Stage 3:  ASAA Allocator         --> AllocationSet                    |
|  Stage 4:  Architectural LLM      --> ArchitecturalDesignSet           |
|  Stage 5:  Geometry Engine        --> FloorPlanSet                     |
|  Stage 6:  Independent Validator  --> ValidationReport                 |
|  Stage 7:  Refinement Loop        --> Refined FloorPlanSet             |
|  Stage 8:  Diversity Generator    --> DesignAlternativeSet             |
|  Stage 9:  Explainability Trace   --> DecisionTrace                    |
|  Stage 10: Export & Rendering     --> ProjectBundleManifest            |
+------------------------------------------------------------------------+
```

---

## 2. Core Architectural Invariants

1. **The API is NOT the Architectural Engine**:
   Zero ASAA algorithms, room allocation logic, geometry construction, validation rules, refinement loops, or diversity metrics exist inside `app/api/`. The API routes purely validate HTTP schemas, delegate execution to `PlanForgeOrchestrator`, store results in the process-local registry, and format responses.

2. **No Requirement Invention**:
   If an input brief lacks critical spatial requirements (e.g., missing plot dimensions, unspecified rooms for declared floors), the `CompletenessGate` halts execution immediately. The pipeline transitions to `incomplete_requirements` and returns a structured diagnostic report without invoking planning or geometry.

3. **Neutral Alternative Presentation**:
   Multi-design alternatives are presented strictly neutrally. The orchestrator and API never declare a "best design", "winner", or ranking. Every alternative includes its objective validation status, metrics, and diversity signature without value judgements.

4. **Process-Local Storage Model**:
   PlanForge intentionally utilizes an in-memory, thread-safe project registry (`ProjectRegistry`). There is **zero external database infrastructure** (no PostgreSQL, SQLite, MongoDB, Redis). Generated projects and pipeline traces exist in memory during the process lifetime. Exported files (PNGs, JSONs, Markdown) are saved to disk under the designated output directory. **Data does not persist across server restarts.**

5. **Filesystem Security & Traversal Prevention**:
   The `/projects/{id}/export` endpoint strictly enforces path traversal defenses via `resolve_safe_path()`. File requests containing `..`, directory navigation, absolute paths, or null bytes are rejected with HTTP 400. All served files must resolve strictly within the project's generated bundle directory.

6. **100% Offline Capability & Dependency Injection**:
   All stage agents and engines can be injected into `PlanForgeOrchestrator`. By default, the orchestrator initializes with `MockLLMClient` and headless `matplotlib` (Agg backend), allowing 100% offline, deterministic execution and sub-second test execution.

---

## 3. Orchestration Subsystem (`app/orchestration/`)

### Stage Lifecycle & Names

The pipeline tracks execution across 10 discrete stages defined in `StageName`:

| Stage | Identifier | Upstream Input | Output Artifact |
|---|---|---|---|
| 1. Requirements | `REQUIREMENTS` | Text brief / dict | `Requirements` |
| 2. Planning | `PLANNING` | `Requirements` | `PlanningSpec` |
| 3. ASAA | `ASAA` | `PlanningSpec` | `AllocationSet` |
| 4. Design LLM | `DESIGN_LLM` | `PlanningSpec` + `AllocationSet` | `ArchitecturalDesignSet` |
| 5. Geometry | `GEOMETRY` | `AllocationSet` + `ArchitecturalDesignSet` | `FloorPlanSet` |
| 6. Validation | `VALIDATION` | `FloorPlanSet` + `PlanningSpec` | `ValidationReport` |
| 7. Refinement | `REFINEMENT` | `FloorPlanSet` + `ValidationReport` | Refined `FloorPlanSet` + `RefinementResult` |
| 8. Diversity | `DIVERSITY` | Refined `FloorPlanSet` + `PlanningSpec` | `DesignAlternativeSet` |
| 9. Explainability | `EXPLAINABILITY` | All intermediate artifacts | `DecisionTrace` |
| 10. Export & Rendering | `EXPORT_RENDERING` | `FloorPlanSet` + `DecisionTrace` | `ProjectBundleManifest` |

### Stage Execution & Status Tracking

Every stage execution is recorded in a `StageRecord` containing:
- `stage_name`: `StageName` enum.
- `status`: `StageStatus` (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `SKIPPED`, `PARTIAL`).
- `start_time` / `end_time` / `duration_ms`: High-resolution execution timing.
- `error_message`: Full error description if a stage fails.
- `metadata`: Diagnostic details (e.g., room count, iteration count, file count).

If any stage raises an exception, the orchestrator:
1. Marks the failed stage as `FAILED`.
2. Marks all subsequent dependent downstream stages as `SKIPPED`.
3. Sets `state.error` with the exception details.
4. Returns a partial `PipelineResult` with complete diagnostics rather than crashing unhandled.

### Configuration (`OrchestrationConfig`)

```python
@dataclass
class OrchestrationConfig:
    project_name: str = "PlanForge Project"
    output_dir: str = "outputs"
    num_alternatives: int = 1
    enable_refinement: bool = True
    max_refinement_iterations: int = 3
    enable_diversity: bool = False
    diversity_distance_threshold: float = 0.20
    enable_rendering: bool = True
    enable_exports: bool = True
    export_formats: list[str] = field(default_factory=lambda: ["png", "json", "md", "zip"])
```

---

## 4. REST API Layer (`app/api/`)

The API is exposed via FastAPI with routes mounted at both root (`/`) and `/api/v1/`.

### Endpoints

#### 1. `GET /health`
Returns system health, active LLM client mode, and rendering backend status.
```json
{
  "status": "ok",
  "service": "PlanForge AI",
  "version": "0.1.0",
  "llm_provider": "MockLLMClient (deterministic offline mode)",
  "device": "CPU (headless Agg)"
}
```

#### 2. `POST /generate` (or `POST /api/v1/generate`)
Synchronously triggers the full 10-stage orchestration pipeline.

**Request Body (`GenerationRequest`):**
```json
{
  "brief": "Single floor modern residence on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.\nFloor 1:\n- 1 living room of 300 sq ft\n- 1 kitchen of 150 sq ft",
  "project_name": "My Villa",
  "num_alternatives": 1,
  "enable_rendering": true,
  "enable_exports": true,
  "output_dir": "outputs"
}
```

**Response Body (`GenerationResponse`):**
```json
{
  "project_id": "proj_d7ed2f756fe1",
  "status": "completed",
  "is_success": true,
  "error_message": null,
  "validation_summary": {
    "overall_valid": true,
    "quality_score": 100.0,
    "error_count": 0,
    "warning_count": 0,
    "issue_summary": []
  },
  "stage_statuses": {
    "REQUIREMENTS": "COMPLETED",
    "PLANNING": "COMPLETED",
    "ASAA": "COMPLETED",
    "DESIGN_LLM": "COMPLETED",
    "GEOMETRY": "COMPLETED",
    "VALIDATION": "COMPLETED",
    "REFINEMENT": "COMPLETED",
    "DIVERSITY": "SKIPPED",
    "EXPLAINABILITY": "COMPLETED",
    "EXPORT_RENDERING": "COMPLETED"
  },
  "alternatives": [
    {
      "alternative_id": "alt_primary",
      "strategy": "default",
      "overall_valid": true,
      "num_floors": 1,
      "total_area_sqm": 41.81,
      "validation_summary": "VALID"
    }
  ],
  "bundle_path": "outputs/proj_d7ed2f756fe1",
  "decision_trace_available": true
}
```

#### 3. `GET /projects/{project_id}`
Retrieves high-level summary and validation report for a previously generated project.

#### 4. `GET /projects/{project_id}/trace`
Retrieves the complete, multi-stage `DecisionTrace` JSON structure for auditing entity lifecycles, rationales, and metrics.

#### 5. `GET /projects/{project_id}/alternatives`
Retrieves the neutral list of design alternatives generated for the project.

#### 6. `GET /projects/{project_id}/export?file=...`
Downloads exported artifacts (`bundle.zip`, `report.md`, `project.json`, `floor_1.png`).
- If `file` is omitted, serves the full bundle ZIP or project manifest JSON.
- If `file` is specified, verifies path safety and streams the requested file.

---

## 5. Security & Safety Mechanisms

### Filesystem Path Traversal Defense
The `resolve_safe_path` function validates every requested file path against the project bundle root:
- Rejects null bytes (`\0`).
- Rejects absolute paths (`/etc/passwd`, `C:\Windows\...`).
- Rejects relative navigation tokens (`..`).
- Resolves symlinks and canonical paths, verifying `resolved.is_relative_to(base_dir)`.
- If violation is detected, raises `PathTraversalSecurityError` mapped to HTTP 400 Bad Request.

---

## 6. How to Run and Test

### Starting the Server
Run directly with python or uvicorn:
```bash
# Direct startup
python main.py

# Or via uvicorn CLI
uvicorn app.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Interactive OpenAPI Swagger UI is available at:
`http://localhost:8000/docs`

### Running the Test Suite
All tests run 100% offline without network calls or external database services:
```bash
# Run unit tests for orchestration and API
pytest tests/unit/test_orchestration/ tests/unit/test_api/ -v

# Run integration tests
pytest tests/integration/test_orchestration_and_api.py -v

# Run full project test suite
pytest
```
Currently, **427 tests pass** across the entire repository.

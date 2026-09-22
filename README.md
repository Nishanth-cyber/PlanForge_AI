# PlanForge AI

PlanForge AI is a multi-stage, deterministic architectural floor plan generation and verification system. It transforms natural language architectural briefs into compliant, multi-floor residential layouts accompanied by deterministic geometry, independent validation reports, explainability decision traces, and publication-ready drawings.

---

## Authoritative Architecture

```
User Brief / REST API
  ↓
Stage 1: Requirement Agent       → Requirements            (WHAT)
  ↓
Stage 2: Planning Agent          → PlanningSpec            (STRATEGY)
  ↓
Stage 3: ASAA (Spatial Allocator)→ AllocationSet           (WHERE)
  ↓
Stage 4: LLM Architectural Design→ ArchitecturalDesignSet  (HOW)
  ↓
Stage 5: Geometry Engine         → FloorPlanSet            (CONSTRUCT)
  ↓
Stage 6: Independent Validator   → ValidationReport        (VERIFY)
  ↓
Stage 7: Refinement Loop         → Refined FloorPlanSet    (CORRECT)
  ↓
Stage 8: Diversity Generator     → DesignAlternativeSet    (DIVERSIFY)
  ↓
Stage 9: Explainability Engine   → DecisionTrace           (EXPLAIN)
  ↓
Stage 10: Export & Rendering     → ProjectBundleManifest   (PUBLISH)
```

---

## Quickstart

### 1. Installation

Ensure Python 3.11+ is installed. Install project dependencies:

```bash
pip install -e .
```

### 2. Running the API Server

Start the synchronous REST API server:

```bash
# Direct startup
python main.py

# Or via Uvicorn CLI
uvicorn app.api.app:app --host 0.0.0.0 --port 8000 --reload
```

Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

### 3. Example API Request

```bash
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{
    "brief": "Single floor residence on a 40 feet by 50 feet plot with front setback: 2m, rear setback: 2m, side setback: 2m.\nFloor 1:\n- 1 living room of 300 sq ft\n- 1 kitchen of 150 sq ft",
    "project_name": "My Bungalow",
    "num_alternatives": 1,
    "enable_rendering": true,
    "enable_exports": true
  }'
```

### 4. Running the Tests

The entire test suite runs 100% offline with zero external network or database dependencies:

```bash
# Run the full test suite (442 tests)
pytest

# Run research evaluation and benchmarking tests
pytest tests/unit/test_evaluation/ tests/integration/test_research_evaluation_runner.py -v
```

### 5. Running the Research Evaluation & Benchmarking Suite

Execute the full scientific evaluation across all 16 benchmark cases, ablations, reproducibility checks, and publication plots:

```bash
# Full evaluation run
python scripts/run_evaluation.py --output-dir results/evaluation_run

# Filter by category tags or specific cases
python scripts/run_evaluation.py --tags SINGLE_FLOOR MULTI_FLOOR
python scripts/run_evaluation.py --cases case_01_small_single_floor case_04_two_floor_family
```

### 6. Running the Web UI (Phase 14)

PlanForge AI provides a dedicated, interactive Web UI built with React 19, TypeScript, and Vite.

**Development Mode:**
```bash
# Terminal 1: Start the backend
uvicorn app.api.app:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2: Start the frontend development server
cd frontend
npm install
npm run dev
```
Navigate to `http://localhost:5173`.

**Production Mode (Single Server):**
```bash
# Build the frontend bundle
cd frontend
npm run build

# Run the backend (automatically serves the built UI at http://localhost:8000)
cd ..
uvicorn app.api.app:app --host 0.0.0.0 --port 8000
```

---

## Documentation

- [Architecture Reference](docs/ARCHITECTURE.md)
- [Requirement System (Phase 2)](docs/REQUIREMENT_SYSTEM.md)
- [Planning Agent (Phase 3)](docs/PLANNING_AGENT.md)
- [Spatial Allocation / ASAA (Phase 4)](docs/ASAA.md)
- [LLM Architectural Designer (Phase 5)](docs/ARCHITECTURAL_DESIGNER.md)
- [Geometry Engine (Phase 6)](docs/GEOMETRY_ENGINE.md)
- [Validator (Phase 7)](docs/VALIDATOR.md)
- [Refinement Agent (Phase 8)](docs/REFINEMENT_AGENT.md)
- [Diversity Generator (Phase 9)](docs/MULTI_DESIGN_DIVERSITY.md)
- [Explainability & Decision Trace (Phase 10)](docs/EXPLAINABILITY_AND_TRACE.md)
- [Export & Rendering (Phase 11)](docs/EXPORT_AND_RENDERING.md)
- [Orchestration & REST API (Phase 12)](docs/ORCHESTRATION_AND_API.md)
- [Research Evaluation & Benchmarking (Phase 13)](docs/RESEARCH_EVALUATION.md)
- [Web UI Architecture & Guide (Phase 14)](docs/UI.md)
- [Development Roadmap](docs/DEVELOPMENT_ROADMAP.md)


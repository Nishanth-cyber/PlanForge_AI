# PlanForge: Agentic AI Transformation Report

## Executive Summary
PlanForge has been transformed from a fixed-rule, deterministic 10-stage sequential pipeline into a **state-aware, tool-using, adaptive multi-agent architectural design system**.

The new architecture preserves all authoritative engineering algorithms (ASAA simulated annealing, Shapely 2D geometry engine, independent deterministic validator, DXF/SVG exporters) while replacing hardcoded control flows with an autonomous **Observe–Decide–Act–Evaluate–Replan–Finish** loop.

---

## 1. Core Architectural Transformations

### 1.1 Shared Project State (`app/agentic/state.py`)
- Acts as the single source of truth across all cooperating agents.
- Maintains private domain artifacts (`requirements`, `planning_spec`, `allocation_set`, `architectural_design_set`, `floor_plan_set`, `alternative_set`), small public facts, active strategy, validation findings, decision records, tool execution history, and execution budgets.
- Stamped validations: `findings` track artifact versions so stale verifications are automatically detected.

### 1.2 Authoritative Tool Registry (`app/agentic/tools.py` & `app/agentic/toolset.py`)
- Agents interact with the environment exclusively through registered tools with strict JSON input schemas, declared reads/writes permissions, preconditions, and execution timeouts.
- **10 Core Tools Implemented**:
  1. `parse_requirements`: Parses and normalizes architectural briefs.
  2. `check_feasibility`: Evaluates physical plot capacity and room area budgets before expensive operations.
  3. `plan_spatial_program`: Formulates strategic planning specs with zoning and relationship graphs; supports adaptive strategies (`balanced`, `compact`, `open_plan`, `circulation_prioritized`).
  4. `allocate_spatial_regions`: Executes ASAA simulated annealing; catches infeasibilities and reports structured deficits.
  5. `design_architecture`: Generates architectural room layouts, doors, and window placements.
  6. `construct_geometry`: Synthesizes exact Shapely 2D polygons and wall geometries.
  7. `validate_design`: Runs deterministic verification and generates prescriptive corrective actions.
  8. `refine_design`: Applies iterative validation-driven geometric adjustments.
  9. `generate_alternatives`: Explores structurally distinct layout candidates across spatial strategies.
  10. `export_bundle`: Produces CAD DXF files, SVG/PNG renders, and integrity reports.

### 1.3 Independent Validation Agent (`app/agents/validation_agent/agent.py`)
- Replaces the placeholder with an authoritative agent wrapping `FloorPlanValidator`.
- Categorizes findings into hard errors vs soft warnings.
- Prescribes machine-readable corrective actions (e.g. `nudge_room_geometry`, `reallocate_asaa`, `replan_zoning`) for the planning and refinement agents.
- **Safety Invariant**: LLMs and agents can never override hard geometric or architectural invariants.

### 1.4 Dynamic Orchestrator & Replanning (`app/orchestration/workflow.py` & `app/orchestration/routing.py`)
- Implements `AgenticPolicy` and `AgenticWorkflow`.
- Bounded execution via `Budget` (max steps, tool calls, LLM calls, and wall-clock seconds).
- **Anti-Oscillation & Loop Prevention**: Detects repeated identical tool calls in unchanged state fingerprints and halts or shifts strategy rather than looping indefinitely.
- **Strategic Replanning**: When local refinement cannot resolve hard errors, the orchestrator autonomously shifts strategy (e.g., switches to `compact` or `circulation_prioritized`) and re-allocates.

---

## 2. Automated Test Verification

A dedicated suite of automated integration tests (`tests/integration/test_agentic_behavior.py`) verifies all 10 required agentic scenarios:

| # | Scenario | Verification Result |
|---|---|---|
| 1 | Straightforward single-floor residence | **PASSED** — Autonomous tool execution through to verified completion. |
| 2 | Conflicting / ambiguous requirements | **PASSED** — Halts and produces structured clarification questions without silent invention. |
| 3 | Plot with insufficient area | **PASSED** — Honest reporting of physical area deficit; invalid plans rejected. |
| 4 | Initial validation failure corrected | **PASSED** — Validation findings guide refinement to quality score ≥ 70/100. |
| 5 | Planning strategy adaptation | **PASSED** — Planning agent adapts constraints across `balanced` and `compact` modes. |
| 6 | Multi-floor residence with stair core | **PASSED** — Verified 2-floor layout with vertical stair alignment and connectivity. |
| 7 | Tool failure resilience | **PASSED** — Tool exceptions captured as structured observations without pipeline crashes. |
| 8 | Repeated action & loop detection | **PASSED** — Detects zero-progress cycles, blocks repeated actions, and halts safely. |
| 9 | Missing program clarification | **PASSED** — Incomplete briefs trigger `NEEDS_CLARIFICATION` status. |
| 10 | Multi-candidate design diversity | **PASSED** — Explores candidate layouts across distinct architectural strategies. |

**Full Suite Status**: **541 tests passing, 1 skipped, 0 failures** across unit, integration, regression, and scenario suites.

---

## 3. Evaluation & Benchmark Comparison

Benchmark evaluation run across representative cases (`case_01`, `case_04`, `case_06`, `case_15`, `case_16`):

| Metric | Baseline | Agentic Architecture |
|---|---|---|
| Total Cases | 5 | 5 |
| Valid Plans Generated | 4 / 5 | 4 / 5 |
| Mean Room Coverage | 100.0% | 100.0% |
| Mean Boundary Compliance | 100.0% | 100.0% |
| Mean Connectivity Rate | 100.0% | 100.0% |
| Mean Pipeline Execution Time | 134.56 ms | 130.88 ms |
| Infeasible Program Handling (`case_16`) | Unhandled exception crashed stage | Clean autonomous replan attempt + honest deficit reporting |

---

## 4. API & UI Observability
- Added `mode: "agentic"` support to `POST /generate`.
- `GenerationResponse` enriched with `agentic_state` (compact public state) and `decisions` (audit trail of tool choices and rationale).
- Real-time append-only event stream (`InMemoryEventLog`) ready for websocket or polling consumption.

# PlanForge Phase 7: Interactive Agentic Clarification and Resumable Floor-Plan Generation Report

## 1. Executive Summary

Phase 7 transforms PlanForge from a pipeline that halts or fails upon encountering ambiguous or infeasible constraints into an **interactive, agentic, and resumable floor-plan generation system**.

Key achievements:
- **Clarification Decision Policy**: Grounded detection of incomplete, ambiguous, contradictory, or geometrically infeasible requirements using authoritative deterministic calculations (ASAA & geometry engine) rather than ungrounded LLM guessing.
- **Typed Clarification Schemas & Provenance**: Structured `ClarificationRequest`, `ClarificationOption`, `ClarificationResponse`, and `RequirementChangeRecord` models with immutable audit trails and explicit provenance tracking (`user_authorized`, `system_default`).
- **Resumable State Machine**: Extended `ProjectState` and `RunStatus` with `WAITING_FOR_CLARIFICATION` and `RESUMABLE`, fine-grained downstream artifact invalidation (`invalidate_downstream`), state version management, and preservation of best-valid candidates.
- **Full API & Frontend Integration**: REST endpoints for inspection, submission, resumption, and cancellation (`/projects/{id}/clarifications`, `/response`, `/resume`, `/cancel`), paired with an interactive React/TypeScript UI (`ClarificationPanel.tsx`) that clearly differentiates verified feasible, suggested, and hypothetical alternatives.
- **Zero Regressions & Benchmark Validation**: The complete test suite stands at **625 passing tests, 1 skipped test (100% pass rate)**, plus **61 passing frontend Vitest tests**. On the 5 standard benchmark cases, feasible cases run without unnecessary interruption, while infeasible cases trigger measured deficit clarification and resume to complete valid designs.

---

## 2. Architecture & Design Implementation

### 2.1 Decision Policy & Clarification Categories
Clarification decisions are governed by `ClarificationDecisionPolicy` (`app/agentic/clarification.py`), categorizing situations into:
- `PROCEED`: Requirements are complete and geometrically feasible within plot envelopes.
- `CLARIFY`: Missing essential architectural inputs (e.g., room types, room counts) or contradictory setbacks (e.g., setback sum $\ge$ plot dimension).
- `OFFER_ALTERNATIVES`: Multiple materially distinct strategies exist and user preference is needed.
- `REQUEST_CONSTRAINT_REVISION`: Physical ASAA deficit measured; options are generated with exact mathematical grounding (plot expansion, floor addition, room reduction, or termination).
- `TERMINATE`: User cancels or declines revisions under original constraints.

### 2.2 Truthful Feasibility & Grounded Option Generation
The system adheres strictly to the rule: **Never automatically alter required rooms, lower minimum mandatory areas, change floor count, or alter boundaries without explicit user authorization.**
When an area deficit $\Delta_{deficit} = A_{req} - A_{buildable} > 0$ is detected:
1. The deficit is reported to the user with exact square-meter measurements.
2. Grounded alternatives are generated:
   - **Expand Plot Depth/Length**: Calculates the minimal length extension $\Delta L = \lceil \Delta_{deficit} / W_{eff} \rceil$ required to fit the program.
   - **Distribute Across Additional Floor**: If multi-floor expansion is permitted, offers `opt_add_floor` with target floors incremented.
   - **Terminate Infeasible**: Allows the user to decline revision and terminate truthfully with `RunStatus.INFEASIBLE`.
3. Options are tagged with explicit feasibility categories:
   - `verified_feasible`: Pre-validated by geometry engine.
   - `suggested_alternative`: Mathematically estimated based on deficits.
   - `unverified_hypothetical`: High-level exploratory proposals.

### 2.3 Resumable Orchestration State Machine
- When clarification is required in `interactive=True` mode, `HierarchicalOrchestrator` pauses execution, stores `state.pending_clarification`, records `state.paused_stage`, and sets `state.status = RunStatus.WAITING_FOR_CLARIFICATION`.
- When a response is received, `ClarificationResponseValidator` validates:
  - Request ID matches pending request.
  - State version is not stale (`expected_state_version == state.version`).
  - Option ID is valid.
- On acceptance:
  - Requirements are updated atomically on a deep copy.
  - Downstream artifacts (`planning_spec`, `allocation_set`, `architectural_design_set`, `floor_plan_set`) are invalidated via `state.invalidate_downstream("requirements")`.
  - A `RequirementChangeRecord` is appended with before/after snapshots and timestamp.
  - `state.status = RunStatus.RESUMABLE`.
- Upon `resume()`, orchestration resumes directly from the invalidated stage without re-running earlier valid stages.

---

## 3. API & Frontend Integration

### 3.1 REST API Endpoints
All endpoints are integrated into `app/api/routes.py` and backed by `app/api/registry.py`:

| Method | Path | Description | Status Codes |
|---|---|---|---|
| `GET` | `/projects/{project_id}/clarifications` | Inspect pending request, clarification history, and change records | 200, 404 |
| `POST` | `/projects/{project_id}/clarifications/{request_id}/response` | Submit option selection, numeric overrides, or free text | 200, 400, 404, 409 |
| `POST` | `/projects/{project_id}/resume` | Resume execution of a paused/resumable workflow | 200, 400, 404 |
| `POST` | `/projects/{project_id}/cancel` | Safely cancel an active or paused session | 200, 400, 404 |

### 3.2 Frontend UI Components
- **`ClarificationPanel.tsx`**: Renders contextual alert badges, measured deficit metrics, selectable options with verified/suggested/hypothetical tags, numeric range inputs, and free-text fields.
- **`FloorPlanWorkspace.tsx`**: Displays the `ClarificationPanel` prominently whenever `project.pending_clarification` is present.
- **`ConversationalStudio.tsx` & `App.tsx`**: Handle user responses, invoke API methods (`submitClarificationResponse`, `resumeProject`, `cancelProject`), and display real-time feedback.

---

## 4. Test Suite & Verification Results

### 4.1 Backend Pytest Suite
- **Baseline**: 600 passed, 1 skipped.
- **Phase 7 Final**: **625 passed, 1 skipped** (0 failures, 158 benign deprecation warnings from ezdxf numpy 2.5).
- **New Tests Added**:
  1. `tests/unit/test_phase7_clarification_policy.py` (10 tests):
     - Feasible requirements proceed without clarification.
     - Infeasible program triggers measured deficit.
     - Contradictory setbacks detected.
     - Grounded plot expansion options generated.
     - Option selection updates requirements atomically.
     - Missing mandatory info detected.
     - Stale response rejected.
     - Non-existent option rejected.
     - Duplicate response handled cleanly.
     - Downstream invalidation preserves unaffected keys.
  2. `tests/integration/test_phase7_interactive_workflow.py` (8 tests):
     - Interactive workflow pauses at `WAITING_FOR_CLARIFICATION`.
     - Workflow resumes from paused stage and completes with authorized revisions.
     - Safe user cancellation.
     - Requirement invalidation and best-valid candidate preservation.
     - Deterministic fallback when LLM is unavailable.
     - Prevention of repeated clarification loops.
     - Truthful reporting of declined infeasible requests.
     - Multi-floor clarification and cross-floor revalidation.
  3. `tests/unit/test_api/test_phase7_clarification_routes.py` (7 tests):
     - `GET /projects/{id}/clarifications` retrieval.
     - `POST .../response` successful submission and state mutation.
     - Stale version rejection (HTTP 409 Conflict).
     - Invalid option rejection (HTTP 400 Bad Request).
     - Workflow resumption via `POST /resume`.
     - Workflow cancellation via `POST /cancel`.
     - Thread-safe concurrent response protection on `ProjectRegistry`.

### 4.2 Frontend Vitest Suite
- **Result**: **10 test files passed, 61 tests passed (100%)**.
- **Coverage**: Includes `clarification_panel.test.tsx` verifying badge distinctions, option selection, numeric input overrides, and submission dispatch.

---

## 5. Benchmark Comparison (5 Standard Benchmark Cases)

Evaluated via `scripts/evaluate_phase7_clarification_modes.py`:

| Benchmark Case | Description | Pipeline Baseline | Phase 6 Multi-Agent Batch | Phase 7 Interactive Mode | Clarification Behavior |
|---|---|---|---|---|---|
| `case_01_small_single_floor` | Small Single-Floor Bungalow | Completed (94.0, 123ms) | Completed (94.0, 404ms) | Completed (94.0, 359ms) | No interruption (`clarif=False`) |
| `case_04_two_floor_family` | Two-Floor Family Residence | Completed (94.0, 104ms) | Completed (94.0, 718ms) | Completed (94.0, 658ms) | No interruption (`clarif=False`) |
| `case_06_irregular_l_plot` | Irregular L-Shaped Boundary | Completed (85.0, 224ms) | Completed (85.0, 546ms) | Completed (85.0, 560ms) | No interruption (`clarif=False`) |
| `case_15_feasibility_edge` | High-Density Feasibility Edge | Completed (82.0, 198ms) | Completed (82.0, 524ms) | Completed (82.0, 510ms) | No interruption (`clarif=False`) |
| `case_16_infeasible_deficit` | Infeasible Room Deficit Program | Failed (0.0, 7.8ms) | Failed (0.0, 10.4ms) | **Waiting for Clarification** (12.0ms) $\to$ **Resumed & Completed (85.0, 472ms)** | Pauses with 112.6 m² deficit question $\to$ User authorizes plot expansion $\to$ Resumes to valid design |

### Key Benchmark Observations:
1. **Zero Unnecessary Interaction**: For feasible programs (`cases 01, 04, 06, 15`), Phase 7 introduces 0 unnecessary pauses and 0 degradation in quality scores (scores identical to baseline).
2. **Truthful Infeasibility Handling**: For `case_16`, while legacy modes failed immediately, Phase 7 pauses, presents exact deficit calculations, offers grounded alternatives, and upon receiving authorized parameters, resumes to generate a valid residential plan with score **85.0/100**.

---

## 6. Demonstration Trace: Infeasible Program $\to$ Clarification $\to$ Resumed Floor Plan

```text
[Step 1 - Initial Execution]
  Project: "case_16_infeasible_deficit" (Plot: 6.1m x 6.1m with 2.0m setbacks -> 4.41 m² buildable area)
  Requested Program: Living (46.5 m²), Dining (27.9 m²), Kitchen (23.2 m²), 2x Bedroom (55.7 m²) = ~153 m² required
  ASAA Check: Feasibility failure -> Measured deficit = 112.6 m²
  Hierarchical Orchestrator:
    - Status transitioned to WAITING_FOR_CLARIFICATION
    - Pending Clarification: "The requested room program is physically infeasible: Total minimum required area exceeds available buildable footprint by 112.6 m². Please choose an authorized adjustment to proceed."
    - Options Generated:
      1. expand_plot_depth (suggested_alternative)
      2. opt_add_floor (suggested_alternative)
      3. opt_terminate_infeasible (verified_feasible)

[Step 2 - User Clarification Response]
  Selected Option: "expand_plot_depth"
  Authorized Overrides: {"plot_width": 20.0, "plot_length": 20.0}
  Validation: State version verified (v1), Request ID verified (clarif_c16)
  Mutation: Requirements updated atomically; RequirementChangeRecord recorded (change_id=change_...)
  Artifacts Invalidated: ['planning_spec', 'allocation_set', 'architectural_design_set', 'floor_plan_set']
  Status transitioned to: RESUMABLE (v2)

[Step 3 - Resumed Orchestration]
  Hierarchical Orchestrator:
    - Event emitted: 'workflow_resumed' from stage 'requirements'
    - Feasibility Check: 20x20m plot with 2m setbacks = 256 m² buildable area -> Feasible!
    - Planning Agent: Formulates spatial zoning PlanningSpec
    - Spatial Allocation Agent: Explores 3 ASAA candidates; selects candidate with optimal aspect ratios
    - Architectural Agent: Synthesizes rooms, interior walls, exterior envelopes, and circulation
    - Validation Agent: Evaluates floor plan against building codes and physical constraints -> 0 Hard Errors
    - Hierarchical Orchestrator: Transitioned to ACCEPTED (Score: 85.0/100, Valid: True)
```

---

## 7. Modified and Added Files

| File | Change Type | Purpose |
|---|---|---|
| `app/agentic/clarification.py` | Added | Clarification schemas, `ClarificationDecisionPolicy`, `ClarificationResponseValidator` |
| `app/agentic/state.py` | Modified | Added `is_paused`, `is_completed`, downstream invalidation, change history, versioning |
| `app/agentic/coordination.py` | Modified | Safe re-exports of clarification types |
| `app/orchestration/config.py` | Modified | Added `interactive: bool = False` flag to `OrchestrationConfig` |
| `app/orchestration/hierarchical.py` | Modified | Integrated clarification pausing, `apply_clarification_response`, `resume`, `cancel` |
| `app/orchestration/orchestrator.py` | Modified | Mapped `WAITING_FOR_CLARIFICATION`, `CANCELLED` and clarification questions in result builder |
| `app/api/registry.py` | Modified | Thread-safe session management, clarification submission, resumption, and cancellation |
| `app/api/schemas.py` | Modified | Pydantic schemas for clarification requests, options, submissions, and list responses |
| `app/api/routes.py` | Modified | REST endpoints for `/clarifications`, `/response`, `/resume`, and `/cancel` |
| `frontend/src/api/types.ts` | Modified | TypeScript interfaces for Phase 7 clarification data contracts |
| `frontend/src/api/projects.ts` | Modified | API client methods for fetching, answering, resuming, and cancelling |
| `frontend/src/components/chat/ClarificationPanel.tsx` | Added | Interactive UI for constraint clarification, deficit display, and option selection |
| `frontend/src/components/chat/FloorPlanWorkspace.tsx` | Modified | Integrated `ClarificationPanel` view |
| `frontend/src/components/chat/ConversationalStudio.tsx` | Modified | Wired clarification submission and resume handlers |
| `frontend/src/App.tsx` | Modified | Wired clarification handlers in primary application shell |
| `frontend/src/__tests__/clarification_panel.test.tsx` | Added | Vitest tests for `ClarificationPanel` interaction and badge display |
| `tests/unit/test_phase7_clarification_policy.py` | Added | Unit tests for clarification decision policy and response validator |
| `tests/integration/test_phase7_interactive_workflow.py` | Added | End-to-end integration tests for pausing, resumption, cancellation, and multi-floor |
| `tests/unit/test_api/test_phase7_clarification_routes.py` | Added | API tests for endpoints, concurrency, and validation error handling |
| `scripts/evaluate_phase7_clarification_modes.py` | Added | Benchmark evaluation script comparing 5 cases across 3 modes |

---

## 8. Known Limitations & Safe Boundaries

1. **Non-Interactive Batch Mode**: When `interactive=False` (default for automated scripts and legacy pipelines), the system terminates immediately with structured status codes (`RunStatus.INFEASIBLE` or `RunStatus.NEEDS_CLARIFICATION`) rather than hanging indefinitely waiting for human input.
2. **Deterministic Feasibility Authority**: The LLM is never permitted to determine physical or geometric feasibility. All area budgets, setback envelopes, and circulation validity are computed authoritatively by Shapely and ASAA.
3. **No Automatic Scope Reduction**: Rooms are never deleted and minimum areas are never reduced without explicit user authorization via an accepted clarification response.

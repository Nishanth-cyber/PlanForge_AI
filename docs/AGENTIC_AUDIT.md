# PlanForge Agentic Transformation - Phase 1 Audit

Status: Phase 1 (audit) partially complete. Every finding below was verified by reading the cited file.
Files not yet read are listed under "Not yet audited" and must not be assumed to behave any particular way.

## 1. Actual execution path (user input -> output)

```
API/CLI -> PlanForgeOrchestrator.generate()            app/orchestration/orchestrator.py
  1 REQUIREMENT   RequirementAgent.process() | CompletenessGate.check()
  2 PLANNING      PlanningAgent.plan()                  (deterministic, no LLM)
  3 ASAA          ASAAAllocator.allocate()              (one call, fixed params)
  4 ARCH_DESIGN   ArchitecturalAgent.design()           (1 LLM call per floor)
  5 GEOMETRY      GeometryEngine.construct()
  6 VALIDATION    FloorPlanValidator.validate()
  7 REFINEMENT    RefinementLoop.run()                  (only if invalid and enabled)
  8 MULTI_DESIGN  MultiDesignGenerator.generate() | single wrapper
  9 EXPLAIN       DecisionTraceBuilder.build()          (post-hoc reconstruction)
 10 EXPORT        export_project_bundle()
```

The sequence is hardcoded as straight-line code in `generate()`. The only conditional branches are
"requirements incomplete -> stop", "validation failed and refinement enabled -> run refinement", and
"num_alternatives > 1". Any stage exception skips every downstream stage (`skip_downstream_stages`).

## 2. Findings (fixed-rule bottlenecks and false-agent patterns)

| # | Location | Finding | Severity |
|---|----------|---------|----------|
| F1 | `orchestration/orchestrator.py::PlanForgeOrchestrator.generate` | Fixed 10-stage linear script. Nothing downstream can send work back upstream. No replanning, no strategy change, no clarification mid-run. | Core |
| F2 | `orchestration/routing.py`, `graph.py`, `workflow.py`, `api/websocket.py`, `agents/validation_agent/agent.py` | Empty placeholder modules (docstring only). The "validation agent" and any live-event channel do not exist. | Core |
| F3 | `orchestration/state.py::PipelineState` | Accumulator of stage outputs only. No decision log, tool-call log, open questions, findings history, budget, or acceptance evidence. | Core |
| F4 | `agents/planning_agent/agent.py::PlanningAgent.plan/_plan_floor` | Pure deterministic pipeline (steps A-F per floor). No LLM, no strategy choice, cannot ask questions or be revised by ASAA/validation. `no_corridor` is derived by substring match on `raw_input` (`_build_global_constraints`). | Core |
| F5 | `asaa/allocator.py::ASAAAllocator._allocate_floor` | Fixed parameters: `num_candidates=3`, `seed=42`, `circ_ratio=0.12`, `staircase_area_sqm=8.0`, refiner `max_iterations=8`. Only the best candidate is kept; the rest are discarded. If no candidate is valid it silently picks the highest-scoring invalid one. No infeasibility/trade-off report leaves the allocator. | Core |
| F6 | `agents/architectural_agent/agent.py` | One LLM call per floor, no feedback channel. Output is bounds-validated (good, keep). An LLM timeout raises and fails the whole pipeline: no retry, no fallback flag. Mock generator is a hardcoded rule table (e.g. entrance always "south", windows always "north"/"east"). | High |
| F7 | `agents/refinement_agent/loop.py::RefinementLoop.run` | `for iter_idx in range(max)` calling the same `refine()` each time. The agent can only edit doors/windows/dimensions, never allocation or planning, so it cannot "reconsider zoning". Infeasibility is detected by substring match on issue messages ("deficit", "exceeds available buildable area"). It never compares the new report with the previous one: on `MAX_ITERATIONS_REACHED` it returns the last design even if it scored worse than an earlier one. Fingerprint oscillation / no-change detection exists (keep and reuse). | Core |
| F8 | `agents/refinement_agent/agent.py` | `RefinementAgent.__init__` uses `LLMConfig()` (provider "mock") whereas `ArchitecturalAgent` uses `LLMConfig.from_env()`. Consequence: the default orchestrator always refines with the keyword-triggered mock (fixed 1.05x growth, windows forced to "north") even when `PLANFORGE_LLM_PROVIDER=huggingface`. | High (verified in code; effect at runtime not yet run) |
| F9 | `orchestration/orchestrator.py` tail (`final_status`) | Status is downgraded only when `cfg.enable_refinement` is true. With refinement disabled, an invalid plan is returned as `"completed"` (`is_success` is true). | High (violates "invalid plans are not marked successful") |
| F10 | `orchestration/orchestrator.py` Stage 8 | When alternatives are generated, `state.floor_plan_set` / `validation_report` are overwritten by `alternatives[0]`, replacing the refined primary result. Not guaranteed to be the validated design. | Medium |
| F11 | `models/validation.py` | `ValidationIssue` has severity/category/details/target_id but no suggested corrective action, no hard/soft flag, no machine-readable code. `ValidationReport.overall_valid` returns `True` for an empty `results` list. | High |
| F12 | `chat/agentic_decision.py::decide` | Named "agentic" but is a hardcoded template table (`_GROUND_FLOOR_*`, `_UPPER_FLOOR_*`) with thresholds (80/160 m2, 200 m2) and silent-style defaults (30x40 ft plot, north entrance). It is only reached on explicit user delegation and explains each choice (acceptable), but it is rule-based, and it appends text to `reqs.raw_input` to get past the completeness gate. | Medium |
| F13 | `chat/orchestrator.py` | Intent routing is regex (`classify_intent`). The LLM only phrases chat replies or extracts requirement JSON that is re-merged by deterministic code. No LLM-driven action selection. | Medium |
| F14 | `agents/requirement_agent/completeness_gate.py` | Asks good targeted questions for plot / floors / rooms-per-floor. `STATUS_AMBIGUOUS` is defined but `check()` never returns it, so contradictions are not detected. Missing setbacks produce a warning claiming "standard municipal setbacks will be used" (default source not yet verified). | High |
| F15 | `explainability/builder.py::DecisionTraceBuilder.build` | Runs at stage 9 and reconstructs events from final artifacts. Honest (read-only, no invented facts) but records outputs, not decision-time rationale, tool calls, rejected ASAA candidates, or failed refinement attempts. | High |
| F16 | `llm/client.py`, `llm/configuration.py` | Only `generate(prompt, system_prompt) -> str`. No token/usage accounting, retry/backoff, structured action interface, or per-run budget. Errors are typed (`HuggingFaceTimeoutError` etc.), but callers do not catch them. `create_default_orchestrator(config)` ignores its argument. | High |

Secrets note: `.env` exists in the repo root. It was deliberately NOT read. Any new code must keep
reading keys only via `LLMConfig.from_env()` and never serialize them.

## 2b. Second-pass findings (API, frontend, validator, budgeter, diversity, explainability, evaluation)

| # | Location | Finding | Severity |
|---|----------|---------|----------|
| F17 | `frontend/src/components/views/NewProjectView.tsx` | **Simulated progress.** While `isLoading`, a `setInterval` (1400 ms) advances `activeStageIndex` through 8 hardcoded stage names. It is unrelated to backend execution and violates the requirement that the UI reflect real events. | Core |
| F18 | `api/routes.py::generate_floor_plan`, `frontend/src/api/projects.ts::generateFloorPlan` | `POST /generate` is one synchronous blocking call returning only post-hoc `stage_statuses`. No job id, no event stream, no polling endpoint. `ProjectRegistry` stores only final `PipelineResult`s. | Core |
| F19 | `asaa/area_budgeter.py` -> `orchestrator.py` Stage 3 | `AreaBudgeter` raises `InfeasibleAllocationError` with structured data (`deficit_sqm`, `offending_rooms`, `floor_number`). The orchestrator's generic `except Exception` flattens it into `status="failed"` + a string, so infeasibility is indistinguishable from a crash. The evaluation run classifies this case's cause as "Validation" although it is raised in ASAA. | High |
| F20 | `completeness_gate.py` vs `asaa/boundary.py` | The gate warns "Standard municipal setbacks will be used", but `BuildableBoundaryCalculator` applies **no** setbacks when none are given (buildable = plot). The warning is misleading (correction to F14). Separately, `_derive_plot_polygon` silently falls back to a 1.5:1 rectangle, and to 200 m2 when no area is given; the gate normally prevents reaching this, but direct callers are not protected. | Medium |
| F21 | `agents/diversity_agent/generator.py::MultiDesignGenerator.generate` | All alternatives share ONE ASAA allocation and differ only by an architectural strategy cycled from a fixed pool of 6 (`strat = pool[idx % len]`). Room-region layout is never varied, so "alternatives" are limited to door/window/dimension variants. Candidate failures are recorded as rejections (good, reusable). | High |
| F22 | `explainability/recorder.py::TraceRecorder`, `decision_log.py`, `event_tracker.py`, `logger.py` | `TraceRecorder` is a real runtime accumulator but is **unused** by the orchestrator; the other three modules are empty placeholders. `DecisionType` has no action/tool/replan types. `DecisionEvent` is JSON-serializable and reusable. | High |
| F23 | `validation/validator.py::FloorPlanValidator` | Deterministic, solid (13 categories, score = 100 - 15/error - 3/warning). `ValidationIssue.check` acts as a machine code; severity "error" == hard. No suggested actions. An empty `floor_plan_set` yields an empty report that is `overall_valid == True` (see F11). | High |
| F24 | `evaluation/runner.py::BenchmarkRunner` | Calls `orchestrator.generate(case.brief, project_name=, config=)` with `enable_exports=False`, `enable_rendering=False`. Any agentic orchestrator exposing the same `generate()` signature and returning `PipelineResult` (with populated `stage_records`) can be benchmarked unchanged. | Info (enabler) |
| F25 | `results/evaluation_run/*` (recorded 2026-09-20, mock LLM, seed 42) | 15/16 cases valid with 0 hard errors on the first pass; `timing_refinement_ms` ~ 0. **The existing benchmark never exercises refinement**, so it cannot measure refinement success or replanning. New fault-injection cases are required. Metric anomalies to investigate before reuse: `trace_entity_chain_completeness` mean = 559 (not a 0-100 percentage); `alternative_validity_rate` = 0 while 15 plans are valid. | High |
| F26 | `frontend/.../NewProjectView.tsx::handleGenerate` | Hardcodes `max_refinement_iterations: 3` (API default is 5) and shows "Standard architectural adjacencies will be applied automatically", i.e. a client-side promise about backend defaults. | Low |

### Plan amendment (Phase 3 package location)
`app/orchestration/__init__.py` eagerly imports the orchestrator (shapely, geometry, LLM, export). Putting the new core there would make it
impossible to unit-test in isolation. Phase 3 therefore lives in a NEW stdlib-only package `app/agentic/` (additive; picked up by the
existing setuptools `include = ["app*"]`). The placeholder files in `app/orchestration/` stay untouched for now. Domain tool adapters
(Phase 4) will be the only modules importing the existing components.

## 3. Components that are genuinely reusable as tools (keep unchanged)

- `CompletenessGate.check`, `RequirementAgent.process/update`
- `AreaBudgeter.compute_budget`, `ASAAAllocator.allocate(num_candidates=, seed=)` (already parameterized)
- `ArchitecturalOutputValidator`, `RefinementOutputValidator` (contract enforcement)
- `GeometryEngine.construct`, `FloorPlanValidator.validate` (authoritative)
- `RefinementLoop._compute_fingerprint` (repeat/oscillation detection)
- `MultiDesignGenerator`, DXF/JSON/PNG/bundle exporters, `verify_export_integrity`

## 4. Not yet audited (do not assume)

Audited in the second pass: `api/routes.py`, `schemas.py`, `registry.py`, `dependencies.py`, `app.py`; frontend `NewProjectView.tsx`, `RefinementView.tsx`, `api/projects.ts`;
`validation/validator.py`; `asaa/area_budgeter.py`, `boundary.py`, `exceptions.py`; `diversity_agent/generator.py`; `explainability/*`; `evaluation/runner.py`; `models/refinement.py`; `results/evaluation_run/*`.

Still NOT audited (do not assume): `requirement_agent/parser.py`, `pipeline.py`, `normalizer.py`; `chat/intent.py`, `chat/llm_service.py`;
`geometry/engine.py` and builders; `asaa/candidate_generator.py`, `refiner.py`, `scoring.py`; `validation/*_validator.py` internals;
`evaluation/metrics.py`, `ablation.py`, `benchmark.py`; remaining frontend files; test bodies; `docs/*.md` claims.

## 5. Proposed implementation plan (additive; baseline path preserved)

Principle: `PlanForgeOrchestrator.generate()` stays as the untouched baseline (`mode="pipeline"`). The agentic
path is opt-in via a new `OrchestrationConfig.mode = "pipeline" | "agentic"` so baseline vs. agentic can be
compared on identical benchmark cases and existing tests keep passing.

Phase 2 (baseline, needs the user to run commands; see handoff): record test counts and evaluation output.

Phase 3 - orchestration core (fill the existing placeholders instead of adding a new framework):
- `orchestration/state.py`: add `ProjectState` (requirements, open questions, strategy, candidates, tool-call log,
  findings history, decision log, budget, acceptance evidence). Existing `PipelineState` stays.
- `orchestration/tools.py` (new): `ToolSpec` (name, input schema, output schema, side effects, error contract) and a
  registry wrapping the reusable components in section 3. No tool may write geometry directly or skip validation.
- `orchestration/routing.py`: `ActionPolicy` interface. Two implementations: `LLMActionPolicy` (JSON action
  proposal, schema-validated against allowed tools and preconditions) and `DeterministicFallbackPolicy`.
  Every decision records `decision_source = "llm" | "fallback"` and the reason for fallback.
- `orchestration/graph.py`: tool preconditions/effects (e.g. geometry requires allocation + design; finish requires
  a valid report). The policy can only choose among currently legal actions.
- `orchestration/workflow.py`: `AgenticWorkflow` observe -> decide -> act -> evaluate loop with budgets
  (steps, LLM calls, wall time), repeated-action detection (action + argument hash + state fingerprint), and
  stop conditions (accepted / infeasible / needs_clarification / budget_exhausted).

Phase 4 - agent roles as policy-driven wrappers over those tools (Requirement, Planning, ASAA, Design,
Validation, Refinement). Required component changes:
- Validation: extend `ValidationIssue` additively with `code`, `hard`, `suggested_actions`, `evidence` (defaults keep
  current serialization); implement `agents/validation_agent/agent.py` as a thin wrapper that never overrides the validator.
- ASAA: expose `candidates` + rejection reasons + infeasibility report from the allocator (additive return), and
  accept `circulation_ratio`, `num_candidates`, `seed`, staircase area as tool arguments (replacing F5 constants as defaults only).
- Refinement: keep best-so-far design by score; add "escalate" actions (re-run ASAA with new parameters, switch design
  strategy, ask user, declare infeasible).
- Requirement: add contradiction detection that can return `STATUS_AMBIGUOUS` (F14).
- Fix F8 (consistent LLM config), F9 (never "completed" when invalid), F10 (preserve validated primary).

Phase 5 - recovery/safety: LLM timeout -> typed error -> explicit fallback with flag; retry bounded; tool exceptions
become observations, not crashes.

Phase 6 - explainability: live `DecisionRecorder` events emitted during execution (append-only), linked to tool-call ids,
requirement ids, validation issue ids, region/room ids; `DecisionTraceBuilder` kept for artifact-derived facts and merged.

Phase 7 - integration: SSE or WebSocket (`api/websocket.py`) streaming real recorder events; frontend panel reads them.
No secrets or raw reasoning text sent to the frontend. Public API responses stay backward compatible.

Phase 8 - tests (mock LLM, deterministic) for the ten required scenarios plus the specific behavior assertions;
a separate live-LLM test skipped unless credentials are present.

Phase 9 - docs and evaluation report: baseline vs agentic with mock/live/untested clearly labeled.

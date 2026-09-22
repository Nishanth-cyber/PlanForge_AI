# Previous Project Reuse Map

> Analysis-only document. No implementation was performed to produce this file.
> Old project inspected: `D:\23ALR060\PlanForge_AI` (workspace snapshot as supplied).
> New project inspected: `D:\23ALR060\Projects\Planforge` (current scaffold, verified live via filesystem access).

---

## 1. Purpose

This document maps every reusable component of the previous PlanForge AI codebase onto the new
seven-stage architecture (Requirement Agent → Planning Agent → ASAA → LLM Architectural Designer →
Geometry Engine → Validator → Refinement Agent), and records exactly what must be **kept, reused,
modified, rewritten, replaced, or dropped**, with the concrete old file path and the concrete new
file path (verified to already exist in the scaffold). It also records specific bugs and
architectural violations found in the old code so they are not silently re-introduced.

No migration was performed. No code was written. This is Phase 0 (analysis) only.

---

## 2. Previous Project Sources Inspected

| Source | What it is | How it was used here |
|---|---|---|
| `workspace_all_files.md` | Full consolidated source dump of `D:\23ALR060\PlanForge_AI` (229 files: `src/`, `backend/`, `frontend/`, `config/`, `docs/`, `scripts/`, `tests/`) | Primary evidence base. Every claim below is grounded in code actually read from this dump. |
| `Project_Plan.txt`, `Sheet.txt`, `Research Paper Writing.pptx`, `PlanForge.docx` | Referenced in the task brief | **Not present in the materials actually supplied to this analysis** — only `workspace_all_files.md` was attached and readable. Any conclusions those files might change (research framing, terminology) are therefore **not** reflected here. This is flagged explicitly rather than guessed at. |
| Live scan of `D:\23ALR060\Projects\Planforge` | Current new-project scaffold | Used to confirm real target file paths for every mapping below (all new-side paths in the table were verified to exist on disk before being written into this document). |

---

## 3. Previous Architecture Summary (as actually implemented, not as documented)

The old project's own docs (`docs/architecture.md`, `docs/PROJECT_COMPLETION_PLAN.md`) describe a
clean separation between "conversational AI" and "deterministic geometry." **The actual code does
not match that description in one important respect**: ASAA in the old project does not stop at
allocation. `src/asaa/algorithm.py`, `src/asaa/space_filling_partitioner.py`, and
`src/asaa/multi_floor_partitioner.py` each directly:

- construct final `Room` objects with exact usable/built Shapely polygons,
- call `geometry/doors.py::generate_doors()` to place actual doors,
- call `validation/validator.py::run_full_validation()`,
- and (in `asaa/refinement_engine.py`) add/remove/repair doors in a loop until validation passes.

So in the old project, **ASAA = allocation + final geometry + doors + refinement**, all in one
package. There is no LLM step anywhere in this pipeline — `use_llm` exists as a boolean flag but
(see §17, Known Bugs) does not actually route to an LLM call for requirement structuring, and no
"architectural design" LLM stage exists at all. The old pipeline is, in truth:

```
User text → RequirementAnalysisAgent (regex/state-machine, NOT an LLM call)
          → GenerationService.generate()
          → ASAA (priority → allocation → candidate placement → geometry → doors → validation → refinement, all inside asaa/)
          → Export/Render
```

This is the architecture that must **not** be carried forward as-is.

---

## 4. New Architecture Summary (target, as defined for this project)

```
User Intent
  → Requirement Agent   (structured requirements; no invention)
  → Planning Agent      (planning spec: priorities, relationships, circulation intent — no geometry)
  → ASAA                (WHERE: spatial partitioning + allocated regions only)
  → LLM Architectural Designer (HOW: room shape/dims/doors/windows intent, within ASAA regions)
  → Geometry Engine     (CONSTRUCT: deterministic polygons/walls/doors/windows from the design)
  → Validator           (VERIFY: deterministic, authoritative, LLM cannot self-certify)
  → Refinement Agent    (CORRECT: revise LLM design from validator feedback, loop back to Geometry Engine)
```

Verified to already exist on disk, matching this shape: `app/agents/{requirement,planning,
architectural,refinement,validation}_agent/`, `app/asaa/`, `app/geometry/`, `app/validation/`,
`app/models/`, `app/orchestration/`, `app/llm/`, `app/explainability/`, `app/export/{dxf,json,png}/`,
`app/rendering/`, `app/config/`, `app/utils/`, `app/api/`.

---

## 5. Architecture Conflicts (old vs. new — must be resolved during migration, not carried over)

| # | Conflict | Old behavior | New requirement | Resolution direction |
|---|---|---|---|---|
| 1 | ASAA owns final geometry | `asaa/algorithm.py::_build_floor_plan()` builds exact `Room.geometry` (usable + built polygons) via `asaa/allocator.py::place_room()` → `candidate_generator.py` | ASAA must output allocated **regions**, not final room polygons | Strip `to_room_geometry()` / `Candidate.built_geometry` finality out of ASAA's output contract; ASAA emits a region (bounding area + adjacency tags + priority), not a committed shape |
| 2 | ASAA owns doors | `asaa/algorithm.py` calls `geometry/doors.py::generate_doors()` directly inside the allocation pipeline | Doors are an LLM Architectural Designer proposal, constructed by Geometry Engine | Move door *placement intent* to the Architectural Designer stage; move door *construction* (exact swing geometry) to Geometry Engine; move door *checking* to Validator |
| 3 | ASAA owns refinement | `asaa/refinement_engine.py::refine_floor_plan()` repairs missing/forbidden doors and unreachable rooms by mutating `FloorPlan.doors` directly, called from inside `asaa/algorithm.py` | Refinement is a distinct LLM-driven stage that revises the *architectural design*, not a sub-routine of allocation | Extract the door/connectivity repair *heuristics* (they are useful) into the new Refinement Agent as a deterministic fallback/aid, not as part of ASAA |
| 4 | "LLM" claims without an LLM call | `backend/services/chat_service.py::ChatService.chat()` never invokes Ollama; it only calls `RequirementAnalysisAgent.process_turn()` (regex/state machine). Ollama is pinged only in `check_ollama_status()` | New architecture requires a real LLM Architectural Designer stage with actual structured-output calls | New `app/llm/client.py` + `app/agents/architectural_agent/agent.py` must perform genuine LLM calls; do not repeat the old pattern of a UI badge claiming "Qwen3:4B analyzing..." while no model is invoked |
| 5 | Requirement invention on the ungated path | `backend/services/generation_service.py::GenerationService.generate()` silently invents Floor 2 rooms (`default_f2 = "1 master bedroom with attached bathroom, 1 bedroom, 1 study room"`) when `floor_2_brief` is absent, bypassing the chat gate entirely | No requirement may ever be invented, on any entry point | The new Requirement Agent must be the **single** authoritative gate for every entry point (chat and direct API); no direct-generation code path may synthesize defaults |
| 6 | Validator entangled with allocation-era concerns | `rules/hard_constraints.py::evaluate_floorplan_hard_constraints()` optionally takes the whole `floor_plan` and folds door/adjacency/connectivity checks into the same "hard constraint report" as geometric containment/overlap checks | New Validator should cleanly separate allocation-level checks (if any survive) from architectural-design-level checks | Keep the checks, but organize the new `app/validation/*_validator.py` files so each validator's scope is unambiguous (this scaffold already gives each concern its own file — preserve that separation on migration) |
| 7 | Duplicated scoring formula | `asaa/algorithm.py::_apply_layout_objective()` and `asaa/diverse_generator.py::_calculate_candidate_score()` both wrap `core/models/score.py::layout_objective()` but with **different weight configs**, producing inconsistent scores between the default pipeline and "diverse candidates" mode | Scoring must be single-sourced | New `app/asaa/scoring.py` must be the one place allocation-candidate scoring lives; do not let the (future) multi-design generator fork its own weight set |

---

## 6. Reuse / Migration Table (primary traceability table)

Decisions used: **KEEP / REUSE / MODIFY / REWRITE / REPLACE / DROP.**
All "New Location" paths below were verified to exist in the current scaffold before being recorded.

| Previous Component | Previous Location | Decision | New Location | New Responsibility | Changes Required | Reason | Migration Phase |
|---|---|---|---|---|---|---|---|
| Priority calculation (F1) | `src/asaa/priority.py` (`compute_priorities`, `ordered_requirement_ids`, weighted by user importance / area demand / dependency / placement complexity) | REUSE | `app/asaa/models.py` (inputs) + `app/asaa/allocator.py` (consumer) | ASAA priority ordering, unchanged in spirit | Re-key off new `app/models/planning.py` / `app/models/requirements.py` schemas instead of old `RoomRequirement`/`AdjacencyGraph` | Pure allocation-time math with no geometry coupling; safe to keep | Phase 4 (ASAA) |
| Area allocation (F2) | `src/asaa/area_allocator.py` (`allocate_usable_areas`, min-first + priority-weighted remainder distribution, raises `InfeasibleAllocationError`) | REUSE | `app/asaa/allocator.py` | Determines target area per allocated region | Replace `RoomRequirement` with new requirement model; keep the two-pass (minimum-then-proportional) algorithm and the explicit infeasibility exception | Well-isolated, no geometry, matches "ASAA determines WHERE/how-much" exactly | Phase 4 |
| Adjacency graph construction | `src/asaa/adjacency.py` (`build_adjacency_graph`, large hardcoded architectural relationship table keyed by `RoomType`: living↔dining STRONG, ensuite↔living AVOID, kitchen↔laundry STRONG, etc.) | MODIFY | `app/asaa/models.py` (graph data structure) + Planning Agent input | Supplies the relationship graph ASAA allocates against | Extract the *default relationship knowledge* into Planning Agent (it is domain knowledge, not an allocation algorithm) so Planning Agent can emit it; ASAA only consumes the graph | This table is genuinely reusable domain knowledge, but it currently lives inside ASAA, which is the exact allocation/design conflation the new architecture forbids | Phase 3 (Planning) + Phase 4 (ASAA) |
| Candidate scoring (F9) | `src/asaa/candidate_scorer.py` (`score_candidate`, `rank_candidates`, `best_candidate`, weights from `config/scoring_weights.yaml`: area_suitability 0.35, adjacency 0.30, geometric_shape 0.15, connectivity 0.10, orientation 0.10, penalty 1.0) | MODIFY | `app/asaa/scoring.py` | Ranks **allocated-region candidates**, not final room shapes | Drop `geometric_shape` (rectangularity of a *final* polygon) from allocation-time scoring — that's a Geometry Engine / Validator concern; keep area_suitability, adjacency, connectivity, orientation | Old scorer scores placed Shapely geometry directly; new ASAA must score abstract regions before any final shape exists | Phase 4 |
| Candidate/shape generation | `src/asaa/candidate_generator.py`, `src/asaa/shape_generator.py` (rectangle + L-shape polygon construction with wall offsetting) | DROP (from ASAA) / REWRITE (into Geometry Engine) | `app/geometry/room_builder.py`, `app/geometry/polygon_builder.py` | Final room polygon construction from an *architectural design* (not from allocation directly) | Re-enter with the LLM design's stated shape/dims as input instead of ASAA's candidate search loop | This is precisely "final architectural room geometry" that the brief says ASAA must not own | Phase 6 (Geometry Engine) |
| Room placement search | `src/asaa/allocator.py` (`place_room`, `generate_candidate_positions` — grid + neighbor-snap position search, up to 240 candidates/room) | MODIFY | `app/asaa/allocator.py` | Region placement search (position + extent), not final polygon | Same position-search idea, but the returned artifact is a region descriptor, not a `Candidate` with committed `built_geometry` | Positioning heuristic (grid + flush-wall snapping) is genuinely allocation-level and reusable; only the "produces final geometry" part must be cut | Phase 4 |
| Space-filling partitioner | `src/asaa/space_filling_partitioner.py` (`partition_plot_layout`, hand-tuned zoning by facing: wide/narrow plot branches, hardcoded ratios per room type) | MODIFY (split) | Allocation ratios → `app/asaa/spatial_regions.py`; final polygon math → `app/geometry/*` | Zoning strategy (which functional zone goes where relative to facing) is ASAA; exact polygon carving is Geometry Engine | **Known limitation to fix, not inherit**: this file computes `_calculate_space_filling_areas()` allocations but `_layout_wide_plot`/`_layout_narrow_plot` never consume them — actual sizes come from separate hardcoded ratios (confirmed by the file's own `# KNOWN LIMITATION` comment). This disconnect is exactly the allocation/geometry conflation to avoid; do not port it as-is | This module is the clearest embodiment of "ASAA became the architect" — its zoning *strategy* (facade-relative placement of social vs. private zones) is valuable input for ASAA's spatial partitioning; its polygon carving is not | Phase 4 (strategy) / Phase 6 (polygons) |
| Multi-floor partitioner | `src/asaa/multi_floor_partitioner.py` (`generate_multi_floor_plan`, staircase footprint locking between floors, hallway insertion, ensuite carving) | MODIFY (split) | Staircase footprint/anchor + per-floor zoning → `app/asaa/spatial_regions.py`; carving/room construction → `app/geometry/staircase_builder.py`, `app/geometry/room_builder.py`, `app/geometry/corridor_builder.py` | Vertical staircase alignment is an ASAA-level constraint (same X/Y region on both floors); the literal wall carving is Geometry Engine | Preserve the *concept* of "lock staircase region across floors" as an ASAA constraint object; do not preserve the direct polygon-difference carving code as ASAA's job | Confirmed via code: this file directly builds `RoomGeometry` with Shapely `difference()` calls for ensuite carving — that is final geometry construction happening inside ASAA | Phase 9 (Multi-Floor) |
| Diverse/Top-3 generator | `src/asaa/diverse_generator.py` (`generate_top_3_diverse_floor_plans`, 5 named strategies, `compute_layout_similarity` via door-adjacency Jaccard + centroid distance, diversity-filtered top-3 selection) | MODIFY | Strategy generation → `app/asaa/spatial_regions.py`; similarity/dedup → new module under `app/asaa/` (not yet scaffolded — needs a `diversity.py` or similar) | Generate **N diverse allocation candidates**, not N diverse final floor plans | Retarget: instead of 5 strategies each producing a fully validated final floor plan, produce 5 diverse *region layouts*; each one is independently sent through the LLM Architectural Designer | The similarity metric (Jaccard on adjacency pairs + normalized centroid distance) is a genuinely reusable, geometry-agnostic idea; the "generate full final floor plan per strategy" wrapper is not | Phase 10 (Multiple Design Generation) |
| Optimizer (F12) | `src/asaa/optimizer.py` (`optimize_floor_plan`, hill-climbing room nudges against `layout_objective`, plateau/threshold/max-iteration stop conditions) | MODIFY | Could inform `app/agents/refinement_agent/agent.py` as a deterministic fallback, or `app/asaa/allocator.py` for allocation-time jitter | Optional secondary refinement mechanism, subordinate to the LLM refinement loop | Only reuse the *stopping-condition logic* (quality threshold / plateau / max iterations) — reusable regardless of what's being optimized | Old optimizer moves already-final room polygons; in the new pipeline the LLM Refinement Agent is primary, this is at most a fallback | Phase 8 (Refinement) — optional |
| Adaptation operators | `src/asaa/adaptation.py` (`AdaptationOperator`: MOVE/RESIZE/RESHAPE/REORDER/REALLOCATE/RECONNECT, each validated for feasibility before commit) | MODIFY | `app/agents/refinement_agent/agent.py` (as a vocabulary of possible corrective actions) | Refinement Agent's action space when repairing a design | The *taxonomy* of correction types is reusable as a design vocabulary the LLM Refinement Agent can select from; the direct Shapely-mutation implementation should be rebuilt on top of the new geometry model | Clean, well-tested feasibility-checked operators; good conceptual scaffolding for what "correct" can mean | Phase 8 |
| Requirement Agent (regex/state-machine) | `src/agents/requirement_agent.py` — **note: two different classes exist here**: `RequirementAnalysisAgent` (1000+ line regex/state-machine gate used by chat) and a separate, older `RequirementAgent` (thin wrapper whose `.analyze(use_llm=True)` still just calls the deterministic parser — see §17 bug #1) | MODIFY (`RequirementAnalysisAgent`) / DROP (`RequirementAgent` legacy class) | `app/agents/requirement_agent/agent.py` | Structures user intent; gates all downstream generation | Keep the **sequential state machine** (`INITIAL → FLOOR_1_REQUIREMENTS → FLOOR_2_REQUIREMENTS → STAIRCASE_REQUIREMENT → REQUIREMENT_CONFIRMATION`) and its explicit "ask one floor at a time, never invent" discipline. Remove the second, dead `RequirementAgent` class entirely — do not port it, its existence caused the two-different-meanings-of-"requirement agent" confusion in the old codebase | The state machine is exactly right for "must not invent Floor 2"; keeping two competing classes with the same conceptual name is a real source of bugs and must not be repeated | Phase 2 (Requirement Agent) |
| Requirement text parsing | `src/requirements/parser.py` (`parse_text`, `ROOM_PATTERNS` regex table, BHK shorthand expansion, `_preprocess_brief` for "attached bathroom with each bedroom" normalization) | REUSE | `app/agents/requirement_agent/agent.py` (as an internal parsing utility) | Free-text → structured room mentions | Update output type to new `app/models/requirements.py` schema | Regex room-type table and phrase normalization are generic NLP-lite utilities, independent of the rest of the architecture | Phase 2 |
| Requirement normalization | `src/requirements/normalizer.py` (`normalize_requirements`, `adapt_requirements_to_plot` — proportionally scales min/preferred areas and dimensions to fit a constrained plot) | REUSE | `app/agents/planning_agent/agent.py` or `app/asaa/allocator.py` | Plot-aware requirement scaling before allocation | Re-key to new requirement model; keep the scaling math | Useful, generic, no architecture coupling | Phase 3/4 |
| Requirement validation | `src/requirements/validator.py` (`validate_requirement`, `validate_requirements` — structural sanity, not completeness) | REUSE | `app/agents/requirement_agent/agent.py` | Structural sanity checks (positive areas, width×length ≤ area, priority in [0,1]) | Re-key to new model | Simple, correct, decoupled | Phase 2 |
| Project requirements data model (incl. per-floor) | `src/core/models/project_requirements.py` (`ProjectRequirements`, `FloorRequirementData`, `RoomRequirementSpec`, `BathroomSpec`, `AdjacencySpec`, `RequirementSource` enum for provenance, `is_complete()`) | REUSE (as design reference) | `app/models/requirements.py`, `app/models/planning.py` | Structured requirement + provenance schema | Rebuild in the new schema style, but **keep `RequirementSource` (user/missing/default/previous_confirmed/system_constraint) as a concept** — it is exactly the "requirement provenance tracking" the new architecture calls for | This is one of the strongest reusable ideas in the old codebase for the no-invention guarantee: every field already tracks *why* it has its value | Phase 1 (Data Contracts) |
| Room / geometry core models | `src/core/models/room.py`, `plot.py`, `wall.py`, `candidate.py`, `floorplan.py`, `score.py`, `door.py` | MODIFY | `app/models/geometry.py`, `app/models/floor_plan.py`, `app/models/doors.py`, `app/models/allocation.py` | Core data contracts | Split cleanly: `Plot`/geometry primitives → geometry models; `Candidate`/`RoomRequirement` → allocation models; keep them from being the same class as in the old code (old `Candidate` conflated allocation position with final `built_geometry`) | Old `core/models/candidate.py::Candidate` has both `position`/`score` (allocation-era) and `built_geometry`/`usable_geometry` (final geometry) on one object — this is the conflation bug at the data-model level; split it | Phase 1 |
| Geometry primitives | `src/geometry/polygon.py` (`RoomPolygon`, Shapely wrapper), `collision.py`, `containment.py`, `operations.py` (union/difference/intersection/shared-boundary-length), `measurements.py` (rectangularity, aspect ratio, area suitability) | REUSE | `app/geometry/geometry_utils.py`, `app/geometry/polygon_builder.py` | Low-level, architecture-agnostic geometry math | Direct port, adjust import paths | Fully generic, no coupling to old pipeline stages; exactly the kind of utility the new Geometry Engine needs | Phase 6 |
| Wall derivation | `src/geometry/walls.py` (`derive_built_geometry` — Shapely `buffer()` offset from usable → built polygon + wall ring) | REUSE | `app/geometry/room_builder.py` | Wall-aware usable↔built polygon derivation | Direct port | Small, correct, generic geometric offsetting; no architecture coupling | Phase 6 |
| Door construction | `src/geometry/doors.py` (`generate_doors`, `_create_main_entrance_door`, `_create_shared_wall_door`, `find_shared_wall_segment`, `FORBIDDEN_DOOR_PAIRS` table, swing-arc math) | MODIFY | `app/geometry/door_builder.py` (construction) + `app/validation/door_validator.py` (the forbidden-pairs check) | Constructs geometry for a door the LLM has proposed; separately, Validator checks it against the forbidden-pairs rule | Split: currently this module *both* decides which doors should exist (an architectural decision — e.g., "put a door between kitchen and dining") *and* constructs the swing geometry. In the new architecture the LLM Architectural Designer decides door intent; Geometry Engine only constructs the swing arc for a door the LLM specified; Validator checks the result against `FORBIDDEN_DOOR_PAIRS` | The swing-arc / shared-wall-segment math is solid and reusable; the auto-decide-which-doors-to-add logic must move out of "construction" and become either LLM intent or a Refinement Agent repair heuristic | Phase 6 (construction) + Phase 7 (validation) |
| Subdivision helpers | `src/geometry/subdivision.py` (`subdivide_by_vertical`, `subdivide_by_horizontal`) | REUSE | `app/geometry/polygon_builder.py` | Generic polygon-splitting utility | Direct port | Generic, small, no coupling | Phase 6 |
| Hard constraints | `src/rules/hard_constraints.py` (boundary containment, min area, min dimension, overlap — each returns a `ConstraintCheckResult` with magnitude) | REUSE | `app/validation/boundary_validator.py`, `app/validation/dimension_validator.py`, `app/validation/overlap_validator.py` | Deterministic hard-constraint checks on final geometry | Split the currently-monolithic `evaluate_floorplan_hard_constraints()` across the new scaffold's per-concern validator files (boundary/dimension/overlap already have dedicated files — use them) | This is exactly the deterministic-verification role of the new Validator; splitting across the existing per-file scaffold improves on the old monolith | Phase 7 |
| Soft constraints | `src/rules/soft_constraints.py` (preferred area, preferred adjacency, orientation [stub, never implemented], shape preference) | MODIFY | `app/validation/relationship_validator.py` (adjacency) + design-quality scoring (TBD location) | Non-blocking design-quality signals, separate from hard pass/fail | Note: `evaluate_orientation_preference()` in the old code is an explicit no-op stub — do not assume orientation soft-scoring was ever implemented, it was declared but never built | Distinct from hard constraints; useful as feedback to the Refinement Agent about *why* a design could be better, not just whether it's valid | Phase 7 (as feedback signal, not gate) |
| Room-type adjacency rules (avoid/preferred pairs from YAML) | `src/rules/room_rules.py` (`evaluate_avoid_pairs`, `evaluate_preferred_pairs`, driven by `config/architectural_rules.yaml`) | REUSE | `app/validation/relationship_validator.py` | Config-driven adjacency rule checking | Re-key to new room-type enum | Clean, data-driven, decoupled from geometry construction | Phase 7 |
| Rule engine façade | `src/rules/engine.py` (`RuleEngine.evaluate()` — single entry combining hard + soft + room-type rules) | REUSE (pattern) | `app/validation/validator.py` | Single Validator entry point | Rebuild as the top of `app/validation/validator.py`, calling the individual `*_validator.py` files already scaffolded | Good façade pattern; the scaffold already anticipates this shape (`validator.py` coordinating the specific validators) | Phase 7 |
| Full validation orchestrator | `src/validation/validator.py` (`run_full_validation`, `ValidationResult` with per-concern booleans, `format_diagnostic_report()`, composite multi-floor validation) | MODIFY | `app/validation/validator.py` | Top-level Validator entry, produces machine-readable + human-readable result | Keep the per-concern boolean breakdown (`geometry_valid`, `doors_valid`, `adjacency_valid`, `connectivity_valid`, `staircase_valid`, `attached_bathrooms_valid`, `relationship_graph_valid`, ...) and the diagnostic report generator — both map directly to "explainable validation" | This is the single most reusable file in the old validation stack; its structure already matches what the new Validator needs, provided its multi-floor "mirrors Floor 1 only" quirk (see §17 bug #4) is fixed at the model level first | Phase 7 |
| Geometry validator | `src/validation/geometry_validator.py` (`validate_geometry` — containment, positive area, self-validity, overlap) | REUSE | `app/validation/boundary_validator.py` + `app/validation/overlap_validator.py` | Pure geometric correctness | Direct port, split across the two dedicated files that already exist | Generic, correct, no architecture coupling | Phase 7 |
| Connectivity validator | `src/validation/connectivity_validator.py` + `src/rules/circulation_rules.py` (`evaluate_door_connectivity` — authoritative BFS over the *door graph*; `evaluate_connectivity` — legacy shared-wall-touch proxy, used only as fallback when no doors exist) | MODIFY | `app/validation/connectivity_validator.py` | Reachability from entrance via actual doors | Keep the door-graph BFS as the sole method — in the new architecture, geometry (and therefore doors) always exists by the time Validator runs, so the "shared-wall proxy" fallback should not be needed and should not be ported forward as a silent substitute for real door-based checking | The proxy fallback in the old code exists because ASAA sometimes produced geometry without doors yet; that scenario should not occur in the new pipeline, so don't reintroduce the fallback as a crutch | Phase 7 |
| Adjacency validator | `src/validation/adjacency_validator.py` (`validate_adjacencies` — walkable-path BFS per required relationship, attached-bathroom privacy check, forbidden-door check) | REUSE | `app/validation/relationship_validator.py` | Verifies required/avoided relationships against the actual door graph | Re-key to new relationship model | Thorough, already graph/door-based (not proxy-based); strong candidate for direct reuse | Phase 7 |
| Relationship graph evaluator | `src/validation/relationship_evaluator.py` (`evaluate_relationship_graph` — classifies every graph edge as SATISFIED / PARTIALLY_SATISFIED / VIOLATED / IMPOSSIBLE; only REQUIRED/AVOID edges gate `is_valid`) | REUSE | `app/validation/relationship_validator.py` | Fine-grained, per-relationship validation status (not just pass/fail) | Direct port of the four-state classification; this is a **better model of "partially satisfied"** than a flat boolean and should be preserved | Its own docstring explains it was placed under `validation/` rather than `asaa/` specifically to avoid a circular import (`asaa/__init__.py` → `asaa.algorithm` → `validation.validator`) — this dependency-direction lesson (ASAA does not need to import validation) should be preserved as a design rule in the new package layout too | Phase 7 |
| Door validator | `src/validation/door_validator.py` (`validate_doors` — access completeness per room, width bounds, shared-wall-segment sanity, overlap-on-same-wall check) | REUSE | `app/validation/door_validator.py` | Geometric/architectural door correctness | Direct port | Thorough and already geometry-based, not intent-based — fits the Validator role cleanly | Phase 7 |
| Area / quality metrics | `src/validation/area_metrics.py` (`calculate_area_metrics` — explicit named breakdown: plot/buildable/built/usable/wall/circulation/habitable/dead-space/overlap/containment-violation areas) + `src/validation/quality_metrics.py` (`QualityMetrics` — space utilization, dead space ratio, area suitability, shape quality, connectivity, adjacency satisfaction) | REUSE | Design-quality reporting layer (not yet a dedicated new-project file — closest fit is `app/explainability/` or a new `app/validation/quality_metrics.py`) | Non-blocking, explainable quality reporting | Direct port of the metric formulas | `area_metrics.py`'s own docstring already documents the buildable-boundary limitation (see §17 bug #3) — carry the *disclosure*, not just the code | Phase 7 (metrics) |
| Circulation rules | `src/rules/circulation_rules.py` | REUSE (already listed under Connectivity validator above) | `app/validation/circulation_validator.py` | Entrance-to-room and corridor circulation checks | Split from `connectivity_validator.py` per the new scaffold's file layout | The new scaffold already separates `circulation_validator.py` from `connectivity_validator.py` — honor that split when porting | Phase 7 |
| Staircase logic | *No dedicated model* — staircase is just a `Room` with `RoomType.STAIRCASE`, footprint math hardcoded inline in `multi_floor_partitioner.py`; validation is ad hoc (vertical-alignment check inline in `validator.py::run_full_validation`) | REWRITE | `app/models/staircase.py`, `app/geometry/staircase_builder.py`, `app/validation/staircase_validator.py` | Explicit staircase model + dedicated builder + dedicated validator | Old project has **no** `Staircase` model at all — the new scaffold already has one; this must be built fresh using the old code's *behavioral requirements* (vertical alignment across floors, forbidden-adjacency rules) as a spec, not as source to copy | The new scaffold's explicit staircase files are a genuine improvement over the old ad hoc inline handling; treat the old code as a requirements reference only | Phase 9 |
| Windows | *Does not exist* — `FloorPlan.windows: list[Any]` is declared but nothing in the old codebase ever populates it; no `window_builder`, no `window_validator`, no window model | REWRITE | `app/models/windows.py`, `app/geometry/window_builder.py`, `app/validation/window_validator.py` | Window placement, from scratch | No prior art to port | Confirmed absent by full-text inspection of `workspace_all_files.md` — must be flagged so nobody assumes a hidden implementation exists | Phase 6/7 |
| DXF export | `src/export/dxf_exporter.py` (`export_dxf`, `ezdxf`-based, layered: PLOT_BOUNDARY/ROOM_BUILT/ROOM_USABLE/WALLS_*/DOORS/DOORS_SWING/WINDOWS/STAIRS/TEXT_*, multi-floor side-by-side layout) | REUSE | `app/export/dxf/` | CAD export from final geometry | Update input shape to the new `FloorPlan` model; keep the layer scheme and the door-swing-arc + stair-tread rendering logic | Solid, complete, self-contained; not coupled to the pipeline architecture, only to the final geometry shape | Phase 12 |
| JSON export | `src/export/json_exporter.py` (`floorplan_to_dict`, dataclass/Shapely-aware serializer) | REUSE | `app/export/json/` | Serialization of final `FloorPlan` | Update to new dataclasses | Generic recursive serializer, no coupling | Phase 12 |
| Image/PNG export + rendering | `src/export/image_exporter.py`, `src/rendering/renderer.py`, `src/rendering/floorplan_renderer.py`, `annotations.py`, `styles.py` (Matplotlib-based, handles both dict and dataclass floor plans, multi-floor side-by-side) | REUSE | `app/export/png/`, `app/rendering/renderer.py`, `app/rendering/floor_renderer.py`, `app/rendering/dimensions.py`, `app/rendering/annotations.py` | Visual rendering of final geometry | Direct port, update input schema | Well-isolated rendering layer already defensively handles multiple input shapes; low risk | Phase 12 |
| Config data (room types, architectural rules, scoring weights, settings) | `config/room_types.yaml`, `config/architectural_rules.yaml`, `config/scoring_weights.yaml`, `config/settings.yaml` | REUSE | `app/config/defaults.py`, `app/config/settings.py` | Static domain data (min/preferred areas & dims per room type; adjacency preferred/avoid pairs; scoring weights; wall thickness & tolerance defaults) | Load into the new config module's structure; note `settings.yaml`'s own `llm.enabled: false` default is consistent with §17 bug #1 — the old project shipped with LLM integration explicitly turned off | Pure data, zero architecture coupling, high value | Phase 1 |
| Backend input-sanitization utils | `backend/utils/security.py` (`validate_identifier` — path-traversal guard, `sanitize_text` — HTML-escape, `validate_plot_bounds`, `validate_wall_thickness`, `sanitize_filename`) | REUSE | `app/utils/ids.py` / a new `app/utils/security.py` (not yet scaffolded) | Input validation / injection prevention | Direct port | Small, correct, generic, already unit-tested in the old project (`tests/unit/test_input_validation_and_injection.py`) | Phase 1 |
| Event/generation-log strings | Scattered `events.append("...")` calls throughout `asaa/algorithm.py` (e.g. `PLOT_ANALYZED`, `ROOM_PRIORITY_CALCULATED`, `AREA_ALLOCATED`, `ROOM_PLACED:<name>`, `VALIDATION_PASSED`/`FAILED`, `REFINEMENT_STARTED`, `FALLBACK_FROM_ASAA:<reason>`) | MODIFY | `app/explainability/event_tracker.py` | Pipeline event stream for explainability | Upgrade from flat strings to structured records (stage, input snapshot, output snapshot, reasoning) — the old format is a list of tags with no attached reasoning, which is not enough for genuine explainability | The *idea* (a running event log the UI/API can stream) is good and already had a WebSocket consumer (`backend/services/websocket_service.py`); the *format* is too thin for the new architecture's explainability requirement | Phase 11 |
| Diagnostic report generation | `src/validation/validator.py::ValidationResult.format_diagnostic_report()` | REUSE (pattern) | `app/explainability/decision_log.py` | Human-readable failure summaries | Extend pattern to cover every pipeline stage, not just final validation | Good template for "explain what failed and why" | Phase 11 |
| LLM client scaffolding | *Does not functionally exist* — `ChatService.__init__` stores `ollama_url`/`default_model` and `check_ollama_status()` pings `/api/tags`, but no generation call is ever made anywhere in the old codebase | REWRITE | `app/llm/client.py`, `app/llm/configuration.py`, `app/llm/factory.py`, `app/llm/response_parser.py` | Real LLM invocation with structured output, for the Architectural Designer and Refinement Agent stages | Build fresh; the old project provides a health-check pattern (`check_ollama_status`) worth keeping, nothing else | This is the single biggest capability gap between the old and new projects — flagged prominently so effort is allocated correctly | Phase 5 |
| Architectural structured-output schema | *Does not exist in old project* (no LLM-produced design object anywhere) | REWRITE | `app/agents/architectural_agent/structured_output.py`, `app/models/architectural_design.py` | Defines what the LLM Architectural Designer must return | Build fresh, informed by the shape of `core/models/candidate.py`/`core/models/room.py` (as a *target vocabulary* — room shape, dims, doors, windows — not as reusable code) | No prior art; the old `Candidate`/`Room` models are a reasonable naming/field reference only | Phase 5 |
| Validation Agent (LLM self-validation) | `src/agents/validation_agent.py` (`ValidationAgent.validate()` — thin wrapper that just calls `run_full_validation()` and reports `approved`) | DROP (as a concept), REUSE (its actual code is already 100% deterministic) | N/A — its real logic already lives in `app/validation/validator.py` | — | The class name suggests "LLM validates," but the implementation is 100% deterministic already (it just calls the real validator) — so there is nothing to drop technically, but the **name/role must not be resurrected as an LLM-based validator** in the new project, per the explicit requirement that "the LLM must never be allowed to declare its own design valid" | Naming/role hygiene: don't let a future "validation_agent" quietly become LLM-authoritative | Phase 7 |
| Constraint/Plot/Layout/Planning/Refinement/DXF agent façades | `src/agents/constraint_agent.py`, `plot_agent.py`, `layout_agent.py`, `planning_agent.py`, `refinement_agent.py`, `dxf_agent.py` | MODIFY (mostly thin façades) | `app/agents/planning_agent/agent.py`, `app/agents/refinement_agent/agent.py` (others have no new-project equivalent and are superseded) | Various | Most of these are thin pass-through wrappers around the deterministic modules already covered above (e.g. `PlanningAgent.plan()` just calls `build_adjacency_graph` + `compute_priorities`). Their *pattern* (agent = thin façade over deterministic core) is worth keeping for Planning Agent and Refinement Agent specifically; `constraint_agent.py`, `plot_agent.py`, `layout_agent.py`, `dxf_agent.py` have no counterpart in the new seven-stage pipeline and should not be resurrected as separate agents | Confirmed by reading each file: none contain novel logic beyond what's already captured in the ASAA/geometry/export rows above | Phase 3/8 |
| Old LangGraph workflow scaffold | `src/workflow/graph.py`, `nodes.py`, `edges.py`, `state.py` (conditional `should_refine`/`after_refinement` edges, node functions wrapping the old agents) | MODIFY | `app/orchestration/graph.py`, `app/orchestration/routing.py`, `app/orchestration/state.py`, `app/orchestration/workflow.py` | Pipeline orchestration | Re-target nodes to the new seven stages; keep the conditional-edge pattern (`should_refine` based on validation quality) | The LangGraph wiring pattern is sound; the specific nodes it wires are the old (conflated) agents and must be swapped for the new ones | Phase 13 (Orchestration/API wiring) |
| Backend chat/generation services, API routes, auth, rate limiting, middleware | `backend/services/{chat_service,generation_service,project_service,auth_service,websocket_service}.py`, `backend/api/**` | MODIFY | `app/api/{app,routes,schemas,websocket}.py` | HTTP/WS surface, RBAC, rate limiting | Keep RBAC (`AuthService`, role hierarchy), rate limiting (`RateLimiter` sliding window), security headers, and error-envelope format (`format_error_response`) — these are orthogonal to the architecture change and already well-tested (`tests/unit/test_security_and_access_control.py`, `test_error_handling_and_logging.py`, `test_concurrency_and_race_conditions.py`). Rebuild the actual generation-triggering logic on the new pipeline | Infra-level concerns (auth/rate-limit/CORS/error format) are architecture-independent and safe to carry forward | Phase 13 |
| Frontend (React) | `frontend/src/**`, `frontend/dist/**` | OUT OF SCOPE | — | — | Not part of this backend-architecture migration phase (task explicitly scopes this analysis to backend/pipeline components) | — | N/A |
| Evaluation harness | `src/evaluation/scenarios.py`, `runner.py`, `scripts/run_evaluation.py` (varied plot sizes/orientations/room counts, deliberately-infeasible scenarios, aggregate stats — explicitly *not* single-example reporting) | REUSE | `app/config` (scenario data) + a future `scripts/run_experiment.py` equivalent (already present in new scaffold as `scripts/run_experiment.py`) | Aggregate-statistics evaluation, not anecdotal single-run success | Re-target metrics to the new pipeline's stages | This is good methodology — the old scenario file itself states "Do not report a single successful example as algorithm performance," which the new project's `docs/EXPERIMENTS.md` should also enforce | Phase 13 / ongoing |

---

## 7. Requirement System Reuse

**Reuse:** the sequential state machine and provenance-tracking concept from
`RequirementAnalysisAgent`/`ProjectRequirements` (§6 rows above) are strong and should anchor the
new `app/agents/requirement_agent/`.

**Do not reuse:** the dual-entry-point design where `GenerationService.generate()` could bypass the
conversational gate and invent Floor 2 requirements. In the new architecture there must be exactly
one Requirement Agent, and every caller (chat or direct API) must pass through it before any
downstream stage runs.

**Explicit non-invention rule to carry forward, worded precisely:** if the user specifies N floors
and does not supply requirements for floor *k*, the Requirement Agent must return an *incomplete*
result (mirroring the old `RequirementValidationResult.is_complete = False` pattern) and must not
proceed to Planning/ASAA until the user supplies floor *k*'s requirements or explicitly asks the
system to suggest some (which the old system never offered as an explicit, user-consented option —
it only ever silently defaulted).

---

## 8. ASAA Reuse

Reusable **as allocation-only** logic: priority computation, area allocation, adjacency-graph
consumption (not construction — that moves to Planning), position-search heuristics, candidate
scoring (minus the `geometric_shape` term), zoning *strategy* (facade-relative placement), and the
staircase-vertical-alignment-as-a-constraint idea.

Not reusable as-is: anything that calls `geometry/doors.py`, anything that builds final `RoomPolygon`
built/usable geometry, anything that calls the Validator, anything that mutates doors for repair.
All of that must move to Geometry Engine / Refinement Agent.

---

## 9. Multi-Floor Reuse

Reusable: the requirement of identical staircase X/Y footprint across floors; the idea of an
independent per-floor requirement set gated by the same Requirement Agent state machine; the
per-floor validation composition pattern in `ValidationResult` (separate `floor_1`/`floor_2`
breakdowns, combined `is_valid`).

Must be fixed, not carried forward silently: `core/models/floorplan.py`'s own docstring states that
for a multi-floor `FloorPlan`, the top-level `rooms`/`doors`/`walls`/`windows` fields mirror **Floor
1 only** — the complete per-floor data lives in `.floors`. `asaa/algorithm.py::run_multi_floor_asaa`
works around this by computing score/quality metrics per floor independently rather than trusting
the top-level fields. The new `app/models/floor_plan.py` should not reproduce this ambiguous
dual-representation; a multi-floor plan should either have no top-level room list at all, or the
top-level list should be an explicit, correctly-labeled aggregate.

---

## 10. Geometry Reuse

High-confidence reuse: `RoomPolygon` (Shapely wrapper), collision/containment/operations utilities,
wall-offset derivation, door swing-arc math, subdivision helpers, measurement utilities
(rectangularity, aspect ratio, area suitability). These are the most portable part of the old
codebase — none of them know anything about ASAA, agents, or the pipeline shape.

---

## 11. Door / Window / Staircase Reuse

- **Doors:** construction math (swing arcs, shared-wall-segment finding) reusable; the *decision of
  which doors should exist* (`FORBIDDEN_DOOR_PAIRS`, auto-generation heuristics) must be split
  between LLM intent (Architectural Designer) and hard-rule checking (Validator) — it currently
  lives entirely inside geometry construction, which conflates "decide" with "construct."
- **Windows:** nothing exists to reuse; build fresh per the new scaffold's `window_builder.py` /
  `window_validator.py` / `models/windows.py`.
- **Staircase:** no dedicated model existed; behavioral requirements (vertical alignment, forbidden
  adjacency to kitchen/bedroom/bathroom/dining/study) are well-documented in the old validator and
  refinement code and should be used as a *specification* for the new `models/staircase.py` +
  `staircase_builder.py` + `staircase_validator.py`, not copied as source.

---

## 12. Relationship & Connectivity Reuse

Reusable: `RelationshipType` taxonomy (required/preferred/strong/medium/weak/optional/indirect/
avoid), the four-state relationship *evaluation* outcome (satisfied / partially satisfied /
violated / impossible) from `relationship_evaluator.py`, and the authoritative door-graph BFS
connectivity check. The legacy shared-wall-touch connectivity proxy should not be carried forward as
a fallback, since the new pipeline guarantees doors exist by validation time.

---

## 13. Validation Reuse

The old validation stack is the most directly reusable subsystem in the codebase, largely because it
was already structured as a set of independent, composable checks. Port the per-concern validators
(boundary, dimension, overlap, connectivity, door, adjacency/relationship, circulation) into the
already-scaffolded `app/validation/*_validator.py` files, and rebuild `app/validation/validator.py`
as the composing entry point (mirroring `RuleEngine.evaluate()` + `run_full_validation()`). Drop the
notion of an LLM-based `ValidationAgent` as an authority — keep only the deterministic checks.

---

## 14. Refinement Reuse

Reusable *as a heuristic library*, not as the primary mechanism: the `AdaptationOperator` taxonomy
(MOVE/RESIZE/RESHAPE/REORDER/REALLOCATE/RECONNECT) and the door/connectivity repair heuristics in
`refinement_engine.py` (e.g., "if a main entrance door is missing, add one on the entrance-eligible
room touching the requested facade"). In the new architecture, the primary refinement mechanism is
the LLM Refinement Agent revising its own architectural design based on structured Validator
feedback; the old deterministic repairs can remain as a fallback for cases where the LLM cannot
produce a valid revision within the iteration budget.

---

## 15. Multiple Design Generation Reuse

The topological-similarity/diversity-filtering algorithm in `diverse_generator.py` is genuinely
reusable and largely **objective** (Jaccard similarity over door-adjacency pairs + normalized
centroid distance), not a subjective "best design" ranking — safe to reuse as a de-duplication step.
It must be retargeted from "diversify 5 final floor plans" to "diversify N ASAA allocation
candidates," each of which then goes through its own LLM Architectural Designer pass. The scoring
formula duplication bug (§5, conflict 7) must be fixed by making scoring single-sourced before this
is ported.

---

## 16. Explainability Reuse

Reusable *pattern*: a running event/decision log, a WebSocket-streamable event channel, and a
human-readable diagnostic report generator. Not reusable *as-is*: the flat string-tag format
(`"ROOM_PLACED:Kitchen"`) carries no reasoning and cannot explain *why* an LLM stage made a choice
(because no LLM stage existed to have a reason). The new `app/explainability/decision_log.py` /
`event_tracker.py` should capture structured records: stage name, inputs consumed, decision made,
reasoning (LLM-provided where applicable), and outputs produced — sufficient to answer all of: what
did the user ask, how were requirements interpreted, why did ASAA allocate as it did, what did the
LLM propose, what was checked, what failed, what changed, why did it pass.

---

## 17. Known Bugs / Risks to Avoid (verified against actual old-project source)

1. **LLM never actually called for requirement structuring.** `agents/requirement_agent.py`'s
   `RequirementAgent.analyze(text, use_llm=True)` calls `deterministic_parse(text)` regardless of
   the `use_llm` flag; `RequirementAgentResult.llm_used` defaults to `False` and is never set `True`
   anywhere in the codebase. Separately, `ChatService.chat()` never calls Ollama at all — only
   `check_ollama_status()` pings it. The frontend's "Qwen3:4B analyzing spatial parameters..."
   loading text and "LLM Semantic Extraction" toggle are therefore cosmetic; no model inference ever
   occurs in the generation path. **Risk if not addressed:** the new project could accidentally
   repeat this pattern by wiring `app/llm/client.py` but never actually calling it from the agent
   stages. Verify with an integration test that asserts an LLM call actually occurred.

2. **Floor 2 requirement invention on the direct-generation path.** `GenerationService.generate()`
   (`backend/services/generation_service.py`) contains: when `floors > 1` and no `floor_2_brief` was
   supplied and per-floor parsing of the free-text brief found nothing for floor 2, it falls back to
   `default_f2 = "1 master bedroom with attached bathroom, 1 bedroom, 1 study room"` and generates
   real geometry from that invented brief. This exactly matches the failure mode the task brief
   warns against. The chat-gated path (`RequirementAnalysisAgent`) does *not* have this bug — it
   correctly blocks generation until the user supplies floor 2. **Risk:** any direct/API generation
   entry point in the new project must route through the same Requirement Agent gate as chat; do not
   let a "quick generate" endpoint reintroduce a parallel, ungated path.

3. **No automatic buildable-boundary derivation.** `core/models/plot.py::Plot.__post_init__`
   defaults `buildable_boundary = boundary` whenever a caller doesn't supply one explicitly, and no
   code anywhere in the old project derives a setback-inset buildable boundary automatically. This
   is confirmed by an explicit `# KNOWN LIMITATION` docstring in `validation/area_metrics.py`. As a
   result, `plot_area` and `buildable_area` are numerically identical unless a caller manually
   builds a smaller polygon. **Risk:** if the new Requirement/Planning Agent captures setback
   requirements from the user, ASAA and Geometry Engine must actually consume them to produce a
   real buildable boundary — do not silently inherit the old no-op behavior.

4. **Multi-floor `FloorPlan` top-level fields are ambiguous.** As documented in `core/models/
   floorplan.py`'s own docstring, for a multi-floor plan the top-level `rooms`/`doors`/`walls`/
   `windows` mirror Floor 1 only; complete data is in `.floors`. Code that forgets this (e.g., naive
   score/metric computation directly on the multi-floor object) will silently report Floor-1-only
   numbers as if they described the whole building. `asaa/algorithm.py::run_multi_floor_asaa` works
   around this correctly by computing metrics per floor, but the underlying model ambiguity itself
   should not be carried into the new `app/models/floor_plan.py`.

5. **Allocation computed but never consumed.** `asaa/space_filling_partitioner.py::
   partition_plot_layout()` computes `_calculate_space_filling_areas()` (a genuine priority/area
   allocation) but the actual room sizing in `_layout_wide_plot`/`_layout_narrow_plot` uses separate
   hardcoded architectural ratios instead — the file's own comment calls this out as a "KNOWN
   LIMITATION." This is dead/decorative allocation logic sitting next to the geometry code that
   actually determines sizes. Do not port this disconnect; if ASAA computes an allocation, the
   Geometry Engine (or LLM design) must actually be constrained by it.

6. **Scoring formula duplicated with different weights.** (Restated from §5, conflict 7.)
   `asaa/algorithm.py::_apply_layout_objective()` and `asaa/diverse_generator.py::
   _calculate_candidate_score()` both call `core/models/score.py::layout_objective()` but construct
   different `LayoutObjectiveWeights` — meaning the same floor plan can score differently depending
   on which code path produced it. Single-source scoring in the new project.

7. **Orientation scoring was silently a no-op for most rooms, then partially patched.** A dedicated
   regression test (`tests/unit/asaa/test_orientation_and_entrance_door.py`) documents that
   `asaa/allocator.py::place_room()` originally never computed a non-zero `orientation_score`,
   meaning the `facing` parameter had no real effect on placement despite being threaded through the
   whole pipeline; a later fix (`_facade_orientation_score`) restricts the correction to
   entrance-eligible room types only (Living Room / Entrance Foyer / Dining), leaving orientation
   preference for all other room types still unscored. **Risk:** if the new ASAA/Planning stage
   claims to honor orientation/facing preferences, verify with a geometry-level regression test
   (not just "no exception raised") that the claim is actually true for every affected room type,
   not just the entrance room.

8. **"Diverse designs" silently fall back to a non-diverse baseline.** `asaa/algorithm.py::
   run_asaa()`'s default `baseline="asaa"` path (`run_asaa_full`) will, on validation failure or
   unplaced requirements, silently substitute the space-filling baseline (`run_space_filling_
   baseline`) and only records the substitution via an event string
   (`FALLBACK_FROM_ASAA:<reason>`) — a caller not reading events would not know the "authoritative"
   pipeline didn't actually run. Decide explicitly in the new architecture what should happen when
   the LLM Architectural Designer + Refinement Agent loop cannot converge (return partial/best-effort
   with a clearly surfaced failure, vs. silently swapping algorithms) — do not default to the old
   silent-substitution pattern without an explicit design decision.

9. **Two classes both named "requirement agent."** (Restated from §6.) `agents/requirement_agent.py`
   defines both `RequirementAnalysisAgent` (the real, gated, chat-facing implementation) and a
   separate `RequirementAgent` (a thin, legacy, non-gating wrapper used only by `workflow/nodes.py`).
   Having two same-domain classes with near-identical names in one module is a maintenance hazard;
   do not reproduce this naming collision in `app/agents/requirement_agent/`.

10. **Historical test-pass claims are unverified for this analysis.** The old project's `README.md`
    and `docs/installation_and_setup.md` both state "*Expected: 83 passed, 1 skipped in ~24s*" for
    `pytest`. No tests were executed as part of this analysis (analysis-only phase, no code run).
    This number must be treated as **historical and unverified**, not as evidence of the current
    state of either the old or new codebase, per the task instructions.

---

## 18. Components That Must NOT Be Reused

- The direct-generation path's default-requirement-invention branch in `GenerationService.generate()`
  (bug #2 above) — must not be ported in any form, gated or not.
- The `RequirementAgent` legacy class in `agents/requirement_agent.py` (bug #9) — superseded by
  `RequirementAnalysisAgent`; do not port both.
- `agents/validation_agent.py`'s framing as an "agent" that "validates" — keep only its underlying
  deterministic call, and do not let a future implementation make it LLM-authoritative.
- The silent-fallback-to-a-different-baseline pattern in `run_asaa()` (bug #8) as a *default*
  behavior — an explicit, surfaced decision is required instead.
- The conflated `Candidate` data model (`core/models/candidate.py`) that mixes allocation-time fields
  (`position`, `score`) with final-geometry fields (`built_geometry`, `usable_geometry`) on one
  object — split these across the allocation model and the geometry model in the new project.
- Any code path (ASAA or otherwise) that calls `geometry/doors.py`-equivalent door construction
  directly from inside allocation logic, bypassing the LLM Architectural Designer stage.
- The "shared-wall-touch" connectivity proxy as a general-purpose fallback (bug/legacy note in §12).

---

## 19. Proposed Migration Sequence

This sequence assumes the seven-stage architecture is fixed and that each phase produces something
independently testable before the next begins.

1. **Phase 1 — Data Contracts & Config.** Finalize `app/models/*` (with the allocation/geometry
   split from §18 applied), port `config/*.yaml` data into `app/config/`, port
   `backend/utils/security.py` utilities.
2. **Phase 2 — Requirement Agent.** Port the sequential state machine and provenance tracking; unit
   tests specifically asserting no-invention for unspecified floors/rooms (this is the single
   highest-priority regression to lock in, given bug #2).
3. **Phase 3 — Planning Agent.** Extract relationship/adjacency domain knowledge out of old ASAA into
   Planning Agent's output.
4. **Phase 4 — ASAA (allocation-only).** Port priority/area-allocation/position-search/scoring
   (minus geometric_shape), with the region-only output contract from §5/§6.
5. **Phase 5 — LLM Architectural Designer.** Build `app/llm/client.py` for real (bug #1 fix) and the
   structured-output schema; no prior source to port here beyond naming inspiration.
6. **Phase 6 — Geometry Engine.** Port geometry primitives, wall derivation, door/window/staircase
   construction (rebuilt to consume LLM design output rather than drive allocation).
7. **Phase 7 — Validator.** Port the per-concern validators and the composing entry point; explicitly
   exclude any LLM self-validation.
8. **Phase 8 — Refinement Agent.** Build the LLM-driven revise-and-reloop mechanism; port the old
   adaptation taxonomy and door/connectivity repair heuristics as an optional deterministic aid.
9. **Phase 9 — Multi-Floor.** Port staircase-alignment-as-constraint and per-floor gating; fix the
   top-level-fields ambiguity (bug #4) at the model level first.
10. **Phase 10 — Multiple Design Generation.** Port the diversity/similarity algorithm retargeted to
    allocation candidates (after Phase 4 and Phase 6 exist).
11. **Phase 11 — Explainability.** Build structured decision logging across all prior phases.
12. **Phase 12 — Export/Rendering.** Port DXF/JSON/PNG export and rendering once the final geometry
    schema from Phase 6 is stable.
13. **Phase 13 — Orchestration & API.** Wire the LangGraph-style graph over the new stages; port
    auth/rate-limiting/security-header infra from the old backend API layer.

---

## 20. Final Reuse Inventory

| Category | Count (approx.) | Disposition |
|---|---|---|
| Files with direct, low-risk reuse (geometry primitives, export, rendering, config, security utils) | ~20 | REUSE, ported largely unchanged |
| Files reusable only after splitting allocation from geometry/doors/refinement | ~6 (ASAA core) | MODIFY, non-trivial |
| Files reusable as a *pattern* or *taxonomy* only, not as source | ~6 (adaptation operators, optimizer, diversity filter, event logging, diagnostic report, rule-engine façade) | MODIFY/REWRITE |
| Files with no counterpart in the old project | Windows (model/builder/validator), LLM client (functional), Architectural Designer structured output, Staircase model | REWRITE, no prior art |
| Files/paths that must be explicitly excluded from migration | Direct-generation invention branch, legacy `RequirementAgent` class, LLM-self-validation framing, silent-baseline-fallback default | DROP |
| Frontend (React app) | All of `frontend/` | OUT OF SCOPE for this phase |

---

*End of analysis. No implementation performed. Per task instructions, work stops here pending
explicit approval to begin Phase 1.*

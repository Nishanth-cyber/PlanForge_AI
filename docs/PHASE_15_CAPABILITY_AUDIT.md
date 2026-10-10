# PHASE 15 — CAPABILITY & LIMITATION AUDIT

**Project:** PlanForge AI — Agentic AI Framework for Intelligent Residential Floor Plan Generation Using Adaptive Space Allocation Algorithm (ASAA)
**Audit date:** 2026-10-03
**System under audit:** package `planforge` 0.1.0 (`pyproject.toml`); ASAA `algorithm_version = "2.0-ASAA"` (`app/asaa/allocator.py`); stored evaluation run `eval_run_66ba99354301` (benchmark 1.0.0, `mock_llm: true`, seed 42, 2026-09-20).
**Machine-readable companion:** `docs/phase15_capability_audit.json`

> **Scope rule applied:** implementation is the source of truth. No application code, test, benchmark result, or frontend file was modified by this phase. Only this file, `docs/phase15_capability_audit.json`, and a Phase 15 section inserted at the top of `progress.md` were written.

---

## 0. Evidence Labels, Coverage and Verification Status (read first)

Every finding carries one evidence tag:

| Tag | Meaning |
|---|---|
| **[SRC]** | Confirmed by reading the cited source file in this audit. |
| **[RES]** | Confirmed by the stored, unmodified evaluation artifacts in `results/evaluation_run/`. |
| **[HYP]** | Inferred from static reading; requires a runtime test to confirm. Not asserted as fact. |

**What this audit did NOT do (stated plainly):**

1. **The test suite was NOT executed.** This audit ran through a file-access interface only; it had no ability to execute `python -m pytest` on the project. No test result is claimed. See §20 for the commands to run. `.pytest_cache/v/cache/lastfailed` contains one stale entry (`tests/unit/test_refinement/test_refinement_loop.py`) for a file that does not exist in the current tree; it is not evidence of the current state.
2. **The repository was not inspected in full.** Files read in depth: `app/asaa/*` (all), `app/models/{requirements,planning,allocation,architectural_design,validation,refinement,alternatives}.py`, `app/agents/{requirement_agent (agent, pipeline, parser, completeness_gate), planning_agent (all except prompts), architectural_agent (all), refinement_agent (agent, loop, context, prompts, output_validator), diversity_agent (generator, signature, metrics)}`, `app/llm/{client,configuration,factory}.py`, `app/geometry/{engine,room_builder,polygon_builder,door_builder,window_builder,wall_builder,corridor_builder,staircase_builder,geometry_utils}.py`, `app/validation/{validator,room,dimension,relationship,circulation,window,connectivity}_validator.py`, `app/orchestration/{orchestrator,pipeline,config}.py`, `app/evaluation/{benchmark,metrics,baselines}.py`, `tests/unit/test_orchestration/test_orchestrator.py`, the full `tests/` file inventory, `results/evaluation_run/*` (metric_summary, failure_analysis, summary, metadata, benchmark_metrics.csv, ablation_metrics.csv, report), `docs/{ASAA,MULTI_DESIGN_DIVERSITY,DEVELOPMENT_ROADMAP}.md`, `README.md`, `requirements.txt`, `pyproject.toml`.
   **Not read:** `normalizer.py`, `conversation.py`, `requirement_agent/validator.py`, `door_validator.py`, `staircase_validator.py`, `boundary_validator.py`, `overlap_validator.py`, `app/explainability/*`, `app/export/*`, `app/rendering/*`, `app/api/*`, `app/evaluation/{ablation,runner,reproducibility,reporting,plotting,aggregation}.py`, `app/models/{geometry,floor_plan,doors,windows,staircase}.py`, the contents of almost all test files, `frontend/src/**`, `scripts/**`, and docs other than the three listed. `.env` was deliberately **not** opened (it may hold credentials).
3. Findings about those unread areas are not made. Where a conclusion could depend on them it is flagged **[HYP]** or listed as an open question (Appendix C).

Because of (1) and (2), the Phase 15 acceptance checklist in §20 is **not** fully satisfied and this phase is **not** declared COMPLETE.

---

## 1. Executive Summary

PlanForge today is a **deterministic, rule-based procedural pipeline with one narrow generative slot**. The generative slot is the Architectural LLM, which is only permitted to emit door/window/shape *intent* inside regions that ASAA has already fixed. In every stored evaluation artifact that slot is filled by a ~300-line hardcoded rule engine (`ArchitecturalAgent._deterministic_mock_generator`), not an LLM **[RES: metadata.json `mock_llm: true`] [SRC]**.

Principal conclusions:

1. **What it can generate:** single- or multi-floor residential plans from regex-parsable briefs, as axis-aligned recursive bisections of the buildable polygon, with rectangular/square/6-vertex-L room footprints, midpoint doors, centered windows, a straight corridor spine, a left-edge stair core and a front-edge foyer zone. **[SRC]**
2. **What it cannot generate:** curved or non-orthogonal rooms; rooms at positions chosen by architectural pattern; style-driven or preference-driven plans; privacy/daylight/ventilation-aware layouts; alternatives with different spatial partitions; anything the schema has no field for (§7).
3. **ASAA is a hybrid, dominated by rule-based procedural generation** (fixed ordering → recursive axis-aligned bisection), followed by a weighted-sum scorer and a first-improvement swap hill-climber. It is not constraint satisfaction, not a learned generator, and not a multi-objective optimizer. Candidate count is ≤4 (3 by default through the orchestrator); the `seed` has **no effect** on output **[SRC]**.
4. **Multi-design "diversity" does not diversify space.** `MultiDesignGenerator.generate` receives the single `AllocationSet` and varies only the Architectural stage; `DesignSignature` is computed from *door intents*. Under the default mock, `privacy_centric` and `service_clustered` execute the identical branch and are therefore duplicates **[SRC]**. No stored benchmark run exercised >1 alternative **[RES]**.
5. **The Validator is strong at hard validity and almost silent on architectural quality.** It has no daylight-presence, ventilation, privacy, proportion, furniture, circulation-efficiency, entrance-sequence or coherence check **[SRC]**.
6. **The benchmark cannot discriminate quality.** nine percentage metrics are exactly 100.0 with zero variance (and five error-count metrics exactly 0) on the feasible cases; two structurally different plans can score identically **[RES]**.
7. **A critical defect hides inside those perfect scores:** rooms with `count > 1` are collapsed to a single realized room. The stored metrics are exactly consistent with this (e.g. `case_08` `room_count_accuracy = 55.6 = 1 − 4/9`), yet `validation_success = True` and `req_room_coverage = 100.0` for every case **[RES][SRC]** (BUG-03).
8. **Integration defects:** the orchestrator's refinement stage calls `RefinementLoop.run` with keyword arguments it does not accept, and reads result attributes that do not exist (BUG-01); an `AlternativeStatus` member that does not exist is referenced (BUG-02); **user-specified side setbacks are silently ignored** because the parser key `"side"` is never mapped to left/right (BUG-16, corroborated by the stored `case_16` buildable area of 12.8 m²); two multi-design metrics read nonexistent attributes and report 0% validity / no diversity (BUG-06). All **[SRC]**; BUG-06 additionally **[RES]**.
9. **Documentation and implementation disagree in at least 18 places** (Appendix B), notably: ASAA orientation awareness, seeded RNG, diversity weights/thresholds, "Pydantic" data contracts (domain models are stdlib `@dataclass`), and the Completeness Gate's claim that "standard municipal setbacks will be used".
10. **Architecture invariant is intact in structure** (Requirement→Planning→ASAA→LLM→Geometry→Validator→Refinement) but is leaky in four places (§2.3).

**Recommended Phase 16 entry:** a short **defect gate** (BUG-03, 16, 01, 02, 06, 07, 08, 09, 10, 17) *before* any new capability, then additive requirement representation. See §18.

---

## 2. Current Architecture (verified from source)

### 2.1 Executed pipeline (`PlanForgeOrchestrator.generate`, `app/orchestration/orchestrator.py`)

| # | Stage | Class / file | Mechanism (actual) | LLM? |
|---|---|---|---|---|
| 1 | REQUIREMENT (WHAT) | `RequirementAgent` → `RequirementPipeline` → `RequirementParser` (`requirement_agent/parser.py`) | Regex extraction + synonym table + `CompletenessGate` + `RequirementValidator` | **No** (no LLM import anywhere in the package) |
| 2 | PLANNING (ORGANIZE) | `PlanningAgent.plan` | Lookup tables: `RoomCategorizer`, `PriorityCalculator`, `RelationshipGraphBuilder`, `CirculationPlanner` | **No** |
| 3 | ASAA (WHERE) | `ASAAAllocator.allocate` (`ASAAAllocator(seed=42)`, `num_candidates=3` default) | Budget → ≤3 strategy candidates → recursive bisection → score → swap refinement → pick max score | **No** |
| 4 | ARCHITECTURAL (HOW) | `ArchitecturalAgent.design` | Prompt → `LLMClient.generate` → JSON parse → `ArchitecturalOutputValidator`. Default provider `mock` → rule engine | Optional (`huggingface`) |
| 5 | GEOMETRY (CONSTRUCT) | `GeometryEngine.construct` | Shapely polygon construction, wall derivation, door/window placement | No |
| 6 | VALIDATION (VERIFY) | `FloorPlanValidator.validate` | 10 sub-validators, severity-scored | No |
| 7 | REFINEMENT (CORRECT) | `RefinementLoop.run` (called from orchestrator — **broken call**, BUG-01) | `RefinementAgent` (default mock keyword rules) | Optional but default mock |
| 8 | MULTI_DESIGN | `MultiDesignGenerator.generate` (only if `num_alternatives > 1`; default 1) | Re-runs stage 4+5+6+7 per strategy on the **same** `AllocationSet` | as stage 4/7 |
| 9 | EXPLAINABILITY | `DecisionTraceBuilder.build` | Not audited | — |
| 10 | EXPORT | `export_project_bundle` | Not audited | — |

### 2.2 Data-contract technology
Domain models in `app/models/*` read for this audit are **stdlib `@dataclass`**, not Pydantic. `pydantic>=2.0.0` is declared in `requirements.txt`/`pyproject.toml` but no audited domain model uses it. Pydantic use in `app/api/schemas.py` is **[HYP]** (not read). Phase brief says "Pydantic/domain models": **discrepancy**.

### 2.3 Where the WHAT/ORGANIZE/WHERE/HOW/CONSTRUCT/VERIFY/CORRECT separation leaks

| # | Leak | Evidence |
|---|---|---|
| L-a | Planning reads **raw user text**: `PlanningAgent._build_global_constraints` substring-matches `"no corridor"`, etc. in `requirements.raw_input` (parsing belongs to WHAT). | `planning_agent/agent.py` **[SRC]** |
| L-b | Validator definitions are **not independent of the Geometry Engine**: "exterior wall" = any room edge not shared with another room (`WallBuilder.build_walls_for_rooms`); `WindowValidator` accepts `wall.type == "exterior"` using that same classification. | `wall_builder.py`, `window_validator.py` **[SRC]** |
| L-c | `RelationshipValidator` (VERIFY) hardcodes parent types `{"master_bedroom","bedroom","suite"}` for attached rooms instead of using `RoomSpec.attached_to_room_id`; and promotes `priority == "high"` adjacencies (a PLANNING heuristic) to **hard errors**. | `relationship_validator.py` **[SRC]** |
| L-d | Orchestrator's multi-design stage does not pass `plot_boundary`/`buildable_boundary`, so alternatives are validated against boundaries re-derived inside the validator rather than the orchestrator's geometry-stage boundaries. | `orchestrator.py` Stage 8 vs `MultiDesignGenerator.generate` signature **[SRC]** |

None of these breaks the *direction* of data flow; all four weaken the independence/purity claims and are recorded in the register.

---

## 3. Actual Capability Map

Legend — Type: **R** rule/lookup, **P** procedural, **H** heuristic search, **S** scoring, **O** optimization, **L** LLM, **M** mock-rule-engine standing in for LLM, **–** absent. Severity: C/H/M/L.

### 3.1 Requirement understanding (`requirement_agent/parser.py`, `completeness_gate.py`)

| Capability | Mechanism | Type | Limitation (evidence) | Tests | Bench | Sev | Upgrade |
|---|---|---|---|---|---|---|---|
| NL parsing | Regex over clauses split on `[\n;]` and `.` | R | Only phrasings the regexes anticipate; no LLM/semantic fallback despite `agent.py` docstring "LLM-ready secondary" **[SRC]** | test_requirement_parser, _regression | all 16 use identical `N <room> of X sq ft` syntax | H | P16 |
| Room extraction | `ROOM_SYNONYMS` longest-first, plural-aware | R | One `RoomRequirement` per canonical type with `min_count`; two differently-sized rooms of one type are merged (second area ignored once first set) **[SRC]** | yes | case_02/08 | H | P16/17 |
| Area extraction | min/max/range/single/dimension regexes per clause | R | Units limited to sq ft/sqm/m²; no "approx", "generous", "large" | yes | all | M | P16 |
| Floor extraction | `G+N`, "N floors", `Floor N:` headers | R | Header-dependent; `bhk` expansion only to bedroom/living/kitchen | yes | 04,05,13 | M | P16 |
| Relationship extraction | `next to / near / beside…`, `away from…` regexes | R | `near` is treated as **required** adjacency (hard error downstream); no strength | yes | 10,11 | H | P16 |
| Orientation / entrance | Cardinal-direction regexes | R | Only 4 cardinals; no road-frontage; orientation never reaches scoring (BUG-04) | yes | 14 | H | P16/18 |
| Plot polygon | Only explicit `(x, y)` coordinate triples | R | Phrase "L-shaped plot of 50 feet by 50 feet" has no coordinates → parsed as a 50×50 rectangle **[SRC][HYP runtime]** (case_06 label vs behavior) | yes | 06 | H | P16 |
| Architectural style | – | – | No field, no extraction **[SRC]** | – | – | H | P16 |
| Qualitative intent | – | – | "bright", "private", "open-plan" are discarded | – | – | H | P16 |
| Ambiguity handling | `CompletenessGate` status INCOMPLETE/AMBIGUOUS/INVALID | R | AMBIGUOUS defined but conflicts are not detected beyond non-positive values **[SRC]** | yes | – | M | P16 |
| Missing info | Gate refuses planning; asks clarification questions | R | Good & protected (no invention). Warning text promises "standard municipal setbacks will be used by the Planning Agent" — **no such default exists** (ASAA uses `setbacks=None` → buildable = plot) **[SRC]** | yes | 16 | M | doc fix |

### 3.2 Planning (`planning_agent/*`)

| Capability | Mechanism | Type | Limitation | Sev |
|---|---|---|---|---|
| Room categorization | `ROOM_FUNCTIONAL_ZONES` dict + substring fallback | R | Fixed 6 zones; unknown → "other" | M |
| Priority | `PRIORITY_RULES` dict (+ substring fallback); user override param exists but is **never passed** by `PlanningAgent._plan_floor` | R | No per-user priority; `user_override` unused **[SRC]** | M |
| Adjacency / separation | `DEFAULT_PREFERRED_ADJACENCIES` (10 pairs), `DEFAULT_AVOID_PAIRS` (6 pairs) + user pairs | R | Same defaults for every house; no strength/weight | H |
| Circulation | `CirculationPlanner.plan_circulation_zones` → string tags + note text | R | Tags are **not consumed by ASAA** (ASAA uses `no_corridor` and fixed ratio only) **[SRC]** | H |
| Entrance | `plan_entrance_intent`: facing = entrance_facing → orientation → **"north"**; room = "living" | R | Default `"north"` places foyer at `max_y` in ASAA while scoring prefers social rooms at `min_y` (inconsistent frame, BUG-04b) **[SRC]** | M |
| Staircase | `plan_staircase_intent`: required if multi-floor | R | Stair type/width not planned | L |
| Zoning (public/private/service) | category tags only | R | Zoning is an *ordering key* in ASAA, not a spatial rule | H |

### 3.3 Spatial allocation (`app/asaa/*`)

| Capability | Mechanism | Type | Limitation | Sev |
|---|---|---|---|---|
| Plot handling | `BuildableBoundaryCalculator`; rect: axis inset; irregular: `buffer(-s, mitre)` or **bbox clipping** for directional setbacks | P | Directional setbacks on non-rect polygons are applied against the *bounding box*, not edge-wise **[SRC]** | M |
| Irregular plots | Shapely polygon preserved; largest component kept | P | `extract_largest_polygon` silently discards other components | M |
| Multi-floor | Each floor partitioned independently on **same** buildable polygon; stair anchored from floor 1 | P | No upper-floor footprint change, no structural/wet-stack alignment, no terraces | M |
| Area allocation | `AreaBudgeter` two-pass; partitioner then uses budgets only as **ratios** and fills 100% of space | P | Budget ≠ final area; rooms absorb all leftover | H |
| Candidate generation | 4 fixed strategy names = 4 different *room orderings* (+ axis tie-break) | H | ≤4 candidates; orchestrator default 3 ⇒ `orientation_aligned` never runs | H |
| Spatial partitioning | Recursive axis-aligned bisection, binary search on cut coordinate | P | Only orthogonal cuts; adjacency is a *by-product of list order* | C |
| Orientation | `orientation` arg accepted by `CandidateScorer.evaluate` and **never used**; score = share of social items with `centroid.y ≤ mid_y` | S | Orientation is not implemented (BUG-04) | H |
| Adjacency | Scored post hoc by shared boundary ≥0.2 m; swap hill-climb | S | Not a construction driver; "required" adjacency is soft in ASAA | H |
| Circulation | Spine strip at 45% of the long axis, width 1.2–2.0 m, only if `circ≥4 m²`, area>30 m², ≥3 specs | P | Single straight strip; not derived from plan topology | H |
| Privacy | – | – | No concept (only category ordering) | H |
| Daylight / ventilation | – | – | No concept in ASAA | H |
| Architectural patterns | – (4 orderings only) | – | No pattern library | H |

### 3.4 Architectural reasoning (`architectural_agent/*`)

| Capability | Mechanism | Type | Limitation | Sev |
|---|---|---|---|---|
| Semantic shape | LLM/mock picks from {rectangular, square, l_shaped, custom} | L/M | Mock never emits `l_shaped`; `custom` accepted by validator but Geometry treats as region fill **[SRC]** | M |
| Proportions / dimensions | LLM/mock proposes `[w, l]` ≤ allocated area (+5%) | L/M | Mock copies region bbox dims | M |
| Door placement | Intent = `{connects_to, wall_orientation, width}` | L/M | No position along wall; compass wall chosen without seeing the polygon (prompt lacks polygon/neighbor direction) | H |
| Window placement | Intent = compass wall + size | L/M | Mock: social→north, private→east, service→west **regardless of room position** | H |
| Visual relationships / privacy gradients / style / furniture | – | – | Not in prompt, schema, or validator | H |

### 3.5 Geometry, Validation, Refinement, Diversity
Covered in detail in §§8–11.

---

## 4. Decision Ownership Map

Traced **statically** through the source for a brief of the form of benchmark `case_02` ("45×55 ft plot, setbacks 2 m, 1 living 280 sq ft, 1 dining 160, 1 kitchen 140, 2 bedrooms 160 each, 1 bathroom 60"). Values are what the code *would* do; nothing here is a run output.

Owner vocabulary (exact): USER, REQUIREMENT RULE, PLANNING RULE, ASAA RULE, ASAA OPTIMIZATION, LLM, GEOMETRY RULE, VALIDATOR RULE, REFINEMENT RULE, DIVERSITY RULE, OTHER.

| # | Decision | Who | Why | Can it learn/adapt? |
|---|---|---|---|---|
| 1 | Room list, counts, areas, setbacks, plot size | USER | Stated in brief | n/a |
| 2 | Parse "2 bedrooms of 160 sq ft each" → one `RoomRequirement(min_count=2)` | REQUIREMENT RULE | `_extract_rooms_from_text` merges by canonical type | No |
| 3 | `near`/`next to` ⇒ required adjacency | REQUIREMENT RULE | `_apply_relationships` | No |
| 4 | living=social, bedroom=private, kitchen/bath=service | PLANNING RULE | `ROOM_FUNCTIONAL_ZONES` | No |
| 5 | living/master/kitchen = "high", bedroom/dining/bath = "normal" | PLANNING RULE | `PRIORITY_RULES` | No |
| 6 | Preferred adjacencies (living–dining, dining–kitchen, bedroom–bathroom…) and avoid pairs | PLANNING RULE | Default pair lists | No |
| 7 | Circulation tags; entrance facing default "north" | PLANNING RULE | `CirculationPlanner` | No |
| 8 | Buildable polygon (plot − setbacks) | ASAA RULE | `BuildableBoundaryCalculator` (front = `min_y`) | No |
| 9 | Circulation ratio 12%, stair 8 m² | ASAA RULE | Constants in `ASAAAllocator._allocate_floor` | No |
| 10 | Per-room area budget | ASAA RULE | `AreaBudgeter` two-pass, weights 1.5/1.0/0.7 | No |
| 11 | Stair at left-center, width 2.2–3.0 m | ASAA RULE | `_carve_staircase_zone` | No |
| 12 | Foyer ≤6 m² at front edge | ASAA RULE | `_carve_entrance_zone` | No |
| 13 | Spine strip at 45% | ASAA RULE | `_carve_circulation_spine` | No |
| 14 | Room order (social, service, circulation, private…) | ASAA RULE | `_order_rooms_by_strategy` | No |
| 15 | Cut axis and cut coordinate | ASAA RULE | `_recursive_bisection` / `_slice_polygon` | No |
| 16 | Which of ≤3 candidates wins | ASAA OPTIMIZATION | `max(score)` over fixed-weight score | No (weights static) |
| 17 | Room-pair swaps | ASAA OPTIMIZATION | `AdaptiveRefiner` first-improvement hill climb | No |
| 18 | Door connections, door walls, window walls/sizes, shape | **LLM only if provider=huggingface; otherwise OTHER (mock rule engine)** | Prompt → JSON; default `_deterministic_mock_generator` | LLM could vary; mock cannot |
| 19 | Room footprint (centered rectangle in region) | GEOMETRY RULE | `PolygonBuilder.construct_rectangle(anchor="center")` | No |
| 20 | Door at wall midpoint, 90° swing toward source-room centroid | GEOMETRY RULE | `DoorBuilder.build_door` | No |
| 21 | Door intent silently re-routed to "circulation" or dropped when rooms not adjacent | GEOMETRY RULE | `GeometryEngine.construct_floor` except-branch | No |
| 22 | Window skipped if no exterior wall | GEOMETRY RULE | same | No |
| 23 | Valid / invalid; score = 100 − 15·errors − 3·warnings | VALIDATOR RULE | `FloorPlanValidator.validate_floor` | No |
| 24 | Dimension +5%, add door, window→"north" | REFINEMENT RULE (mock) | `_deterministic_mock_refinement_generator` keyword match | No |
| 25 | Which strategies/alternatives to keep | DIVERSITY RULE | Distance ≥ threshold on door-graph signature | No |

**Where the system *looks* agentic but is fixed:** items 2–7 (named "Agents"), 14–17 ("Adaptive" in ASAA — the adaptation is a single swap operator over a static score), 18 (the mock "LLM"), 24 (the "Refinement Agent"), 25 ("Diversity").
**Genuinely generative decision points:** only item 18 when `PLANFORGE_LLM_PROVIDER=huggingface`. No stored evidence exists for that configuration (`tests/integration/test_huggingface_runtime.py` and `scripts/run_e2e_huggingface_sample.py` exist but were not read).

---

## 5. ASAA Audit

### 5.1 Classification (from code, not docs)
**F — Hybrid, dominated by D (rule-based procedural generation).**
- Not **A** (CSP): no variable/domain/constraint propagation; "hard constraints" are *post-hoc checks* in `CandidateScorer.evaluate`.
- Not **B** (heuristic search) in any strong sense: there is no search tree; candidates come from 4 static orderings.
- **C** (optimization): a weighted-sum scorer + first-improvement swap hill-climber (`AdaptiveRefiner`, ≤8 iterations, improvement threshold 0.5) — local, single-operator, single-objective.
- Not **E** (learned): nothing learned.

Pipeline: `AreaBudgeter.compute_budget` → `CandidateGenerator.generate_candidates` (calls `SpatialPartitioner.partition` per strategy) → `CandidateScorer.evaluate` → `AdaptiveRefiner.refine` → `max(valid, key=score)` → regions.

### 5.2 Hardcoded architectural assumptions

| ID | File :: symbol | Behavior | Why it limits | Safe to generalize? | Future direction |
|---|---|---|---|---|---|
| A1 | `spatial_partitioner.py :: _slice_polygon` / `_recursive_bisection` | Only axis-aligned cuts (X or Y) | No diagonal, no non-guillotine, no courtyard plans | Yes, behind a partitioner interface | P18 |
| A2 | `_order_rooms_by_strategy` | 4 fixed category orderings define adjacency | Adjacency determined by list order, not graph | Yes | P18/19 |
| A3 | `candidate_generator.py :: STRATEGIES` | 4 names; `rng = random.Random(seed)` created and **never used** | Candidate set cannot grow; `seed` inert (BUG-05) | Yes | P18/19 |
| A4 | `scoring.py :: WEIGHTS` | 0.25/0.25/0.15/0.15/0.10/0.10 constants | Cannot trade off per client/style | Make configurable | P19, P27 |
| A5 | `scoring.py :: evaluate` (aspect) | ratio ≤1.8→100, ≤2.5→70 | Equates "good room" with near-square bbox | Yes | P19/24 |
| A6 | `scoring.py :: evaluate` (orientation) | `centroid.y <= mid_y` for social items; `orientation` param unused | Not orientation; fixed front=`min_y` | Fix (BUG-04) then generalize | 15.1, P18 |
| A7 | `scoring.py :: evaluate` (defaults) | Missing circ zones ⇒ 85; no relationships ⇒ 80/90 | Inflates scores when information is absent | Yes | P19 |
| A8 | `allocator.py :: _allocate_floor` | `circ_ratio = 0.12`, `staircase_area_sqm = 8.0`, `max_iterations=8` | Same circulation share for every house | Make configurable | P17/19 |
| A9 | `area_budgeter.py` | `PRIORITY_WEIGHTS` 1.5/1.0/0.7; min fallback `0.8×target` else `6.0`; `+1.0` gap smoothing; `1.25×` | Arbitrary sizing law | Configurable / calibratable | P17, P27 |
| A10 | `spatial_partitioner.py :: _carve_staircase_zone` | Left-edge center; width 2.2–3.0 m; fallback corner | Stair always on the west wall; no relationship to entrance/circulation | Yes | P18 |
| A11 | `_carve_entrance_zone` | `min(6.0, 8%)` m², width ≤3.5 m, "front" = `min_y` | No true entry sequence | Yes | P18/20 |
| A12 | `_carve_circulation_spine` | 45% offset, 1.2–2.0 m, thresholds (≥4 m², >30 m², ≥3 specs) | One straight corridor; no L/loop/open-plan | Yes | P18/20 |
| A13 | `allocator.py :: allocate` | `staircase_aligned` true only if polygon `==` exactly | Brittle equality check | Tolerance | 15.1 |
| A14 | `boundary.py :: _derive_plot_polygon` | Area only ⇒ 1.5:1 rectangle, default 200 m² | Invents plot shape (violates no-invention in spirit) | Gate in Requirement | P16 |
| A15 | `boundary.py :: _apply_polygon_setbacks` | Directional setbacks on irregular polygon use bounding-box clipping | Not edge-wise setbacks | Yes | P18 |
| A16 | `allocator.py :: allocate` | Every floor uses the same buildable polygon and independent partition | No structural stacking, no setback of upper floors | Yes | P17/18 |
| A17 | `spatial_partitioner.py :: _recursive_bisection` single-item leaf | Room gets `poly.area` (all remaining area) | Rooms absorb the entire leftover; budget is only a ratio | Yes | P17/19 |

### 5.3 ASAA facts that surprised the audit
- **Seed is inert** (A3, BUG-05). Determinism holds trivially; "seeded RNG" in `docs/ASAA.md §18` is not a mechanism.
- **Orientation is not implemented** (A6/BUG-04) although `docs/ASAA.md §10` states ASAA aligns social rooms toward the preferred facade.
- **"Hard Constraint D" (attached-room proximity) is not hard** — it appends a rejection reason but does not set `is_valid=False` (BUG-11).
- **Infeasibility check ignores minimum circulation** (docs §5.2 says it includes it) — `AreaBudgeter` compares `Σmin` to `buildable − stair` only.
- **`_slice_polygon` keeps only the largest component** of each cut (`extract_largest_polygon`); for non-convex plots this can silently lose area. Docs guarantee containment and non-overlap, **not coverage**. [HYP — needs a non-convex-plot test measuring Σ region areas vs buildable area] (BUG-13).
- **Budgeter pass-2 adds the room's share of the *total* remainder to the *per-instance* minimum** and later multiplies by `count` (`allocated[rs.id] * rs.count`). The overshoot is hidden by `final_circ = max(0, …)`. [HYP] (BUG-12).

---

## 6. LLM Audit

### 6.1 What the LLM may decide
Per `ARCHITECTURAL_SYSTEM_PROMPT` + `ArchitecturalOutputValidator`: `intended_shape` ∈ {rectangular, square, l_shaped, custom}; `intended_dimensions`; `intended_area_sqm` (≤ allocated ×1.05, ≥ min−0.2); per-room door list (`connects_to`, compass wall, width/height, rationale); per-room window list (compass wall, type, size, sill); `connected_spaces`; rationale text.

### 6.2 What is decided before the LLM sees the problem
All positions, all region polygons and areas, the adjacency graph, categories, priorities, entrance/stair/corridor locations, floor assignment, room list. User-specified dimensions are **forced** (`UserDimensionConstraintViolationError`).

### 6.3 What is ignored or overridden afterwards
- Doors whose target room is not physically adjacent are **silently re-routed to `circulation`** and, if that fails, **dropped** (`GeometryEngine.construct_floor`, logger warning only).
- Windows with no exterior wall are **dropped**.
- `custom` shape and `proposed_boundary` → region fill/bbox (parser always sets `proposed_boundary=[]`).
- A compass wall that doesn't exist on the room → "widest available wall" fallback.
- A rectangle smaller than its region is **centered** (`anchor="center"`), which can break shared walls and then trigger the door fallback.
- `StaircaseIntent` is always `stair_type="straight"`, `recommended_width=1.0` (hardcoded in `ArchitecturalAgent._design_floor`; not LLM-chosen).

### 6.4 Can it propose genuinely different solutions?
Only *within the fixed partition*, and only along dimensions {door graph, door/window compass wall, shape/dim inside region}. It cannot move, merge, split, resize beyond ±bbox, or reorder rooms. Under the default mock, strategies differ only by branch tables; `privacy_centric` ≡ `service_clustered` (same `else:` branch; `elif strategy in ("privacy_centric","open_social"): intended_shape = "rectangular"` is a no-op) **[SRC]** → exact duplicate, rejected by the diversity filter.

### 6.5 Information sufficiency
Prompt fields (`prompts.build_floor_prompt`): plot orientation, circulation zone tags + note, entrance/stair intent dicts, per-room: ids, type, priority, category, areas, `approximate_dimensions` (bbox w×l), adjacent room **types**, user/system adjacencies, avoid list, attached id, user dims.

| Reasoning topic | Info available to LLM? | Schema can represent output? | Geometry preserves? | Validator evaluates? |
|---|---|---|---|---|
| Privacy | No (no sightlines, no entry sequence) | No | n/a | No |
| Daylight | No (no exterior-wall info, no solar) | Window intent only | Partially (centered; silently dropped) | Only wall-type/size sanity |
| Ventilation | No | `window_type="ventilation"` string | Same | No (no cross-vent check) |
| Circulation | Tags only | `connects_to="circulation"` | Fallback re-routing | Connectivity (social rooms only) |
| Functional zoning | Category string | – | – | No |
| Room proportions | bbox dims only | `intended_dimensions` | Rect centered / region fill | Area only (no ratio) |
| Visual relationships | No | No | No | No |
| Architectural style | No field | No | No | No |
| **Which wall faces which neighbor** | **No polygon, no neighbor direction** | compass `wall_orientation` | Matches compass to wall | Door existence only |

### 6.6 Separation of causes

| Class | Items |
|---|---|
| **LLM limitation** (model-capability) | Cannot be assessed: no stored evidence with a real LLM. Provider code is complete (`HuggingFaceClient`) but outputs never entered the benchmark. |
| **System-architecture limitation** | Prompt omits polygons/neighbor geometry; allocation fixed before LLM; refinement cannot go upstream; diversity shares one allocation; silent geometry fallbacks erase LLM intent; mock rule engine masquerades as the LLM in all evaluation. |
| **Schema limitation** | `DoorIntent` has no position/anchor; `WindowIntent` has no daylight/ventilation/view fields; `RoomDesign` has no adjacency/privacy/zone/pattern fields; no `proposed_boundary` use; shape vocabulary of 3. |

### 6.7 Provenance honesty (RULE 7)
`MockLLMClient.last_metadata` hard-codes `"model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"`, and `ArchitecturalAgent._design_floor` writes `"model": self.config.model_name` (default = DeepSeek) even when `provider == "mock"`. A reader of the metadata alone could believe DeepSeek produced the design (BUG-10). `provider: "mock"` is also written, so the truth is recoverable, but the `model` field is misleading.

### 6.8 Provider wiring inconsistency
`ArchitecturalAgent` uses `LLMConfig.from_env()`; `RefinementAgent` defaults to `LLMConfig()` (provider `"mock"`) and `RefinementLoop()` builds `RefinementAgent()` with no config. With `PLANFORGE_LLM_PROVIDER=huggingface`, stage 4 would call a real LLM while refinement silently stays on keyword rules (BUG-09, L9).

---

## 7. Data Contract Audit

Models: `Requirements/FloorRequirement/RoomRequirement`, `PlanningSpec/FloorPlanSpec/RoomSpec`, `Allocation/AllocatedRegion`, `ArchitecturalDesign/RoomDesign`, `ValidationIssue/Result/Report`, `RefinementResult/Change`, `DesignAlternative/Signature`. (Geometry/Door/Window/Staircase models not read.)

| Concept | Representable today? | Where / how | Gap |
|---|---|---|---|
| Hard user constraints (min/max/pref area, dims, count, adjacency, separation, attached, floors, plot, setbacks, orientation, entrance) | **Yes** | `RoomRequirement`, `Requirements` | none |
| Architectural intent (design goals) | **No** | – | New `ProgramIntent` |
| Soft preferences with strength | **No** | `adjacency`/`separation` are un-weighted `list[str]`; `RoomSpec.priority` is a 3-level string | Need `Preference(kind, strength, source)` |
| Functional zones | Partial | `RoomSpec.room_category` (6 strings), `AllocatedRegion.zone_type` (4 strings) | No zone entity, no hierarchy |
| Privacy relationships / gradients | **No** | – | Public→semi→private depth |
| Visual relationships / sightlines | **No** | – | – |
| Daylight / ventilation preferences | **No** | `WindowIntent.window_type` string only | – |
| Circulation preference | Weak | `FloorPlanSpec.circulation_zones: list[str]`, `circulation_notes: str` (unconsumed) | Typed circulation intent |
| Room hierarchy (suite, wing) | Weak | `attached_to_room_id` only | – |
| Architectural patterns | **No** | – | Pattern reference + parameters |
| Style | **No** | – | – |
| Shape preference | Weak | `RoomDesign.intended_shape` (3 values) | Shape vocabulary + tolerance |
| Qualitative user preference | **No** | `Requirements.notes: str` unused downstream | – |
| Alternative strategies | Partial | `DesignStrategy` enum (6) used only by Architectural/Refinement prompts | Not an ASAA-level concept |
| Performance metrics (daylight area, etc.) | **No** | `ValidationResult.score` is a scalar | Metric records |
| Provenance of each value | Partial | `RoomRequirement.source` ("user"/"derived"/"default"), `DecisionTrace` | No per-field provenance on soft data |
| Geometry intent fidelity (intent vs realized) | **No** | – | Needed to detect silent fallbacks |

**Additional schema defects:** `ValidationResult.score` collapses all severities to one scalar; `AllocatedRegion.score` is set to the **candidate** score for every region (not per region); `RoomDesign.intended_area_sqm` can disagree with `intended_dimensions` product after refinement; refinement prompt schema (`door_type:"standard"`, `purpose`, `daylight_intent`, `ventilation_required`) is **not the same schema** as the architectural prompt (`door_type:"interior|entrance|balcony"`, `recommended_width`, …) and `RefinementOutputValidator` **drops** `purpose/daylight_intent/ventilation_required` and resets omitted widths to 0.9/1.2 (LIM-20).

---

## 8. Geometry Audit

| Capability | Status | Evidence |
|---|---|---|
| Orthogonal geometry | Supported | `PolygonBuilder`, region polygons from bisection |
| Non-rectangular rooms | Only 6-vertex L: default 40% cutout, `north_east` quadrant, or region returned unchanged if it already has 6 vertices | `construct_l_shaped` **[SRC]** |
| Irregular room geometry | Only if the **ASAA region** is irregular (rooms then fill the region) | `construct_from_intent` default branch |
| Curved geometry | **None** (polygon coordinates only; swing arc is an 8-segment polyline) | **[SRC]** |
| Wall generation | Exterior = unshared edge; interior = pairwise overlap ≥0.3 m within 0.08 m | `WallBuilder` |
| Doors | Midpoint of chosen wall; no collision handling for two doors on one wall; swing toward source-room centroid | `DoorBuilder` |
| Windows | Centered on chosen exterior wall; no spacing, no multiple per wall | `WindowBuilder` |
| Stairs | `GeoStaircase.polygon = allocated region`; `riser_count=16`, `tread_depth=0.28` are constants; computed `run_length` is **unused**; no check that a 15×0.28 = 4.2 m run fits an ~8 m² core | `StaircaseBuilder` |
| Corridors | `GeoRoom(is_corridor=True)` from `zone_type=="circulation"` regions only | `CorridorBuilder`, `GeometryEngine` step 2 |
| **Entrance/foyer zone** | **Allocated by ASAA (`zone_type="entrance"`) but `GeometryEngine.construct_floor` builds rooms only from `RoomDesign`s and `circulation` regions** → no `GeoRoom` is made for it; the region has `room_spec_id=None` so `ContextBuilder` also never designs it | `engine.py`, `context.py` **[SRC]** (BUG-14; runtime effect not reproduced) |
| Multi-floor geometry | Per-floor independent; stair polygon replicated | `construct` |
| Containment check | `is_contained_in(…, 0.05)`; violation raises `RoomOutOfBoundsError` → **whole floor fails** (no per-room recovery) | `RoomBuilder.build_room` |
| Intent fidelity tracking | None — dropped/re-routed doors and dropped windows are logged, not recorded in the model | `engine.py` |

**Voids and "false exterior" walls.** Because a shrunken rectangle is centered in its region and wall type is defined as "unshared edge", an internal void creates edges classified as `exterior`. A window may then be placed facing an internal void and `WindowValidator` will accept it (it only tests `wall.type == "exterior"`). [HYP — requires a case where intended dims < region dims; mock normally copies region dims.]

---

## 9. Validator Audit

`FloorPlanValidator.validate_floor` runs: Boundary, Overlap, Room (completeness/allocation/topology), Dimension, Relationship, Door, Window, Staircase, Connectivity, Circulation. Score = `max(0, 100 − 15·errors − 3·warnings)`. `EVALUATED_CATEGORIES` has 13 entries (docs say "18 check groups").

### 9.1 HARD VALIDITY (present)

| Check | Status | Note |
|---|---|---|
| Boundary containment (plot, buildable) | Yes | `BoundaryValidator` (not read in detail) |
| Overlap | Yes | `OverlapValidator` (not read in detail) |
| Room completeness / invented rooms | Yes — **by type count, one per RoomSpec** | Counts `expected_room_types` once per spec, not × `count` (BUG-03 co-cause) |
| Floor assignment | Yes | |
| Allocation containment & references | Yes | |
| Polygon validity / area>0 | Yes | |
| Min area (hard, 5% tolerance); target deviation ±25% warn | Yes | Keyed by `room_type`; duplicate types share one entry |
| Required adjacency / separation / attached | Yes | Required = user pairs **plus all adjacencies of `priority=="high"` rooms**; attached parent via hardcoded types |
| Doors (attachment, width, swing) | Yes | `DoorValidator` not read |
| Windows (valid wall, exterior-typed, size) | Yes | Orientation mismatch is a **warning** |
| Stairs (existence, multi-floor alignment) | Yes | `StaircaseValidator` not read |
| Connectivity | Partial | Isolated habitable room; **only living/dining/hall/drawing** must be reachable from entrance — bedrooms/baths reachable only through other private rooms pass |
| Floor-count match | Yes | `expected_floor_count = requirements.target_floors` (None would mismatch; gate normally prevents) |

### 9.2 ARCHITECTURAL QUALITY (absent)

| Quality | Present? |
|---|---|
| Habitable room has ≥1 window / daylight area ratio | **No** (windows are validated only if they exist; dropped intents are invisible) |
| Cross-ventilation / ventilation opening ratio | No |
| Privacy (sightline from entrance/social to bedroom, door-to-door exposure) | No |
| Circulation efficiency (path length, corridor/area ratio, dead ends) | No |
| Room proportion (aspect limits, min width) | No — only the **scorer** in ASAA uses aspect, the validator never does |
| Furniture/usability clearances | No |
| Visual connectivity | No |
| Functional zoning coherence | No |
| Entrance sequence | No (only "entrance door exists") |
| Service efficiency / plumbing adjacency | No |
| Architectural coherence | No |

**Consequence:** a plan can be `overall_valid=True` with a windowless bedroom, a bedroom entered through a bathroom, a 1:5 sliver room, or fewer rooms than requested (BUG-03).

### 9.3 Protection note
This audit recommends **adding** deterministic quality checks in future phases and **keeping** hard validation unchanged and authoritative. It recommends no weakening and no LLM judging.

---

## 10. Refinement Audit

| Question | Finding |
|---|---|
| What kind of loop? | **Rule-based adjustment** (default `MockLLMClient` + `_deterministic_mock_refinement_generator`) wrapped in a validate-reconstruct loop; with a real provider it would be **repeated LLM proposal** over the same intent set. |
| Targeted repair? | Per-floor: floors with zero errors are copied; floors with errors get a whole-floor prompt containing all rooms, and the response must restate all rooms. Mock edits are keyed on **string occurrence in the prompt** (`"missing_entrance_connection" in prompt` …), not on room-level diagnostics. |
| Repairable | Missing entrance door (adds `entrance` door to living/first room), isolated room (adds door to "corridor"), living–dining adjacency (adds door only if rooms already touch), undersize (×1.05 per iteration within region), window orientation (forces "north"). |
| Not repairable | Anything rooted upstream: non-adjacent required rooms, separation violations, undersized *region*, missing rooms (BUG-03), plot/setback issues, topology, stairs. `RefinementOutputValidator` forbids changing `allocated_region_id`; there is no path back to ASAA/Planning (LIM-18). |
| Chooses repair strategy? | No. Fixed `CATEGORY_PRIORITY` ordering for diagnostics; one strategy (rewrite intent). |
| Can change only intent? | Yes — `shape`, `dims`, `doors`, `windows`. |
| Allocation immutable? | Yes (enforced). |
| Repeated failures diagnosed? | Only via SHA-256 fingerprint: no-change ⇒ `REFINEMENT_FAILED`; revisit ⇒ `REFINEMENT_FAILED`. No root-cause classification. `RefinementContext.previous_history` is built but **not used** in `build_refinement_floor_prompt` — no learning from prior attempts within a run. `DEVELOPMENT_ROADMAP` cites an `OSCILLATION_DETECTED` status that **does not exist** in `RefinementStatus`. |
| Invariants re-checked? | **Not fully**: `RefinementOutputValidator` does not re-enforce `user_specified_dimensions` (the mock's +5% growth can violate them) and uses a looser ±15% bbox bound instead of the architect stage's ±5% area bound. |
| Orchestrator integration | **Broken** (BUG-01): `self.refinement_loop.run(initial_design=…, allocation_set=…, planning_spec=…, initial_report=…, max_iterations=…, requirements=…)` — `RefinementLoop.run` has no `initial_report`/`max_iterations` parameters ⇒ `TypeError`, caught by the stage's `except Exception`, so the stage is marked FAILED and generation continues unrefined. Then `ref_res.iteration` and `ref_res.applied_changes` are read although `RefinementResult` defines `total_iterations`/`changes`. The path is untested: `test_orchestrator.py` runs with `enable_refinement=False` or valid plans (so refinement is skipped), and all 15 feasible stored cases were valid on first pass (`timing_refinement_ms ≈ 0`) **[RES]**. The same loop works correctly when invoked from `MultiDesignGenerator`. |
| Opportunities | Goal-directed repair: classify failure origin (intent vs allocation vs requirement-infeasible), choose operator (door retarget, dimension resize, region re-request), per-room prompts, use `previous_history`, add escalation to a controlled upstream-feedback protocol. (Phase 25.) |

---

## 11. Diversity Audit

| Aspect | Finding | Evidence |
|---|---|---|
| What varies between alternatives | Only the Architectural stage (`strategy`, `alternative_index` inserted into the prompt) and the refinement `target_design_strategy`. | `MultiDesignGenerator.generate` receives one `allocation_set` and passes it unchanged to every candidate **[SRC]** |
| Strategy-based diversity | Yes, nominally 6 strategies. | `DEFAULT_STRATEGIES` |
| Effective strategies under default mock | `privacy_centric` and `service_clustered` share the final `else:` branch ⇒ identical door/window output ⇒ distance 0.0 ⇒ `DUPLICATE`. Effective ≤5. | `_deterministic_mock_generator` **[SRC]** |
| Structural diversity | Defined on `DesignSignature` built from **door intents** (`connects_to`, `door_type`), room shape strings and aspect buckets — not from region polygons, not from realized geometry. | `DesignSignatureBuilder.build` **[SRC]** |
| True architectural diversity | **No**: room positions, partition, circulation geometry, stair/entrance position are identical in every alternative. | invariant is *documented* (`MULTI_DESIGN_DIVERSITY.md §2`) and implemented |
| Pattern / shape / topology diversity | Pattern: none. Shape: mock never emits `l_shaped`; only square vs rectangular. Topology: door-graph only. | **[SRC]** |
| User-preference diversity | None (no preference model). | §7 |
| Metric vs docs | Doc weights 0.40/0.20/0.10/0.10/0.05×4; code 0.35/0.15/0.15/0.15/0.20. Threshold: doc 0.15, `generate()` default 0.25, `OrchestrationConfig` 0.20. Circulation labels differ (`open_plan/central_spine/compact_hub` vs `corridor/direct/hybrid_*`). Social sequence uses set equality, not Levenshtein. | `metrics.py`, `generator.py`, `config.py` vs docs **[SRC]** |
| Semantics of "social_sequence" | Derived from door edges, not from entrance traversal. | `signature.py` |
| Evidence in stored results | **None.** All 16 runs used `num_alternatives=1`; `diversity_mean_distance = NOT_AVAILABLE`; and the metric function itself reads a nonexistent attribute (BUG-06). The report's §5 has no data. | **[RES][SRC]** |

**Conclusion:** the diversity subsystem measures variation in *door-connection intent*; it cannot presently claim spatial or topological architectural diversity.

---

## 12. Benchmark Audit

### 12.1 What it measures
20 metric families (`MetricCalculator`): requirement adherence, room-count accuracy, area satisfaction, allocation adjacency/separation/attached, boundary & overlap compliance (derived from **validator** results), connectivity (derived from validator), door/window compliance (derived from validator), staircase, validation success, refinement effectiveness, diversity, alternative validity, trace completeness/fabrication, timing, ASAA rate, reproducibility.

### 12.2 What it does not measure
Daylight, ventilation, privacy, circulation efficiency, proportion beyond area, furniture usability, visual connectivity, zoning coherence, entrance sequence, style, user-preference fit, expert rating, comparison with reference architectural plans.

### 12.3 Ceiling effect **[RES]**
On the 15 feasible cases, nine percentage metrics are exactly `100.0` with `std_dev 0.0` (`req_room_coverage`, `req_floor_count_adherence`, `allocation_adjacency_compliance`, `separation_compliance`, `attached_suite_compliance`, `boundary_compliance`, `connectivity_rate`, `door_compliance`, `staircase_compliance` n=3) and five error-count metrics are exactly `0` (`area_max_violations`, `boundary_violation_count`, `overlap_violation_count`, `disconnected_room_count`, `validation_error_count`). Several of these are *derived from the validator*, so they restate `overall_valid` rather than add independent evidence. Only `validation_warning_count` (0–9), `validation_score` (73–94), `area_preferred_mae`, `area_min_compliance` and `room_count_accuracy` vary.

### 12.4 Can two architecturally different plans score the same?
Yes. Metrics are insensitive to: window facade, door graph (except "exists"), room proportion within area bounds, position of rooms outside adjacency pairs, circulation shape, entrance position, and (BUG-03) the **number of repeated rooms actually built**.

### 12.5 Defects that mislead results
- **BUG-03 visible only in `room_count_accuracy`:** 55.6 (case_08), 66.7 (case_03), 83.3 (cases 02, 04, 12, 13). Each equals `1 − Σ|req−built| / Σreq` when every `count>1` room type contributes `count−1` missing instances (e.g. case_08: bedrooms 4→1, bathrooms 2→1, Σdiff 4, Σreq 9). Meanwhile `validation_success=True` and `req_room_coverage=100.0` for all 15. The Markdown report states "Room Coverage 100.0%".
- **BUG-08:** `req_room_coverage` compares *number of requirement entries (types)* with *all* geometry rooms **including corridors**, capped at 100%.
- **BUG-06:** `alternative_validity_rate = 0.0` with `alternatives_generated_count = 1` and `alternatives_valid_count = 0` for all 15 cases, while the same plans are `overall_valid=True` — the function reads `overall_valid`, an attribute `DesignAlternative` does not define (it has `is_valid`). Diversity function reads `signature` (field is `design_signature`).
- **BUG-07:** `trace_entity_chain_completeness` mean 559% (unbounded ratio).
- **BUG-17:** `area_min_compliance` uses an implicit 5.0 m² floor (`min_bound = … else 5.0`) that is neither in the requirement nor enforced by the validator; cases with a ~4.2–4.6 m² bathroom report 75%.
- **BUG-16 (requirement integrity):** every benchmark brief says `… side setback: 2m`. The parser stores key `"side"`; `BuildableBoundaryCalculator._normalize_setbacks` reads only `front/rear/left/right/all`, so side setbacks are **silently dropped**. [RES] corroboration: `case_16` (20×20 ft = 6.096×6.096 m, front+rear 2 m) reports available buildable area **12.8 m²** = 6.096 × 2.096; with side setbacks applied it would be 2.096 × 2.096 = 4.4 m². The same `"side"`-blind logic is duplicated in `FloorPlanValidator`'s fallback boundary, so the validator cannot catch it.
- **Failure analysis:** `case_16` is labelled `classified_cause_stage: "Validation"` although the error is `InfeasibleAllocationError` raised in ASAA's budgeter.
- **Report formatting:** the "Difficulty" column prints the category tag.

### 12.6 Ablations and baseline
- ASAA-vs-baseline: valid as a comparison of *area MAE and adjacency%* only (report: ASAA 2.75–12.9 m² MAE, 100% adjacency vs baseline 8.36–24.05 m², 66.7%). The baseline (`BaselineSpatialAllocator`) slices one strip per RoomSpec, ignores `count`, circulation spine and entrance, so it is a weak control; and both feed the same count-collapsing downstream (BUG-03).
- Refinement ablation: `error_reduction = 0.0` and `validity_gain = 0.0` on all 4 cases because no case ever needed refinement ⇒ **RQ3 is unanswered**.
- Diversity ablation: values blank in `ablation_metrics.csv` ⇒ **RQ4 is unanswered**.
- Reproducibility: 2 cases × 3 runs, mock LLM only.
- (`ablation_results.json`, `runner.py`, `reproducibility.py` were not read; statements above rely on the CSV and Markdown report.)

### 12.7 Can it detect architectural improvement?
No — neither a better nor a worse architectural plan (in the sense of §9.2) would change any current metric.

---

## 13. Hardcoded Knowledge Inventory

Disposition: **K** = keep deterministic; **C** = make configurable; **L** = candidate for learned/retrieved; **D** = fix/defect.

| ID | Location | Hardcoded knowledge | Why it exists | Disposition | Phase |
|---|---|---|---|---|---|
| HK-01 | `planning_agent/categorizer.py :: ROOM_FUNCTIONAL_ZONES` | room type → 6 zones; substring fallback | quick zoning | C/L | 17 |
| HK-02 | `priority_calculator.py :: PRIORITY_RULES` | high/normal/low per type; `user_override` never wired | explainable priority | C | 16/17 |
| HK-03 | `relationship_graph.py :: DEFAULT_PREFERRED_ADJACENCIES` | 10 symmetric pairs | architectural convention | C/L | 17/20 |
| HK-04 | `relationship_graph.py :: DEFAULT_AVOID_PAIRS` | 6 pairs (garage–bedroom, attached_bath–living…) | convention | C | 17 |
| HK-05 | `circulation_planner.py` | zone tags, default entrance facing "north", entrance room "living", stair always "required" if multi-floor | default intents | C/D | 16/17 |
| HK-06 | `planning_agent/agent.py :: _build_global_constraints` | raw-text phrase match for `no_corridor`; `privacy_buffering: True` constant (unconsumed) | quick flag | D (move to Requirement) | 16 |
| HK-07 | `requirement_agent/parser.py` | unit regexes, `G+N`, ordinal floors, BHK→bedroom/living/kitchen, `near`⇒required adjacency | NL coverage | C/L | 16 |
| HK-08 | `normalizer.py :: ROOM_SYNONYMS…` | (not read) | synonyms | C | 16 |
| HK-09 | `allocator.py :: _allocate_floor` | `circ_ratio=0.12`, `staircase_area_sqm=8.0`, refiner `max_iterations=8` | budget defaults | C | 17/19 |
| HK-10 | `area_budgeter.py` | priority weights 1.5/1.0/0.7; min fallback 0.8×target else 6.0; +1.0; ×1.25; min circ `max(4.0, ratio·area)` | sizing law | C/L | 17/27 |
| HK-11 | `candidate_generator.py :: STRATEGIES` | `front_to_back, lateral, radial, orientation_aligned` | candidate families | C/L | 18/20 |
| HK-12 | `spatial_partitioner.py :: _order_rooms_by_strategy` | category sequences per strategy | zoning heuristic | L/C | 18/20 |
| HK-13 | `_carve_circulation_spine` | 45% offset; width clamp 1.2–2.0; thresholds 4 m²/30 m²/3 specs | corridor heuristic | C/L | 18 |
| HK-14 | `_carve_staircase_zone` | left-center; width 2.2–3.0; corner fallback | stair placement | C/L | 18 |
| HK-15 | `_carve_entrance_zone` | ≤6 m² / 8%, ≤3.5 m / 40%; front=`min_y`; area>20 gate | entry zone | C/L | 18 |
| HK-16 | `_recursive_bisection` | 0.8×half split; axis rule (dy>0.7dx etc.); 25-step binary search; fallback midpoint | partition mechanics | K/C | 18 |
| HK-17 | `scoring.py :: WEIGHTS` + thresholds | 6 weights; aspect 1.8/2.5; 80/85/90 defaults; −20 per avoid violation; ×0.2 invalid | scoring | C/L | 19/27 |
| HK-18 | `boundary.py` | area-only ⇒ 1.5:1, 200 m²; front=`min_y`; bbox clipping for directional irregular setbacks; **"side" key ignored** | plot defaults | D/C | 15.1/16 |
| HK-19 | `architectural_agent/agent.py :: _deterministic_mock_generator` | per-strategy door tables, wall compass choices, window sizes (1.2×1.5, sill 0.9; service 0.6×0.6, sill 1.5), orientation social→N / private→E / service→W | offline stand-in for LLM | K (as test double only) | 22 |
| HK-20 | `structured_output.py` | `ALLOWED_SHAPES`, +5% area tolerance, −0.2 min tolerance | schema bounds | K/C | 22 |
| HK-21 | `agent.py :: _design_floor` | `stair_type="straight"`, width 1.0 | stair intent | C | 22 |
| HK-22 | `polygon_builder.py` | L-shape 40% cutout NE; `anchor="center"` | shape construction | K/C | 18/22 |
| HK-23 | `GeometryEngine` | wall 0.20/0.15 m, height 3.0 m; door at 0.5; windows centered | construction constants | C | 22/23 |
| HK-24 | `staircase_builder.py` | 16 risers, 0.28 tread | stair constants | C/D | 23 |
| HK-25 | Validators | tolerance 0.05; shared boundary 0.3; dim 5%/25%; score −15/−3; window tol 0.15 | verification thresholds | K (+C) | 24 |
| HK-26 | `relationship_validator.py` | attached parent types; high-priority ⇒ hard adjacency | validation shortcut | D | 15.1 |
| HK-27 | Refinement | `CATEGORY_PRIORITY`; mock rules (+5%, window→north); bbox ±15%; loop default 3 iterations vs config 5 | repair policy | K/C | 25 |
| HK-28 | Diversity | 6 strategies; signature rules; weights; thresholds 0.25/0.20/0.15 | diversity policy | C | 18/30 |
| HK-29 | `evaluation/metrics.py` | implicit 5.0 m² min; dup<0.05, near<0.20; stage coverage /10 | metric policy | D/C | 15.1/30 |
| HK-30 | `completeness_gate.py` | warning text promising municipal setbacks | UX text | D | 15.1 |
| HK-31 | `llm/configuration.py` | temp 0.2, 4096 tokens, 120 s, DeepSeek-R1-Distill-Qwen-7B default model | runtime defaults | C | 22 |

**Rule:** items marked K stay deterministic (safety/reproducibility). "Learned" never means replacing verification.

---

## 14. Protected Deterministic Invariants

These **must not** be compromised by any later phase. Status = whether the *current implementation* upholds it.

| ID | Invariant | Current status |
|---|---|---|
| PI-01 | **Requirement integrity & no-invention** — never add rooms/floors; incomplete briefs stop at the gate | Upheld for rooms/floors (`CompletenessGate`, tests `test_no_room_invention_on_missing_floors`). **Violated for setbacks** (BUG-16: user side setbacks silently ignored) and plot shape default (A14) |
| PI-02 | Room identity & traceability (`source_requirement_id → room_spec_id → region id → architectural_room_id → geo id`) | Upheld per spec; **broken for `count>1`** (BUG-03) |
| PI-03 | Floor assignment immutable | Upheld (architectural + refinement validators) |
| PI-04 | Hard user constraints (min area, explicit dimensions, explicit adjacency/separation, floors) | Partially: user dims enforced at architect stage only (LIM-20) |
| PI-05 | Boundary containment & non-overlap | Upheld (ASAA scorer + validator) |
| PI-06 | Geometry constructed only by `GeometryEngine`; LLM emits no coordinates | Upheld (`RefinementOutputValidator` forbids geometry keys; architect schema semantic) |
| PI-07 | Topology/wall derivation deterministic | Upheld; independence of definitions with validator is weak (L-b) |
| PI-08 | Doors/windows/stairs only realized & checked physically | Upheld; silent fallbacks reduce transparency (LIM-17) |
| PI-09 | Validator is the sole authority; zero LLM; no self-certification | Upheld |
| PI-10 | Export integrity (`verify_export_integrity`) | Not audited |
| PI-11 | Reproducibility under fixed inputs | Upheld trivially (seed inert); fingerprints exist |
| PI-12 | Provenance of every decision | Upheld structurally; `model` field misleading for mock (BUG-10) |
| PI-13 | ASAA allocation immutability downstream | Upheld. Any future upstream feedback needs an explicit, logged protocol, never silent mutation |
| PI-14 | WHAT/ORGANIZE/WHERE/HOW/CONSTRUCT/VERIFY/CORRECT separation | Structurally upheld; four leaks (§2.3) |
| PI-15 | No fabricated results; neutral presentation of alternatives (no "best") | Upheld in code paths read; stored report headline "Room Coverage 100%" is *misleading* (BUG-03/08) |
| PI-16 | Hard errors invalidate; warnings never mark a category passed | Upheld (`ValidationResult.add_issue`) |
| PI-17 | No LLM/mock presented as intelligence | At risk (BUG-10; mock is the only evaluated generator) |

---

## 15. Limitation Register

Categories: L1 Representation · L2 Reasoning · L3 Search · L4 Optimization · L5 Geometry · L6 Validation · L7 Learning · L8 Data · L9 Integration · L10 Implementation Bug (bugs are in §16/Appendix A and the JSON `bugs` array; `LIM-` entries below are *not* bugs).
Each entry: **Cat · Sev · Component** — *Evidence* — Current → Desired — Root cause — Direction — Regression risk. Full field set also in the JSON.

**LIM-01 · L1 · Critical · Data contracts.** *§7 table.* Only hard numeric/relational requirements are representable → soft preferences with strength, intent, style, privacy, daylight, ventilation, visual relations, patterns, hierarchy. Root: models were designed for constraint satisfaction. Direction: additive optional dataclasses with provenance (P16). Risk: Low if additive/defaulted; serializers & exports must tolerate.

**LIM-02 · L1 · High · RoomDesign / PolygonBuilder.** *`ALLOWED_SHAPES`, `proposed_boundary=[]`.* 3-shape vocabulary → parametric & irregular room shapes. Root: schema + builder. Direction: shape vocabulary + parameter block (P18/22). Risk: Medium (geometry/validator).

**LIM-03 · L1 · High · DoorIntent/WindowIntent.** *§6.5.* No anchor/position/neighbor relation or intent-vs-realized record → positioned, referenced openings with fidelity tracking. Root: compass-only intent. Direction: anchored intents (P22). Risk: Medium.

**LIM-04 · L1 · Medium · Plot frame.** *`boundary.py`, planner default "north".* No notion of road frontage, front edge, or orientation→coordinate mapping; front=`min_y`. → explicit site frame. Root: coordinate convention baked in. Direction: P16/18. Risk: Medium (changes every coordinate-dependent rule).

**LIM-05 · L2 · High · Requirement Agent.** *Parser regexes.* Regex-only NL; no ambiguity/qualitative handling; "L-shaped plot of W by D" parsed as rectangle [HYP-runtime]. → robust extraction with provenance, asks when ambiguous. Direction: P16 (deterministic first; optional LLM extraction must be validated by deterministic schema). Risk: Medium (benchmark parse drift).

**LIM-06 · L2 · High · Planning Agent.** *Lookup tables; `user_override`, circulation tags unused.* No program reasoning (sizes, zoning depth, service clustering). Direction: P17. Risk: Low–Medium.

**LIM-07 · L2 · High · Architectural LLM path.** *§6.5.* LLM never sees polygons, neighbor direction, exterior walls; no real-LLM evidence exists. Direction: P22 with geometric context + deterministic fidelity checks. Risk: Medium.

**LIM-08 · L3 · Critical · ASAA.** *§5.* ≤4 orderings; orthogonal bisection; adjacency incidental; best-only retained. → hybrid reasoner with diverse partition families and adjacency-driven construction. Root: procedural generator. Direction: P18, P20, P21 (no replacement of ASAA; extend behind interface). Risk: High (touches every downstream fixture) — protect with golden regression.

**LIM-09 · L3 · Critical · Diversity.** *§11.* Alternatives share one allocation; 2/6 strategies identical (mock); signature from door intents. → alternatives from distinct allocations/topologies. Direction: P18/P30. Risk: Medium.

**LIM-10 · L4 · High · CandidateScorer / AdaptiveRefiner.** *§5.* Fixed weighted sum of proxies; single swap operator; no quality objectives; no Pareto set. Direction: P19, P27. Risk: Medium (score semantics change).

**LIM-11 · L5 · High · Geometry.** *§8.* Centered rectangles create voids; midpoint doors/windows; nominal stairs; default L only. Direction: P22/23. Risk: Medium–High.

**LIM-12 · L5 · Medium · WallBuilder / WindowValidator.** *L-b.* Exterior defined as "unshared edge". → envelope-based exterior + independent validator definition. Direction: P24 (validator-side independent computation). Risk: Medium.

**LIM-13 · L6 · Critical · Validator.** *§9.2.* No architectural-quality checks. Direction: P24 (additive categories, `severity="warning"|"quality"` first; hard checks unchanged). Risk: Low if additive; keep scoring formula versioned.

**LIM-14 · L6 · High · Validator hard checks.** *§9.1.* Count-blind completeness; connectivity scope limited; hardcoded attached parents; type-keyed dimension map; priority⇒hard adjacency. Direction: 15.1 then P24. Risk: Medium (stricter ⇒ more failures; expected).

**LIM-15 · L7 · High · System-wide.** *Static weights, no memory; `previous_history` unused.* Direction: P26, P27, P29. Risk: Low if offline & optional.

**LIM-16 · L8 · High · Benchmark/data.** *§12.* 16 uniform-syntax briefs; no reference plans/ratings; ceiling effect. Direction: P28, P30. Risk: Low.

**LIM-17 · L9/L5 · High · GeometryEngine.** *§6.3.* Intent silently re-routed/dropped (log only). → record `intent_fidelity` per door/window and surface it. Direction: P22/24. Risk: Low (additive).

**LIM-18 · L9 · High · Refinement ↔ ASAA/Planning.** *§10.* Allocation-rooted failures are unrepairable. → controlled, logged upstream-feedback protocol. Direction: P25. Risk: High (invariant PI-13) — design as explicit escalation, never mutation.

**LIM-19 · L8 · High · Real-LLM evidence.** *`metadata.json`.* No stored result with a live LLM. Direction: P22 + P28. Risk: Low.

**LIM-20 · L9 · High · Refinement schema.** *§7.* Different schema than architect; fields dropped; widths reset; `user_specified_dimensions` not re-enforced; looser bounds. Direction: shared schema module (P22/25). Risk: Medium.

**LIM-21 · L3 · Medium · Multi-floor.** *A16.* Same footprint for every floor, no stacking/wet-stack/terrace logic. Direction: P17/18. Risk: Medium.

---

## 16. Bug vs Limitation Classification

A **bug** is an intended capability whose implementation is wrong. A **limitation** is a capability the architecture/schema/search/validator does not have. Examples from this audit:

| Statement | Class | ID |
|---|---|---|
| `orientation` is passed to the scorer but never used | **Bug (L10)** | BUG-04 |
| No field for privacy gradient | **Representation limitation (L1)** | LIM-01 |
| Adjacency representable but only 4 orderings of one partition family | **Search limitation (L3)** | LIM-08 |
| LLM could propose an L-shape; Geometry only has a 40% NE default | **Geometry limitation (L5)** | LIM-11 |
| Geometrically valid plan, no daylight metric | **Validation limitation (L6)** | LIM-13 |
| Orchestrator calls `RefinementLoop.run(initial_report=…)` | **Bug (L10)** | BUG-01 |
| Entrance zone allocated but never constructed | **Integration gap (L9)** | BUG-14 |
| Repeated rooms collapse to one | **Bug (L10)**, critical | BUG-03 |
| Side setbacks parsed but ignored | **Bug (L10)**, critical | BUG-16 |

### Bug register (all **L10** unless stated; evidence level in brackets)

| ID | Sev | Component | Defect | Evidence |
|---|---|---|---|---|
| BUG-01 | High | `orchestrator.py` Stage 7 | `refinement_loop.run(initial_report=…, max_iterations=…)` not accepted by `RefinementLoop.run`; reads `ref_res.iteration`/`applied_changes` (nonexistent); exception swallowed; untested path | [SRC] |
| BUG-02 | Medium | `orchestrator.py` Stage 8 | `AlternativeStatus.FAILED_VALIDATION` does not exist (`INVALID`/`REJECTED` do) ⇒ AttributeError when `num_alternatives<=1` and plan invalid; `alternative_set` left `None` | [SRC] |
| BUG-03 | **Critical** | `ContextBuilder.build`, `GeometryEngine`, `RoomValidator` | `count>1` rooms: ASAA emits `count` regions with the same `room_spec_id`; context builds one `RoomDesignContext` per spec (first region); only designed rooms are constructed; validator expects one per spec ⇒ N−1 requested rooms never built yet plan is `valid` | [SRC]+[RES] (metrics arithmetic); not runtime-reproduced |
| BUG-04 | High | `scoring.py`, `refiner.py` | orientation parameter unused; refiner re-evaluates without it | [SRC] |
| BUG-04b | Medium | `circulation_planner.py` vs `scoring.py` / `_carve_entrance_zone` | default entrance "north" ⇒ foyer at `max_y`; scorer prefers social at `min_y` (front); mock puts entrance door on "south" | [SRC] |
| BUG-05 | Low | `candidate_generator.py` | `rng` created, never used; `seed` has no effect | [SRC] |
| BUG-06 | High | `evaluation/metrics.py` | `_calc_diversity` reads `signature`; `_calc_alternative_validity` reads `overall_valid` (neither exists) ⇒ 0% validity, no diversity | [SRC]+[RES] |
| BUG-07 | Medium | `evaluation/metrics.py` | `trace_entity_chain_completeness` unbounded (mean 559%) | [SRC]+[RES] |
| BUG-08 | High | `evaluation/metrics.py` | `req_room_coverage` counts types vs all rooms incl. corridors, capped 100% ⇒ masks BUG-03 | [SRC]+[RES] |
| BUG-09 | Medium | `refinement_agent/agent.py` | defaults to `LLMConfig()` (mock) ignoring env; `RefinementLoop()` has no config path | [SRC] |
| BUG-10 | Medium | `llm/client.py`, `architectural_agent/agent.py` | mock labeled with DeepSeek `model` | [SRC] |
| BUG-11 | Low | `scoring.py`, `refiner.py` | "Hard Constraint D" only warns; refiner returns baseline `is_valid` | [SRC] |
| BUG-12 | Medium | `area_budgeter.py` | pass-2 adds share of total remainder to per-instance area ⇒ over-budget for `count>1`, masked by `max(0,…)` | [HYP] |
| BUG-13 | Medium | `spatial_partitioner.py` | `extract_largest_polygon` in slicing may lose area on non-convex plots | [HYP] |
| BUG-14 | Medium | `engine.py` / `context.py` (L9) | ASAA entrance/foyer zone never constructed or designed | [SRC]; runtime effect not reproduced |
| BUG-15 | Low | `allocator.py` | stair alignment via exact polygon equality | [SRC] |
| BUG-16 | **Critical** | `parser.extract_setbacks` ↔ `boundary._normalize_setbacks` (+ validator fallback) | `"side"` setback key never mapped to left/right ⇒ user constraint silently ignored | [SRC]+[RES] (case_16 area 12.8 m²) |
| BUG-17 | Low | `evaluation/metrics.py` | implicit 5.0 m² minimum in `area_min_compliance` | [SRC]+[RES] |

---

## 17. Future Upgrade Map

Based only on evidence above. Every phase **extends** an existing component, keeps ASAA, and adds capability behind additive interfaces.

| Phase | Addresses | Extends | Must NOT change | Expected capability | Research contribution | Depends on |
|---|---|---|---|---|---|---|
| **15.1 Defect gate** (precondition, not in the brief's list) | BUG-01,02,03,04,06,07,08,09,10,16,17 | orchestrator, ContextBuilder, parser/boundary, metrics, validator completeness | generation semantics beyond bug fix; tests may be *added*, never weakened | Honest metrics; true room counts; side setbacks honored | A trustworthy baseline | none |
| **16 Expanded Requirement Representation** | LIM-01, 04, 05 | `Requirements`, parser, gate | Hard-constraint semantics; no-invention; completeness gate | Optional `Preference`/`ProgramIntent`/`Style`/`SiteFrame` with `source` provenance; ambiguity questions | Formal soft/hard separation | 15.1 |
| **17 Architectural Program Planning** | LIM-06, 21, HK-01–05, 09–10 | Planning agent | Planning never produces coordinates; ASAA stays WHERE | Typed zoning, privacy depth, service clustering, circulation intent that ASAA consumes | Program-level reasoning, explainable | 16 |
| **18 Hybrid Spatial Reasoner** | LIM-08, 09, 21, A1–A17 | `SpatialPartitioner` behind interface | Hard containment/non-overlap; deterministic given seed; ASAA retained | Multiple partition families, adjacency-driven construction, non-orthogonal option, real seeded exploration | Diverse spatial candidates | 17, 15.1 |
| **19 Multi-Objective Spatial Optimization** | LIM-10 | `CandidateScorer`, `AdaptiveRefiner` | Hard constraints remain gates, not weights | Pareto set over area/adjacency/circulation/daylight proxies/privacy; more operators | Objective-vector reporting | 18, 24 (metrics) |
| **20 Architectural Pattern Knowledge** | LIM-01, 08, HK-11–15 | candidate generation | Patterns propose; validator disposes | Pattern library (entry sequences, corridor/open-plan/courtyard templates) | Knowledge-grounded generation | 16–18 |
| **21 Learned Spatial Proposal** | LIM-08, 15 | candidate generator (as additional proposer) | Learned output **never** bypasses validator/hard gates; ASAA fallback retained | Learned proposals scored by deterministic scorer | Learned vs rule comparison | 20, 28 (data) |
| **22 Advanced Architectural LLM** | LIM-02, 03, 07, 11, 17, 19, 20 | Architectural agent, schema, geometry intent fidelity | LLM emits intent only; no coordinates | Context with polygons/neighbor walls; anchored openings; shared schema; real-LLM runs | First real LLM evidence | 15.1, 16 |
| **23 Furniture & Usability** | LIM-13 | new deterministic module, geometry | Hard validity unchanged | Clearance/usable-wall checks | Usability metric | 22 |
| **24 Architectural Performance Validation** | LIM-12, 13, 14 | `FloorPlanValidator` (new categories) | Existing hard checks & severity semantics | Daylight/ventilation/privacy/circulation/proportion checks | Independent quality metrics | 15.1 |
| **25 Goal-Directed Refinement** | LIM-15, 18, 20 | `RefinementLoop` | Allocation immutability except via logged escalation (PI-13) | Failure-origin classification, operator choice, per-room repair | Repair-policy study | 24, 22 |
| **26 Experience Memory** | LIM-15 | new store | Reproducibility: memory versioned & opt-in | Retrieve past solutions | Memory ablation | 28 |
| **27 Strategy/Weight Calibration** | LIM-10, 15 | scorer weights, strategy selection | Hard gates | Calibrated weights from ratings | Calibration method | 24, 28 |
| **28 Architectural Benchmark Dataset** | LIM-16, 19 | `app/evaluation/benchmark.py` | Existing 16 cases & results remain frozen as v1.0.0 | Varied syntax, qualitative briefs, reference plans, expert ratings | Dataset | 16, 24 |
| **29 Human-in-the-Loop Preferences** | LIM-01, 15 | API/UI preferences | Backend authoritative; no UI generation logic | Preference capture & feedback | User study | 16, 27 |
| **30 Research Evaluation 2.0** | LIM-09, 16, §12 | `MetricCalculator`, ablations | v1.0.0 results immutable | Quality-sensitive metrics, valid diversity & refinement ablations, real-LLM arms | Publishable evaluation | 22, 24, 28 |

---

## 18. Recommended Phase 16 Entry Point

1. **Do not start Phase 16 on top of the current metrics.** Run a small **Phase 15.1 defect gate** first (no new capability): add *failing-first* regression tests (never edit existing ones), then fix BUG-03, BUG-16, BUG-01, BUG-02, BUG-06/07/08/17, BUG-09/10, in that order. Re-run the 16-case benchmark as a **new** run (`v1.0.1`) and keep `results/evaluation_run` frozen. Expect `room_count_accuracy` → 100, some `validation_error_count` > 0, and smaller buildable areas — these are *correct* outcomes, not regressions.
2. **Then Phase 16 starts at the Requirement layer, additively:** add optional, defaulted dataclasses (`Preference`, `SiteFrame`, `ProgramIntent`, `StyleHint`) to `app/models/requirements.py`, each with `source ∈ {user_stated, user_confirmed, system_default}`; extend `RequirementParser` to *extract and store* qualitative statements (still no invention); surface them in `CompletenessResult.warnings`; **no downstream consumer yet**. This leaves ASAA, Architect, Geometry and Validator byte-identical and gives Phase 17 a typed input.
3. First measurable Phase 16 target: parser coverage on a new set of non-templated briefs (Phase 28 seed), reported separately from the frozen v1.0.0 benchmark.

---

## 19. Research Implications

| Claim | Supported by current evidence? |
|---|---|
| ASAA improves area fidelity and adjacency over a priority-blind strip baseline | **Weakly yes** (report table; 4 cases; weak baseline; downstream BUG-03/16 apply to both arms) |
| PlanForge always produces valid, complete layouts | **No**: validity is true by the validator's definition, but room counts are wrong for `count>1` and side setbacks are ignored |
| Refinement converges and reduces errors (RQ3) | **Not tested** (never triggered; orchestrator call broken) |
| Multi-design produces structurally diverse alternatives (RQ4) | **Not tested**; diversity is door-intent diversity on a shared allocation |
| An LLM contributes architectural reasoning | **No evidence**: every stored run uses a deterministic rule engine |
| System is reproducible | **Yes, trivially** (seed inert; rule-based); 2 cases × 3 runs |
| Explainability traces are non-fabricated | Plausible (source-tagged events) but trace metadata mislabels the mock model; `trace_entity_chain_completeness` is ill-defined |

Recommended: keep a **claims ledger** mapping each paper claim to a metric, a case set and a defect status; do not describe the system as "agentic", "adaptive" or "LLM-driven" beyond what §4 supports; report the mock/real distinction in every table.

---

## 20. Final Audit Conclusion and Acceptance Status

The architecture is sound as a **verifiable, deterministic scaffold** and is a good base for the roadmap: separation of concerns is largely real, hard validation is genuine and independent of the LLM, and ASAA's partition-score-refine loop is a workable seam. It is **not** yet an architectural reasoning system: intelligence-like behavior is concentrated in lookup tables, a procedural partitioner and a mock rule engine, and the representation, search, validator and benchmark all lack the dimensions in which architectural quality lives. In addition, two requirement-integrity defects (BUG-03, BUG-16) and several integration/metric defects mean that the stored 100% headline figures should not be cited without qualification.

### Acceptance checklist

| Criterion | Status |
|---|---|
| Entire repository inspected | ⚠️ **Partial** — see §0 for read/not-read lists |
| Current architecture verified from source | ✅ (for stages read) |
| ASAA deeply audited | ✅ |
| LLM path audited | ✅ (mock + provider code; no real-LLM run evidence) |
| Data contracts audited | ✅ (geometry/door/window/staircase models not read) |
| Geometry audited | ✅ (engine, room/polygon/wall/door/window/corridor/stair builders) |
| Validator audited | ⚠️ 7 of 10 sub-validators read |
| Refinement audited | ✅ |
| Diversity audited | ✅ |
| Benchmark system audited | ⚠️ benchmark/metrics/baseline + stored outputs read; ablation/runner/reproducibility code not read |
| Hardcoded knowledge inventoried | ✅ (31 items; `normalizer.py` content not read) |
| Decision ownership mapped | ✅ (static trace) |
| Bugs separated from limitations | ✅ |
| Protected invariants documented | ✅ |
| Limitation register | ✅ |
| Future upgrade map | ✅ |
| `docs/PHASE_15_CAPABILITY_AUDIT.md` | ✅ |
| `docs/phase15_capability_audit.json` | ✅ |
| `progress.md` updated | ✅ (inserted at top of the auto-generated snapshot; status is *not* "COMPLETE") |
| **Existing tests still pass** | ❌ **Not verified — tests were not executed** |
| No Phase 16+ implementation | ✅ no application, test, or frontend file was changed |
| No fabricated claims/results | ✅ (all numbers are from source or stored artifacts; HYP items labelled) |

**Phase 15 status: AUDIT DELIVERED — verification incomplete.** It may be promoted to COMPLETE after (a) running the commands below with all tests green and `git status` showing only the three documentation changes, and (b) optionally closing the unread-file gaps.

```bash
# from D:\23ALR060\Projects\Planforge
git status --short              # expect only docs/PHASE_15_*.md, docs/phase15_*.json, progress.md
python -m pytest -q
python -m pytest tests/unit/test_evaluation tests/integration/test_research_evaluation_runner.py -q
```

---

## Appendix A — Static trace of BUG-03 (for reproduction)

1. `ASAAAllocator._allocate_floor` → `SpatialPartitioner.partition` builds `count` `PartitionItem`s per `RoomSpec` (`id=f"{rs.id}_{idx}"`, all with `room_spec_id=rs.id`) ⇒ `count` `AllocatedRegion`s.
2. `ContextBuilder.build` loops `for room_spec in floor_spec.room_specs`, takes the first region with `reg.room_spec_id == room_spec.id` ⇒ **one** `RoomDesignContext` per spec.
3. `ArchitecturalOutputValidator.validate_and_parse` requires exactly the contexted `room_id`s.
4. `GeometryEngine.construct_floor` builds rooms from `floor_design.rooms` ⇒ one room per spec.
5. `RoomValidator.validate_floor` builds `expected_room_types` with one entry per `RoomSpec` ⇒ no mismatch reported.
6. Stored corroboration: `results/evaluation_run/benchmark_metrics.csv` `room_count_accuracy` per case (see §12.5).

**Minimal reproduction (not executed):** a brief with `2 bedrooms of 160 sq ft each`; assert `len([r for r in floor_plan.geometry.rooms if r.room_type == "bedroom"]) == 2`.

## Appendix B — Documentation vs implementation discrepancies

| # | Document claim | Implementation |
|---|---|---|
| 1 | Phase brief: "Pydantic/domain models" | Domain models are `@dataclass` |
| 2 | `ASAA.md §10`: orientation aligns social rooms toward preferred facade | Orientation unused; fixed `y ≤ mid_y` rule |
| 3 | `ASAA.md §18`: RNG explicitly seeded | RNG created and unused |
| 4 | `ASAA.md §5`: infeasibility includes min circulation | Excludes it |
| 5 | `ASAA.md §8`: required adjacency enforced | Soft score in ASAA; "Hard Constraint D" only warns |
| 6 | `ASAA.md §13`: stair 6–8 m² | Constant 8.0 |
| 7 | `ASAA.md §15`: `orientation_aligned` = solar/facing optimized | Only a room ordering; never run with default 3 candidates |
| 8 | `ASAA.md §7`: 100% containment *and* partition guarantees | Coverage not guaranteed (BUG-13 HYP) |
| 9 | `MULTI_DESIGN_DIVERSITY.md §4–5`: weights, thresholds, labels, Levenshtein | Different constants/labels/set-equality |
| 10 | `MULTI_DESIGN_DIVERSITY.md §4`: signature from "realized" doors | Built from **door intents** of the design set |
| 11 | `DEVELOPMENT_ROADMAP`: `OSCILLATION_DETECTED` status | Not in `RefinementStatus` (`REFINEMENT_FAILED`) |
| 12 | Roadmap/Validator docs: "18 check groups" | 13 `EVALUATED_CATEGORIES` |
| 13 | `README.md` links `ARCHITECTURAL_DESIGNER.md`, `EXPLAINABILITY_AND_TRACE.md` | Files are `LLM_ARCHITECTURAL_DESIGN.md`, `EXPLAINABILITY.md` |
| 14 | `completeness_gate` warning: municipal setbacks will be used | No default setbacks exist |
| 15 | Roadmap Phase 5: "13 architectural boundaries" in system prompt | 11 numbered invariants in prompt |
| 16 | Roadmap Phase 8: "LLM-driven corrections" | Default = keyword rules (mock) |
| 17 | Roadmap Phase 9: counts preserved in every alternative | BUG-03 |
| 18 | Report: Room Coverage 100% | `room_count_accuracy` 55.6–83.3 for 6 cases |

## Appendix C — Open questions (not resolved by this audit)

1. **Unexplained room count:** `case_05` reports `req_rooms_generated = 9` for 6 requested rooms and `room_count_accuracy = 100`. By §5/§8 only corridor-typed extras are excluded from accuracy, but the ≥3-spec corridor gate predicts none on 2-room floors. Needs inspection of the stored geometry for that run or a re-run.
2. Does `RequirementParser` + evaluation runner turn "L-shaped plot of 50 feet by 50 feet" into an L polygon anywhere (e.g. in `runner.py`)? Parser alone does not.
3. Do `DoorValidator`/`StaircaseValidator` perform any quality checks (not read)?
4. How does `DecisionTraceBuilder` label mock-vs-real LLM events?
5. Real-LLM behavior under `PLANFORGE_LLM_PROVIDER=huggingface` (tests/scripts exist; not read).
6. Whether any existing test covers `count > 1` end-to-end (test contents were not read).


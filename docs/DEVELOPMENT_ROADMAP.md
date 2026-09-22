# PlanForge AI — Development Roadmap

This document records the phased delivery milestones of the PlanForge AI architecture.

---

## Phase Status Summary

| Phase | Milestone | Status | Test Coverage | Description |
|---|---|---|---|---|
| **Phase 1** | Data Contracts & Foundation | **COMPLETE** | 75 passed | Core dataclasses, door/window intent vs geometry separation, ID generation, serialization, unit conversion. |
| **Phase 2** | Requirement System | **COMPLETE** | 158 passed | Deterministic requirement pipeline: Parser, Normalizer, Completeness Gate, Semantic Validator, Regression Safeguards. |
| **Phase 3** | Planning Agent | **COMPLETE** | 182 passed | Strategic spatial program (`PlanningSpec`), room categorization, priority calculation, 4-tier relationship graphs, circulation/entrance/stair intents. |
| **Phase 4** | ASAA (Adaptive Spatial Allocation) | **COMPLETE** | 218 passed | Partitioning buildable area into functional bounding regions (`AllocationSet`). |
| **Phase 5** | LLM Architectural Designer | **COMPLETE** | 242 passed | Proposing room shapes, door intents, window intents within allocated regions. |
| **Phase 6** | Geometry Engine | **COMPLETE** | 277 passed | Deterministic physical construction of GeoRoom (dual polygons), GeoWall, GeoDoor (swing arcs), GeoWindow, GeoStaircase, GeometrySet, and FloorPlanSet. |
| **Phase 7** | Validator | **COMPLETE** | 318 passed | Authoritative legal, geometric, and physical verification across 18 check groups (`ValidationReport`). |
| **Phase 8** | Refinement Agent | **COMPLETE** | 336 passed | LLM-driven architectural corrections based on validator feedback loop with oscillation and convergence controls. |
| **Phase 9** | Multi-Design Generation & Architectural Diversity | **COMPLETE** | 350 passed | Structural diversity engine (`DesignAlternativeSet`), 6 architectural strategies, `DesignSignature`, pairwise diversity distance, duplicate/near-duplicate filtering. |
| **Phase 10** | Explainability & Decision Trace | **COMPLETE** | 382 passed | Deterministic decision trace (`DecisionTrace`), multi-level human-readable explanations (`ExplanationRenderer`), unbroken room entity lifecycle linkage. |
| **Phase 11** | Export & Rendering | **COMPLETE** | 408 passed | Publication-grade PNG rendering (300 DPI), structured JSON, Markdown generation reports, standardized bundles, and integrity verification. |
| **Phase 12** | Orchestration & API | **COMPLETE** | 427 passed | End-to-end 10-stage execution pipeline, FastAPI REST API, process-local registry, and path traversal defense. |
| **Phase 13** | Research Validation & Benchmarking | **COMPLETE** | 442 passed | External evaluation subsystem: 16 benchmark cases, 20 metrics, baseline allocator, 3 ablations, reproducibility auditor, publication report & plots. |
| **Phase 14** | Web UI / Frontend Implementation | **COMPLETE** | 443 backend passed / 9 frontend passed | Interactive React 19 + Vite + TypeScript web interface: vector SVG canvas, room inspector, 8 research views, 16 benchmark presets, neutral alternatives matrix, direct export center. |

---

## Phase 14 Key Accomplishments
- Implemented a complete, modern, research-grade Web User Interface (`frontend/`) on top of the existing FastAPI backend without redesigning or duplicating any generation logic.
- Enforced strict core design invariants:
  - **Zero Generation Redesign**: Frontend contains zero placement, space allocation, constraint checking, or geometry calculations. The backend remains 100% authoritative.
  - **Zero Fabrication / Subjective Ranking**: Alternatives are displayed objectively in a factual matrix without synthetic "winner", "recommended", or artificial quality scores.
  - **Direct Geometry Consumption**: Interactive 2D vector SVG viewer directly draws `GeoRoom` polygons, `GeoWall` lines with structural thickness, `GeoDoor` swing arcs (90° quarter-circles), `GeoWindow` openings, and `GeoStaircase` treads with direction arrows from backend coordinates.
  - **Real-Time Pipeline Tracking**: Live execution feedback tracks true backend agent milestones with zero fake progress bars.
  - **Controlled Research Scope**: Strictly adhered to Phase 14 scope (no auth, no persistent database, no Phase 15 features).
- Built interactive SVG Floor Plan Canvas (`FloorPlanCanvas.tsx`):
  - Zoom and pan controls (0.4x to 3.0x), reset view, and responsive coordinate transforms.
  - Interactive room selection drawer (`RoomInspector.tsx`) showing exact bounding dimensions, daylight access, room type, aspect ratio, connected doors, validation errors/warnings, and entity traceability linkage.
  - Floor selection tabs (`FloorTabs.tsx`) for multi-floor structures.
  - Publication-grade toggle to 300 DPI high-resolution raster PNG view.
- Implemented 8 comprehensive research & operational views:
  - **Dashboard View**: Active projects list, status indicators, quick-start benchmark preset cards.
  - **New Project View**: Dual input interface (structured numeric parameters + natural language brief sync) and 1-click loading of all 16 research benchmark cases.
  - **Project Overview View**: Status summary, generation metrics, and interactive 10-stage execution timeline.
  - **Requirements View**: Program requirements broken down by spatial allocations and room specifications per floor.
  - **Alternatives View**: Neutral side-by-side design cards and comprehensive comparison matrix (area, room count, circulation ratio, aspect compliance, validation status).
  - **Validation View**: 18-category validator breakdown with hard errors vs. warnings separation, issue list, and affected room links.
  - **Explainability View**: Chronological stage decision timeline and per-room entity lifecycle traceability explorer.
  - **Refinement View**: Iteration-by-iteration error reduction tracking, convergence status, and granular change logs.
  - **Export View**: Download center for high-res PNG, vector SVG, structured JSON, markdown reports, and complete project ZIP bundle.
- Built-in static serving in FastAPI:
  - Added `GET /projects` and `GET /projects/{project_id}/data` endpoints to FastAPI.
  - Configured automatic static file mounting of `frontend/dist` at root `/` when built.
- Verification & Test Coverage:
  - 9 Vitest frontend tests passing across app rendering, canvas vector drawing, validation, alternatives, and export.
  - 443 backend pytest tests passing (0 failures, 100% passing across the entire repository).

- Implemented the complete, strictly external research evaluation and benchmarking subsystem (`app/evaluation/`) without modifying or redesigning upstream generation logic.
- Enforced core research invariants:
  - **Zero Generation Redesign**: Pipeline stages (`app/orchestration/`, `app/asaa/`, etc.) remain pure generation logic; evaluation is strictly an external observation and measurement layer.
  - **Zero Metric Fabrication**: Inapplicable metrics (e.g., staircase on single-floor plans, diversity on single-alternative runs) explicitly evaluate to `MetricValue.not_available()` with structured reasons.
  - **Scientific Baseline Comparison**: Built `BaselineSpatialAllocator`, a deterministic priority-blind proportional slice allocator that isolates the exact empirical value added by ASAA.
  - **Controlled Scientific Ablations**: Implemented `AblationStudyCoordinator` for ASAA vs Baseline (Ablation B), With vs Without Refinement (Ablation C), and Single vs Multi-Alternative Diversity (Ablation D).
  - **Deterministic Multi-Run Reproducibility**: Implemented `ReproducibilityAuditor` running multi-run stability checks across canonicalized stage fingerprints, guaranteeing 100% bitwise determinism under fixed random seeds.
  - **100% Offline & Headless**: Zero external network or database dependencies; headless Matplotlib Agg backend generating 300 DPI publication plots.
- Built comprehensive 16-case residential benchmark suite (`app/evaluation/benchmark.py`) spanning 11 categories:
  - Small/medium/large single-floor, 2-floor family, 3-floor townhouse, irregular L-plot, tight urban infill, multi-bedroom, attached suite, separation heavy, adjacency heavy, preferred relationships, staircase core, east orientation, feasibility edge, and infeasible deficit cases.
- Implemented `MetricCalculator` calculating 20 quantitative architectural metrics across 8 research categories:
  - Requirement adherence, Room count accuracy (MAE), Area satisfaction, Spatial allocation adjacency/separation/attachment compliance, Boundary & overlap satisfaction, Connectivity & circulation, Validation & Refinement error reduction, Multi-design structural diversity, Explainability trace completeness & fabrication safety, and Pipeline runtime.
- Built publication reporting & plotting engine (`app/evaluation/reporting.py`, `app/evaluation/plotting.py`):
  - `RESEARCH_EVALUATION_REPORT.md`: Comprehensive publication-ready markdown report.
  - Structured JSON outputs: `benchmark_results.json`, `metric_summary.json`, `ablation_results.json`, `reproducibility_results.json`.
  - Analytical CSV datasets: `benchmark_metrics.csv`, `ablation_metrics.csv`, `performance_metrics.csv`.
  - Publication figures: `constraint_compliance.png`, `refinement_error_reduction.png`, `asaa_vs_baseline_area.png`, `stage_runtimes.png`.
- Added standalone CLI runner (`scripts/run_evaluation.py`) with `--cases`, `--tags`, `--output-dir`, `--repro-runs`, and `--export-plots` flags.
- Complete test suite: 442 passed tests with 0 failures across the entire repository.

---

## Phase 12 Key Accomplishments
- Implemented the complete end-to-end execution pipeline in `app/orchestration/` and the synchronous REST API in `app/api/`.
- Enforced strict core architectural invariants:
  - **API is NOT the Architectural Engine**: Zero spatial allocation, geometry, validation, or diversity logic in `app/api/`.
  - **No Requirement Invention**: Incomplete briefs trigger `CompletenessGate` and stop immediately before planning or geometry.
  - **Neutral Presentation**: Alternatives are presented objectively with validation reports and diversity signatures without subjective "winner" or "best design" claims.
  - **Process-Local Storage Model**: Thread-safe in-memory cache `ProjectRegistry`; zero external database services (no Postgres, SQLite, Redis).
  - **Filesystem Security**: `resolve_safe_path` strictly prevents path traversal (`../`, absolute paths, null bytes) when downloading bundle artifacts.
  - **100% Offline & Injectable**: Fully injectable dependencies with deterministic `MockLLMClient` defaults.
- Built `PlanForgeOrchestrator` managing the 10-stage pipeline:
  - Requirements -> Planning -> ASAA -> Architectural LLM -> Geometry -> Validation -> Refinement -> Diversity -> Explainability -> Export & Rendering.
  - Granular lifecycle tracking (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `SKIPPED`, `PARTIAL`).
  - Graceful downstream skipping on stage failures with partial diagnostics.
- Implemented FastAPI REST routes mounted at `/api/v1` and root (`/`):
  - `GET /health`: Service health and LLM provider diagnostics.
  - `POST /generate`: Synchronous end-to-end floor plan generation.
  - `GET /projects/{id}`: High-level project summary and validation report.
  - `GET /projects/{id}/trace`: Multi-stage decision trace and entity lifecycles.
  - `GET /projects/{id}/alternatives`: Neutral design alternatives.
  - `GET /projects/{id}/export`: Secure download of generated bundles, PNG drawings, reports, and JSON schemas.
- Comprehensive test coverage: 427 tests passing across the entire repository (0 failures).

---

## Phase 11 Key Accomplishments
- Implemented the complete presentation, serialization, and publication subsystem across `app/rendering/` and `app/export/` without modifying upstream geometries or allocations.
- Enforced core architectural invariants:
  - **Direct Geometry Engine Consumption**: Renders physical `GeoRoom`, `GeoWall`, `GeoDoor` (swing arcs), `GeoWindow`, and `GeoStaircase` instances directly.
  - **Multi-Floor Physical Isolation**: Strictly generates discrete, independent drawings per floor (`floor_1.png`, `floor_2.png`, ...) — never merges floors into composite views.
  - **Zero Fabrication**: Orientation (north arrow) is drawn **only** when explicitly provided in requirements; dimensions reflect exact bounding metrics; missing rationales fall back transparently.
  - **Strictly Neutral Presentation**: Alternatives are presented neutrally without subjective ranking, single-winner selection, or "best design" claims.
  - **Truthful Validity Distinction**: Truthfully reports `VALID`, `INVALID`, and `VALID WITH WARNINGS` based strictly on `ValidationReport.overall_valid` (zero synthetic quality scores).
  - **Source Model Immutability**: All input data models remain 100% untouched.
  - **100% Offline & Deterministic**: Headless `matplotlib` (Agg backend), zero network calls, zero CAD framework dependencies.
- Built `FloorPlanRenderer` (alias `PlanForgeFloorPlanRenderer`) with:
  - High-resolution rendering (default 300 DPI).
  - Dual styling palettes: functional semantic pastel and paper-ready monochrome publication mode.
  - Safe label placement using Shapely `representative_point()`, preventing label clipping on non-convex/L-shaped rooms.
  - Configurable `RenderOptions` (DPI, dimensions, area labels, orientation, grid, walls, openings).
- Implemented `export_project_json` and `export_alternative_json` preserving 100% of entity traceability identifiers (`room_id`, `allocation_id`, `architectural_room_id`, `geo_room_id`, `validation_issue_id`, `change_id`, `alternative_id`).
- Implemented `generate_project_markdown_report` and `generate_alternative_markdown_report` for human-readable project summaries and alternative narratives.
- Built `BundleExporter` assembling standardized project packages (`outputs/<project_id>/`) with per-alternative directories, decision traces, room narratives, and optional ZIP archives (`<project_id>.zip`).
- Developed `verify_export_integrity` validating structural completeness, non-empty reports, parseable JSON schemas, and valid rendered images.
- 408 passing tests with 0 failures across unit, schema validation, multi-floor, boundary, and end-to-end integration suites.

---

## Phase 10 Key Accomplishments
- Implemented read-only, non-invasive `DecisionTrace` architecture in `app/explainability/` capturing every architectural decision and supporting factual evidence across all 9 pipeline stages (Requirement, Planning, ASAA Allocation, Architectural Design, Geometry Engine, Independent Validator, Refinement Loop, Diversity Generation, and Final Selection).
- Enforced strict core design invariants:
  - **Decisions and Evidence, NOT Chain-of-Thought**: Zero storage of model scratchpads, hidden deliberation, or internal token reasoning.
  - **Zero Fabrication**: Only facts and scores computed by pipeline algorithms are reported; missing rationales explicitly fall back to `"Rationale not provided"` without hallucination.
  - **Read-Only / Immutability**: Source models (`Requirements`, `PlanningSpec`, `AllocationSet`, `ArchitecturalDesignSet`, `FloorPlanSet`, `ValidationReport`, `RefinementResult`, `DesignAlternativeSet`) remain 100% untouched.
  - **Unbroken Entity Lifecycle Traceability**: `EntityTraceChain` links `source_requirement_id` -> `room_spec_id` -> `allocated_region_id` -> `architectural_room_id` -> `geo_room_id` -> `validation_issue_ids` -> `change_id`, queryable by any ID.
- Established standardized `DecisionEvent` contracts with 10 authoritative `ProvenanceSource` origins and 23 `DecisionType` classifications.
- Built `DecisionTraceBuilder` constructing linked traces from any combination of pipeline stage artifacts with robust fallback for partial pipeline runs.
- Implemented `ExplanationRenderer` generating deterministic human-readable explanations across 6 levels:
  - Project-level executive summary.
  - Alternative-level design narrative with strategy characteristics and diversity metrics.
  - Room-level lifecycle narrative tracing every transformation from user request to physical geometry.
  - Validation compliance report with structured expected vs. observed findings.
  - Iterative refinement progress report linking modifications directly to validation diagnostic issues.
  - Pairwise structural diversity comparison contrasting 5 topological features between alternatives.
- Full JSON serialization and deserialization (`to_dict`, `to_json`, `from_dict`, `from_json`, `model_dump`, `model_dump_json`).
- 382 passing tests across the full project test suite (including 32 dedicated unit and integration tests in `tests/unit/test_explainability/` and `tests/integration/test_explainability_trace.py`) with zero regressions and zero failures.

---

## Phase 9 Key Accomplishments
- Implemented `MultiDesignGenerator` synthesizing multiple verified, genuinely diverse residential floor plans (`DesignAlternativeSet`) for the same user brief and ASAA spatial allocation.
- Enforced strict architectural invariants: 100% room count, room identity, floor assignment, and minimum area preservation with ASAA allocation envelope immutability across all alternatives.
- Established 6 distinct architectural strategies: `social_centric`, `corridor_centric`, `compact_circulation`, `privacy_centric`, `open_social`, and `service_clustered`.
- Implemented canonical `DesignSignature` capturing structural topology: normalized adjacency graph edges, circulation type classification, entrance room type, social sequence, private clustering, vertical core access, semantic room shapes, and aspect ratio buckets.
- Built quantitative `calculate_diversity_distance` metric normalized to $[0.0, 1.0]$ with symmetry, identity, and weighted multi-attribute features ($w_{\text{adj}}=0.40, w_{\text{circ}}=0.20, w_{\text{ent}}=0.10, w_{\text{seq}}=0.10, \dots$).
- Enforced duplicate detection ($d == 0.0$) and near-duplicate rejection ($d < \tau_{\text{div}}$, default $0.15$), rejecting candidates with superficial jitter or window shifts while accepting structurally differentiated layouts.
- Integrated end-to-end with `FloorPlanValidator` and `RefinementLoop`, guaranteeing that all accepted alternatives are independently validated (`overall_valid == True`).
- Implemented structured candidate rejection logging with full audit trails (`SCHEMA_FAILURE`, `INVARIANT_VIOLATION`, `GEOMETRY_FAILURE`, `VALIDATION_FAILURE`, `DUPLICATE`, `INSUFFICIENT_DIVERSITY`).
- Maintained zero "best design" claims, presenting alternatives with design rationales, characteristics, validation reports, and pairwise diversity distance matrices.
- 350 passing tests with 0 failures across unit, multi-floor, boundary, and full multi-design generation integration suites.

---

## Phase 8 Key Accomplishments
- Implemented `RefinementAgent` and `RefinementLoop` providing validation-driven architectural corrections across an iterative pipeline (`Design → Geometry → Validator → Refinement → Geometry → Validator`).
- Formulated immutable `RefinementContext` and `RefinementContextBuilder` prioritizing errors before warnings and ordering diagnostics by architectural dependency hierarchy.
- Established `RefinementOutputValidator` enforcing 100% room preservation, ASAA allocation immutability, rejecting raw geometry output, and extracting granular `RefinementChange` records.
- Enforced strict zero direct physical geometry mutation: the agent only operates on `RoomDesign`, `DoorIntent`, and `WindowIntent`, delegating all physical construction to `GeometryEngine`.
- Enforced zero self-certification: the Independent Validator (`FloorPlanValidator`) remains the sole authority on floor plan validity across every iteration.
- Implemented robust termination guards: initial valid exit (`VALID_ON_INITIAL_PASS`), convergence exit (`CONVERGED`), canonical SHA-256 fingerprint oscillation detection (`OSCILLATION_DETECTED`), no-change detection (`REFINEMENT_FAILED`), and iteration limit (`MAX_ITERATIONS_REACHED`).
- Implemented comprehensive research audit records via `RefinementIterationRecord` and `RefinementResult`.
- 336 passing tests with 0 failures across unit, schema validation, multi-floor, boundary, and full iterative loop integration suites.

---

## Phase 7 Key Accomplishments
- Implemented `FloorPlanValidator` (and authoritative alias `Validator`) providing 100% deterministic, rule-based verification with zero LLM calls and zero geometry mutation.
- Built modular specialized validators:
  - `BoundaryValidator`: Zero-tolerance plot boundary containment and setback buildable boundary containment using Shapely polygon difference/contains.
  - `OverlapValidator`: Pairwise interior room collision and staircase overlap detection.
  - `RoomValidator`: Structural completeness, missing/unrequested room detection, floor assignment checking, ASAA allocation containment, and geometric topology/self-intersection.
  - `DimensionValidator`: Minimum area enforcement and target area deviation advisory warnings.
  - `RelationshipValidator`: Hard required adjacencies, soft preferred adjacencies, separation/avoidance constraints, and attached suites.
  - `DoorValidator`: Wall attachment verification (no floating doors), distance to wall line, door width vs. wall length, and swing arc clearance.
  - `WindowValidator`: Exterior wall placement, positive dimensions/sills, orientation matching, and interior partition placement prohibition.
  - `StaircaseValidator`: Staircase existence, riser/tread counts, core containment, and multi-floor vertical core alignment.
  - `ConnectivityValidator`: BFS door-graph reachability, isolated room detection, and entrance connectivity.
  - `CirculationValidator`: Corridor network validation and multi-floor floor count matching.
- Preserved strict stage boundaries: `GeometryEngine` produces unvalidated floor plans (`is_valid=False`, `validation=None`), and only `FloorPlanValidator` certifies validity (`is_valid=True/False`).
- Enforced hard vs. soft constraint discipline: errors invalidate the plan; soft warnings are tolerated without invalidation and are never marked as passed.
- 318 passing tests with 0 failures across unit, multi-floor, boundary, and full pipeline integration suites.

- Implemented `GeometryEngine` converting `ArchitecturalDesignSet` + `AllocationSet` into exact physical geometry: `GeoRoom`, `GeoWall`, `GeoDoor`, `GeoWindow`, `GeoStaircase`, `Geometry`, `GeometrySet`, and `FloorPlanSet`.
- Implemented `RoomBuilder` maintaining dual-polygon representation: clear interior `usable_polygon` (offset by half-wall thickness) and exterior wall boundary `built_polygon`.
- Implemented `PolygonBuilder` deterministically generating rectangular, square, and L-shaped room shapes within assigned ASAA allocated regions, with 90° orientation alignment support.
- Implemented `WallBuilder` deriving exterior and interior partition walls, deduplicating shared room boundaries, and generating 2D wall footprint polygons with configurable thickness ($t_{\text{ext}}=0.20$m, $t_{\text{int}}=0.15$m).
- Implemented `DoorBuilder` realizing `DoorIntent` (interior, entrance, balcony) onto matching physical walls, calculating exact opening positions and 90° circular swing arc polygons.
- Implemented `WindowBuilder` realizing `WindowIntent` onto exterior walls matching compass orientation with sill height specifications.
- Implemented `StaircaseBuilder` and `CorridorBuilder` generating vertical circulation with riser/tread parameters and circulation corridor geometry.
- Preserved true irregular and L-shaped polygonal boundaries without bounding-box substitution.
- Implemented `GeometryConstructionError` hierarchy for clean error propagation without architectural redesign.
- Enforced strict determinism: identical inputs produce bitwise-identical geometry coordinates.
- Preserved stage boundaries: `FloorPlan.is_valid=False` and `validation=None` (strictly leaving verification to Phase 7).
- 277 passing tests with 0 failures across unit, multi-floor, boundary, and full pipeline integration suites.

---

## Phase 5 Key Accomplishments
- Implemented `ArchitecturalAgent` transforming ASAA allocated spatial regions into structured architectural design proposals (`ArchitecturalDesignSet`).
- Created `ContextBuilder` mapping `PlanningSpec`, `AllocationSet`, and `Requirements` into an immutable `ArchitecturalContext`.
- Formulated `ARCHITECTURAL_SYSTEM_PROMPT` strictly enforcing 13 architectural boundaries (no geometry, no wall cutouts, no room invention, no floor shuffling).
- Enforced semantic shapes (`rectangular`, `square`, `l_shaped`) and positive dimension bounds within ASAA allocated region areas.
- Proposed `DoorIntent` (interior, entrance, attached suite) and `WindowIntent` (orientation, daylight, ventilation) without physical geometry.
- Built abstract `LLMClient` protocol with deterministic `MockLLMClient` (for offline, fast, repeatable testing) and `HuggingFaceClient` (for Hugging Face DeepSeek models).
- Implemented `ArchitecturalOutputValidator` with comprehensive schema validation: full room coverage, allocation reference integrity, and dimension bounds checks.
- 242 passing tests with 0 failures across unit, schema validation, multi-floor, boundary, and end-to-end integration suites.

---

## Phase 4 Key Accomplishments
- Implemented `ASAAAllocator` orchestrating the complete spatial allocation pipeline without generating final architectural geometry.
- Built `BuildableBoundaryCalculator` supporting rectangular, L-shaped, and irregular polygon plots with setback calculation without replacing polygons by bounding boxes.
- Developed `AreaBudgeter` with two-pass proportional allocation and explicit `InfeasibleAllocationError` detection preventing silent room dropping or area reductions.
- Implemented `SpatialPartitioner` using computational recursive bisection, guaranteeing 100% containment and zero overlap.
- Built `CandidateGenerator` exploring 4 architectural zoning strategies (`front_to_back`, `lateral`, `radial`, `orientation_aligned`) with deterministic seeds.
- Implemented `CandidateScorer` with clean separation of hard constraints from soft multi-objective scoring breakdowns.
- Built `AdaptiveRefiner` performing allocation-level room swaps and plateau detection.
- Coordinated multi-floor vertical staircase alignment (`staircase_aligned = True`) across single and multi-floor buildings.
- 218 passing tests with 0 failures across unit, boundary, regression, and pipeline integration suites.

---

## Phase 3 Key Accomplishments
- Implemented `PlanningAgent` transforming validated `Requirements` into `PlanningSpec`.
- Created `RoomCategorizer` mapping room types into functional architectural zones (`social`, `private`, `service`, `circulation`, `outdoor`, `other`).
- Implemented `PriorityCalculator` calculating explainable planning priorities (`high`, `normal`, `low`) with decision rationales.
- Built `RelationshipGraphBuilder` handling 4 relationship tiers (Required Adjacency, Preferred Adjacency, Avoid/Separation, Attached Room) with bidirectional symmetry and conflict resolution.
- Developed `CirculationPlanner` deriving circulation zones, entrance intent, and multi-floor vertical staircase connectivity intent without geometry.
- Enforced strict non-invention and architectural boundary invariants: no coordinates, polygons, walls, doors, or windows.
- Gated planning against incomplete requirements with `IncompleteRequirementsError`.
- 182 passing unit, boundary, and integration tests across the test suite.

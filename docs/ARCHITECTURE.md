# PlanForge — Architecture Reference

This document describes the authoritative responsibility boundaries of the
PlanForge seven-stage pipeline as established in Phase 1.

---

## Pipeline Overview

```
User Input / REST API Client
  ↓
Requirement Agent           → Requirements            (WHAT)
  ↓
Planning Agent              → PlanningSpec            (STRATEGY)
  ↓
ASAA (Spatial Allocator)    → AllocationSet           (WHERE)
  ↓
LLM Architectural Designer  → ArchitecturalDesignSet  (HOW)
  ↓
Geometry Engine             → GeometrySet             (CONSTRUCT)
  ↓
Validator                   → ValidationReport        (VERIFY)
  ↓
Refinement Agent            → Revised ArchitecturalDesignSet  (CORRECT)
  ↓
Diversity Generator         → DesignAlternativeSet    (DIVERSIFY)
  ↓
Explainability Engine       → DecisionTrace           (EXPLAIN)
  ↓
Export & Rendering          → ProjectBundleManifest   (PUBLISH)
  ↓
Orchestrator / REST API     → GenerationResponse      (SERVE)
```

---

## Stage Responsibilities

### 1. Requirement Agent → `Requirements`

**WHAT** does the user want?

- Parses and structures the user's plain-language brief.
- Records plot dimensions, plot polygon, orientation, setbacks.
- Records entrance facing direction and preferred entrance room type.
- Records the number of target floors.
- Records per-floor room requirements: type, count bounds, area bounds, adjacency, separation, attachments.
- Records staircase and circulation requirements at the floor level.
- Executes 6-stage deterministic pipeline: Input Parsing -> Structured Requirements -> Normalization -> Completeness Check -> Semantic Validation -> Planning Hand-off.
- Governed by CompletenessGate multi-floor gating: never invents rooms for unspecified floors.
- Full details documented in [docs/REQUIREMENT_SYSTEM.md](file:///D:/23ALR060/Projects/Planforge/docs/REQUIREMENT_SYSTEM.md).

**Must NOT contain:** Coordinates, final polygons, invented requirements, geometry.

---

### 2. Planning Agent → `PlanningSpec`

**STRATEGY:** How is the program organized?

- Preserves exact floor assignments and stable room identities (`source_requirement_id`).
- Assigns room categories (`social`, `private`, `service`, `circulation`, `outdoor`, `other`).
- Calculates explainable room priorities (`high`, `normal`, `low`) with decision rationales.
- Defines target areas and min/max area bounds per room.
- Constructs 4-tier relationship graphs: Required Adjacency, Preferred Adjacency, Avoid/Separation, and Attached Room links.
- Formulates circulation intent, entrance intent, and multi-floor staircase connectivity intent (as structured dicts).
- Full details documented in [docs/PLANNING_AGENT.md](file:///D:/23ALR060/Projects/Planforge/docs/PLANNING_AGENT.md).

**Must NOT contain:** Room polygons, wall coordinates, door swing geometry, spatial partitioning.

---

### 3. ASAA (Adaptive Space Allocation Algorithm) → `AllocationSet`

**WHERE** are functional spaces located?

- Computes setback-adjusted buildable boundary via `BuildableBoundaryCalculator` for rectangular, L-shaped, and irregular polygon plots without replacing polygons by bounding boxes.
- Enforces two-pass area budgeting via `AreaBudgeter` (minimums first + proportional priority-weighted remainder); raises structured `InfeasibleAllocationError` if requests exceed space.
- Performs computational 2D space-filling recursive bisection via `SpatialPartitioner` guaranteeing 100% containment and zero overlap between regions.
- Explores diverse multi-strategy candidates via `CandidateGenerator` (front-to-back, lateral, radial, orientation-aligned) with deterministic seeds.
- Scores candidates via `CandidateScorer` cleanly separating hard constraints from soft multi-objective score breakdowns.
- Applies allocation-level adaptive refinement via `AdaptiveRefiner` (room assignment swapping and plateau detection).
- Tracks and guarantees identical multi-floor vertical staircase alignment across all floors (`staircase_aligned = True`).
- Derives physical boundary contact adjacency IDs between neighboring regions.
- Full details documented in [docs/ASAA.md](file:///D:/23ALR060/Projects/Planforge/docs/ASAA.md).

**Must NOT contain:** Final wall offsets, wall thickness, door swing arcs, window openings, corridor geometry, staircase geometry, architectural detailing.

---

### 4. LLM Architectural Designer → `ArchitecturalDesignSet`

**HOW** are spaces shaped and connected?

- Transforms ASAA `AllocatedRegion` instances into structured architectural design proposals (`RoomDesign`, `ArchitecturalDesign`, `ArchitecturalDesignSet`).
- Formulates immutable `ArchitecturalContext` via `ContextBuilder` preserving user vs. system relationship provenance.
- Enforces semantic shapes (`rectangular`, `square`, `l_shaped`), avoiding arbitrary polygon coordinate generation.
- Formulates `DoorIntent` specifying connections between rooms, suites, and circulation zones (without swing arcs or wall cutouts).
- Formulates `WindowIntent` specifying daylight and ventilation orientations (without physical wall cutouts).
- Formulates `StaircaseIntent` linking multi-floor building levels to the locked ASAA vertical core.
- Enforces strict schema validation via `ArchitecturalOutputValidator` guaranteeing 100% room coverage, allocation reference integrity, and dimension feasibility within ASAA bounds.
- Backed by abstract `LLMClient` protocol with deterministic `MockLLMClient` for offline testing and `HuggingFaceClient` for Hugging Face DeepSeek models.
- Full details documented in [docs/LLM_ARCHITECTURAL_DESIGN.md](file:///D:/23ALR060/Projects/Planforge/docs/LLM_ARCHITECTURAL_DESIGN.md).

**Must NOT contain:** Deterministic wall buffering, wall thickness, exact coordinate snapping, door swing arcs, window openings, CAD entities, or geometry validation.

---

### 5. Geometry Engine → `GeometrySet`

**CONSTRUCT:** What is the physical built layout?

- Deterministically constructs `GeoWall`, `GeoDoor`, `GeoWindow`, `GeoStaircase`, `GeoRoom` via modular builders (`PolygonBuilder`, `RoomBuilder`, `WallBuilder`, `DoorBuilder`, `WindowBuilder`, `StaircaseBuilder`, `CorridorBuilder`, `GeometryEngine`).
- `GeoRoom` carries both `usable_polygon` (interior usable space buffered by half-wall thickness) and `built_polygon` (wall-centerline exterior footprint).
- `GeoWall` segments represent interior partitions and exterior walls, deduplicating shared room boundaries with thickness polygons ($t_{\text{ext}}=0.20$m, $t_{\text{int}}=0.15$m).
- `GeoDoor` carries exact wall placement and computed 90° swing arc polygon vertices.
- `GeoWindow` carries exact wall placement, orientation matching, width, height, and sill height.
- `GeoStaircase` carries full footprint polygon aligned across floors, riser count (16), and tread depth (0.28m).
- Preserves full upstream traceability (`architectural_room_id`, `intent_id`, `room_ids`).
- Supports irregular and L-shaped plots without bounding-box substitution.
- Emits structured `GeometryConstructionError` if proposals violate physical bounds; performs zero architectural redesign.
- Full details documented in [docs/GEOMETRY_ENGINE.md](file:///D:/23ALR060/Projects/Planforge/docs/GEOMETRY_ENGINE.md).

**Must NOT contain:** Architectural decisions, room relocation, validation scoring, or refinement loops.

---

### 6. Validator → `ValidationReport`

**VERIFY:** Is the layout legally and physically sound?

- Produces `ValidationResult` per floor with `checks_passed`, `checks_failed`, `checks_warned`.
- Produces `ValidationIssue` per finding with severity (`error`, `warning`, `info`).
- **Critical invariant:** `warning` severity does NOT mark a category as passed.
  Only explicit `record_passed_check()` calls can add to `checks_passed`.
  An `error` removes the category from `checks_passed` and adds it to `checks_failed`.
- Supports refinement iteration tracking via `iteration` counter on `ValidationReport`.

**Must NOT contain:** Modified geometry or design proposals.

---

### 7. Refinement Agent → Revised `ArchitecturalDesignSet`

**CORRECT:** How are validation issues resolved?

- Receives `ValidationReport` and original `ArchitecturalDesignSet`.
- Produces a modified `ArchitecturalDesignSet` with corrected proposals (doors, windows, dimensions, shapes).
- Changes are expressed at the architectural intent level — not by mutating `GeometrySet` directly.
- Orchestrated by `RefinementLoop` across iterations with oscillation detection, no-change detection, and `max_iterations` limits.
- Zero self-certification: only the Independent Validator certifies validity.
- Full details documented in [docs/REFINEMENT_AGENT.md](file:///D:/23ALR060/Projects/Planforge/docs/REFINEMENT_AGENT.md).

**Must NOT contain:** Directly mutated Shapely polygons or bypassed Geometry Engine calls.

---

### 8. Floor Plan → `FloorPlanSet`

**AGGREGATE:** Final validated deliverable.

- Pairs each floor's `Geometry` with its `ValidationResult` in a `FloorPlan`.
- Carries global `plot_boundary` and `buildable_boundary`.
- Carries aggregate `ValidationReport`.
- Carries `generation_metadata` for provenance.
- `all_valid` property is only `True` when every floor is valid.
- `total_usable_area` sums across all floors without mirroring Floor 1.

---

### 9. Event Log → `EventLog`

**AUDIT:** Why were decisions made?

- Every stage emits structured `Event` objects.
- Events carry: `stage`, `event_type`, `timestamp`, `message`, `data`, `metadata`, `execution_time_ms`.
- Filterable by stage and event type.

---

### 10. Explainability & Decision Trace → `DecisionTrace`

**EXPLAIN:** End-to-end evidence, provenance, and narrative generation.

- Observes the complete generation pipeline without mutating any upstream artifacts.
- Records structured `DecisionEvent` items across all 9 pipeline stages.
- Distinguishes authoritative `ProvenanceSource` (user, system, agents, algorithms).
- Preserves unbroken `EntityTraceChain` lifecycle linkage for every room across planning, allocation, design, geometry, validation, and refinement.
- Provides multi-level human-readable explanations via `ExplanationRenderer` (project, alternative, room narratives, validation findings, refinement history, pairwise diversity).
- Zero chain-of-thought storage; zero fabrication of missing facts or uncomputed scores.
- Full details documented in [docs/EXPLAINABILITY.md](file:///D:/23ALR060/Projects/Planforge/docs/EXPLAINABILITY.md).

---

### 11. Export & Rendering Subsystem → Visual & Data Packages

**PRESENT & SERIALIZE:** Publication-grade rendering, structured JSON, Markdown reporting, and self-verifying bundles.

- Consumes constructed `FloorPlanSet` and `DecisionTrace` downstream without modifying geometry or allocations.
- Renders publication-grade, high-resolution (300 DPI) floor plans using headless `matplotlib` (Agg backend) with pastel semantic or monochrome publication palettes.
- Strictly maintains multi-floor isolation ($N$ independent drawings for $N$ floors).
- Preserves 100% of entity traceability keys in structured JSON exports.
- Generates human-readable Markdown reports presenting design alternatives neutrally without subjective ranking or "winner" claims.
- Assembles standardized `outputs/<project_id>/` project bundles with per-alternative isolation and optional ZIP archives.
- Performs automated self-auditing through `verify_export_integrity`.
- Full details documented in [docs/EXPORT_AND_RENDERING.md](file:///D:/23ALR060/Projects/Planforge/docs/EXPORT_AND_RENDERING.md).

---

### 12. Orchestration Subsystem & REST API → `GenerationResponse`

**SERVE & COORDINATE:** How does the system execute deterministically end-to-end?

- Executes all 10 pipeline stages via `PlanForgeOrchestrator` with dependency injection.
- Enforces strict multi-floor completeness gating without room invention.
- Tracks granular stage lifecycle states (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `SKIPPED`, `PARTIAL`).
- Manages thread-safe process-local in-memory result caching in `ProjectRegistry`.
- Exposes synchronous FastAPI REST endpoints (`/health`, `/generate`, `/projects/{id}`, `/trace`, `/alternatives`, `/export`).
- Enforces strict path traversal defenses rejecting directory navigation tokens and absolute paths.
- Full details documented in [docs/ORCHESTRATION_AND_API.md](file:///D:/23ALR060/Projects/Planforge/docs/ORCHESTRATION_AND_API.md).

### 13. External Research Validation & Benchmarking → `ExperimentRun` (EVALUATE)

**EVALUATE:** How robust, compliant, and diverse are the generated floor plans?

- Strictly an **external evaluation subsystem** (`app/evaluation/`) operating outside the generation loop.
- Evaluates 20 quantitative architectural metrics across 8 research categories.
- Features a deterministic, priority-blind reference implementation (`BaselineSpatialAllocator`) to isolate ASAA's specific contributions.
- Coordinates controlled scientific ablations (ASAA vs Baseline, Refinement impact, Diversity scaling).
- Executes multi-run deterministic reproducibility audits verifying bitwise canonical stability.
- Generates publication-ready artifacts (`RESEARCH_EVALUATION_REPORT.md`, JSON/CSV metrics, and Matplotlib PNG figures).
- Full details documented in [docs/RESEARCH_EVALUATION.md](file:///D:/23ALR060/Projects/Planforge/docs/RESEARCH_EVALUATION.md).

---

## Architectural Intent vs. Constructed Geometry

PlanForge enforces a strict two-layer distinction:

| Intent Layer (Architectural LLM — HOW) | Geometry Layer (Geometry Engine — CONSTRUCT) |
|---|---|
| `DoorIntent` | `GeoDoor` |
| `WindowIntent` | `GeoWindow` |
| `StaircaseIntent` | `GeoStaircase` |
| `RoomDesign` (proposed boundary) | `GeoRoom` (usable + built polygon) |

Intent objects describe **what should exist** and **why**.
Geometry objects describe **what was constructed** and **exactly where**.

---

## Module Map

| Module | Primary Classes |
|---|---|
| `app.utils.ids` | `generate_id()` |
| `app.models.requirements` | `Requirements`, `FloorRequirement`, `RoomRequirement` |
| `app.models.planning` | `PlanningSpec`, `FloorPlanSpec`, `RoomSpec` |
| `app.models.allocation` | `AllocationSet`, `Allocation`, `AllocatedRegion` |
| `app.models.doors` | `DoorIntent` (alias: `DoorSpec`) |
| `app.models.windows` | `WindowIntent` (alias: `WindowSpec`) |
| `app.models.staircase` | `StaircaseIntent` (alias: `StaircaseSpec`) |
| `app.models.architectural_design` | `ArchitecturalDesignSet`, `ArchitecturalDesign`, `RoomDesign` |
| `app.models.geometry` | `GeometrySet`, `Geometry`, `GeoRoom`, `GeoWall`, `GeoDoor`, `GeoWindow`, `GeoStaircase` |
| `app.models.validation` | `ValidationReport`, `ValidationResult`, `ValidationIssue` |
| `app.models.refinement` | `RefinementStatus`, `RefinementChange`, `RefinementIterationRecord`, `RefinementResult` |
| `app.models.alternatives` | `DesignStrategy`, `AlternativeStatus`, `RejectionReason`, `DesignSignature`, `DesignAlternative`, `DesignAlternativeSet` |
| `app.models.floor_plan` | `FloorPlanSet`, `FloorPlan` |
| `app.models.events` | `EventLog`, `Event` |
| `app.validation` | `FloorPlanValidator`, `Validator`, `BoundaryValidator`, `OverlapValidator`, `RoomValidator`, `DimensionValidator`, `RelationshipValidator`, `DoorValidator`, `WindowValidator`, `StaircaseValidator`, `ConnectivityValidator`, `CirculationValidator` |
| `app.agents.refinement_agent` | `RefinementAgent`, `RefinementLoop`, `RefinementContext`, `RefinementContextBuilder`, `RefinementOutputValidator` |
| `app.agents.diversity_agent` | `MultiDesignGenerator`, `DesignSignatureBuilder`, `calculate_diversity_distance`, `is_duplicate`, `is_near_duplicate` |
| `app.explainability` | `DecisionTrace`, `DecisionEvent`, `StageTrace`, `EntityTraceChain`, `AlternativeTrace`, `DecisionTraceBuilder`, `ExplanationRenderer`, `TraceRecorder` |
| `app.rendering` | `FloorPlanRenderer`, `PlanForgeFloorPlanRenderer`, `RenderOptions`, `RenderedFloor` |
| `app.export` | `BundleExporter`, `export_project_bundle`, `export_project_json`, `export_alternative_json`, `generate_project_markdown_report`, `verify_export_integrity` |
| `app.orchestration` | `PlanForgeOrchestrator`, `OrchestrationConfig`, `PipelineState`, `PipelineResult`, `StageName`, `StageStatus`, `StageRecord` |
| `app.api` | `create_app`, `app`, `ProjectRegistry`, `GenerationRequest`, `GenerationResponse`, `resolve_safe_path` |
| `app.evaluation` | `BenchmarkRunner`, `BenchmarkRegistry`, `MetricCalculator`, `BaselineSpatialAllocator`, `AblationStudyCoordinator`, `ReproducibilityAuditor`, `MetricAggregator`, `EvaluationReporter`, `EvaluationPlotter` |

---

## Phase Status

| Phase | Status |
|---|---|
| Phase 1 — Data Contracts & Foundation Stabilization | ✅ Complete |
| Phase 2 — Requirement System | ✅ Complete |
| Phase 3 — Planning Agent | ✅ Complete |
| Phase 4 — ASAA (Adaptive Spatial Allocation Algorithm) | ✅ Complete |
| Phase 5 — LLM Architectural Designer | ✅ Complete |
| Phase 6 — Geometry Engine (Physical Construction) | ✅ Complete |
| Phase 7 — Validator (Deterministic Verification across 18 Check Groups) | ✅ Complete |
| Phase 8 — Refinement Agent (Validation-Driven Iterative Correction) | ✅ Complete |
| Phase 9 — Multi-Design Generation & Architectural Diversity | ✅ Complete |
| Phase 10 — Explainability & Decision Trace | ✅ Complete |
| Phase 11 — Export & Rendering (PNG / JSON / Markdown / Bundle) | ✅ Complete |
| Phase 12 — Orchestration & API | ✅ Complete |
| Phase 13 — Full-System Research Validation & Benchmarking | ✅ Complete |

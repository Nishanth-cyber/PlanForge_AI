# Phase 11 — Export & Rendering Subsystem

## 1. Overview & Architectural Role

The **Export & Rendering Subsystem** represents the presentation, serialization, and publication layer of the PlanForge AI research architecture. It consumes already constructed, validated, and refined floor-plan sets and decision traces, transforming them into:

1. **Publication-Grade Rendered Floor Plans (PNG)**: Headless, high-resolution (default 300 DPI) multi-floor images adhering strictly to architectural graphics conventions.
2. **Structured JSON Exports**: Complete, lossless JSON data representations preserving 100% of entity traceability identifiers across all pipeline stages.
3. **Comprehensive Markdown Generation Reports**: Human-readable, structured executive and detailed summaries with neutral multi-alternative presentations.
4. **Structured Multi-Level Explanations**: Trace-driven explanations covering project summaries, per-alternative strategies, room lifecycle narratives, validation findings, and pairwise diversity comparisons.
5. **Standardized Project Bundles**: Reproducible directory packages (`outputs/<project_id>/`) with per-alternative isolation, optional ZIP archives, and self-verifying structural integrity checks.

```
+-----------------------------------------------------------------------------------------------------------------------------------------+
|                                                      UPSTREAM PIPELINE OUTPUTS                                                          |
|  Requirements  ->  PlanningSpec  ->  AllocationSet  ->  ArchitecturalDesignSet  ->  FloorPlanSet  ->  ValidationReport  -> DecisionTrace  |
+-----------------------------------------------------------------------------------------------------------------------------------------+
                                                                     |
                                                                     v
                                                   +-----------------------------------+
                                                   |    Phase 11: Export & Rendering   |
                                                   +-----------------------------------+
                                                     |               |               |
                                                     v               v               v
                                            +----------------+ +-----------+ +---------------+
                                            | Floor Renderer | | JSON/Md   | | Bundle Export |
                                            | (matplotlib    | | Exporters | | & Integrity   |
                                            |  headless Agg) | |           | | Verifier      |
                                            +----------------+ +-----------+ +---------------+
                                                     |               |               |
                                                     v               v               v
                                            +------------------------------------------------+
                                            |         outputs/<project_id>/                  |
                                            |           project.json                         |
                                            |           summary.md                           |
                                            |           decision_trace.json                  |
                                            |           explanations/                        |
                                            |             project_summary.md                 |
                                            |             rooms/<room_id>.md                 |
                                            |           alternatives/                        |
                                            |             alternative_1/                     |
                                            |               floor_1.png                      |
                                            |               design.json                      |
                                            |               explanation.md                   |
                                            |           <project_id>.zip (optional)          |
                                            +------------------------------------------------+
```

---

## 2. Invariants & Strict Design Principles

The Export & Rendering subsystem adheres to seven non-negotiable architectural invariants:

1. **Presentation & Serialization Layer Only**:
   - The subsystem NEVER moves rooms, modifies wall alignments, recalculates ASAA allocations, alters door/window dimensions, or synthesizes geometry.
   - It is strictly a downstream consumer of constructed `FloorPlanSet` and `Geometry` instances.
2. **Direct Geometry Engine Consumption**:
   - Renders actual `GeoRoom`, `GeoWall`, `GeoDoor`, `GeoWindow`, and `GeoStaircase` objects produced by `GeometryEngine`.
   - Never draws approximate bounding boxes or unpartitioned ASAA regions.
3. **Multi-Floor Physical Isolation**:
   - Multi-floor projects with $N$ floors produce exactly $N$ independent, discrete floor drawings (`floor_1.png`, `floor_2.png`, ...).
   - Floors are never merged into a single ambiguous composite drawing.
4. **Zero Fabrication & Evidence-Based Annotation**:
   - Orientation (North Arrow) is rendered **only** when explicit orientation is provided in requirements. If `orientation is None`, no arrow is drawn.
   - Dimension annotations reflect exact bounding metrics without rounding inventions.
   - Missing rationales or descriptions fall back cleanly to transparent placeholders (`"Rationale not provided"`).
5. **Strictly Neutral Presentation**:
   - Design alternatives are presented neutrally without subjective ranking.
   - The system NEVER asserts a "best design", "winner", "optimal alternative", or "recommended layout".
6. **Validity State Fidelity**:
   - Explicitly and truthfully distinguishes `VALID`, `INVALID`, and `VALID WITH WARNINGS` based strictly on `ValidationReport.overall_valid` and issue severities.
   - Never fabricates synthetic "overall quality scores" to mask non-compliant designs.
7. **Source Model Immutability**:
   - All upstream models passed into renderers and exporters are treated as immutable and are never modified in place.
8. **100% Offline & Deterministic**:
   - Fully reproducible rendering and serialization with zero network calls, zero cloud dependencies, and zero heavy CAD framework dependencies.

---

## 3. Rendering Engine Architecture (`app/rendering/`)

### 3.1 Headless Matplotlib Backend
Rendering utilizes `matplotlib.figure.Figure` directly in headless mode (`Agg` backend), avoiding global GUI states and ensuring thread safety and performance across continuous integration and web environments.

### 3.2 Dual Styling Palettes
- **Standard Pastel Semantic Palette**: Functional zone-based coloring (social: `#D4E6F1`, private: `#D5F5E3`, service: `#FCF3CF`, circulation: `#F2F4F4`, outdoor: `#E8F8F5`, other: `#EAECEE`).
- **Publication Mode**: Clean monochrome/grayscale rendering with white fills, bold black wall outlines (`#111111`), hatching/subtle fills for circulation, and high-contrast typography optimized for black-and-white print papers.

### 3.3 Graphical Components
- **Exterior Walls**: Rendered with thickness proportional to `0.20m` wall width, clean `butt` cap styles, and dark charcoal stroke (`#1A252F` / `#000000`).
- **Interior Partition Walls**: Rendered with proportional `0.10m` wall width.
- **Doors**: Wall clearance opening with swing arcs indicating direction and clearance envelope.
- **Windows**: Wall opening with triple-line architectural convention (outer frame, inner glazing).
- **Staircases**: Tread lines, direction arrows ("UP"), and boundary enclosures.
- **Room Labels**: Centered safely inside room polygons using Shapely `representative_point()`, preventing label clipping on non-convex or L-shaped rooms.
- **Plot and Buildable Boundaries**: Dashed boundary lines distinguishing property limits (`#7F8C8D`) and municipal setbacks (`#95A5A6`).
- **North Arrow**: Drawn in the top-right corner with true geographic bearing only when orientation is explicitly provided.

### 3.4 Render Options (`RenderOptions`)
```python
@dataclass
class RenderOptions:
    dpi: int = 300
    figsize: Tuple[float, float] = (10.0, 10.0)
    publication_mode: bool = False
    show_room_ids: bool = False
    show_room_areas: bool = True
    show_dimensions: bool = True
    show_orientation: bool = True
    show_title: bool = True
    show_walls: bool = True
    show_doors: bool = True
    show_windows: bool = True
    show_staircases: bool = True
    show_corridors: bool = True
    show_grid: bool = False
    show_legend: bool = False
    margin_ratio: float = 0.08
```

---

## 4. Export Subsystem Architecture (`app/export/`)

### 4.1 JSON Exporter (`json_exporter.py`)
Serializes complete project pipelines into lossless, structured JSON dictionaries:
- Preserves 100% of entity traceability keys: `room_id`, `allocation_id`, `architectural_room_id`, `geo_room_id`, `validation_issue_id`, `change_id`, `alternative_id`.
- Robust recursive serialization handling dataclasses, Enums, NumPy types, Shapely geometries, and nested dictionaries.

### 4.2 Report Exporter (`report_exporter.py`)
Generates comprehensive human-readable Markdown generation reports (`summary.md` and per-alternative `explanation.md`):
- **Executive Summary**: Project name, plot dimensions, area, setbacks, orientation.
- **Planning & Strategy**: Programmed rooms per floor, functional category breakdown.
- **ASAA Spatial Allocation**: Regional space allocations, circulation budgets.
- **Independent Validation Status**: Truthful disclosure of `VALID`, `INVALID`, or `VALID WITH WARNINGS` with specific rule violations and severities.
- **Iterative Refinement Trajectory**: Applied modifications, targeted issue resolutions.
- **Multi-Design Exploration**: Tabular and narrative summaries of alternatives with pairwise structural diversity distances and zero subjective winner claims.
- **Explainability Integration**: Automated inclusion of DecisionTrace project summaries and room lifecycle narratives.

### 4.3 Bundle Exporter (`bundle_exporter.py`)
Assembles complete project directories according to the standard project layout:
```
outputs/<project_id>/
├── project.json
├── summary.md
├── decision_trace.json (if available)
├── explanations/
│   ├── project_summary.md
│   └── rooms/
│       ├── room_living_1.md
│       └── room_kitchen_1.md
├── alternatives/
│   ├── alternative_1/
│   │   ├── floor_1.png
│   │   ├── design.json
│   │   └── explanation.md
│   └── alternative_2/
│       ├── floor_1.png
│       ├── design.json
│       └── explanation.md
└── <project_id>.zip (optional)
```

### 4.4 Integrity Verification (`integrity.py`)
Automated self-auditing utility (`verify_export_integrity`):
- Verifies directory existence and structural completeness.
- Validates syntax and essential metadata in `project.json` and `design.json`.
- Confirms non-empty Markdown reports and valid rendered floor images.
- Returns detailed `ExportIntegrityReport` with errors, warnings, and verified file lists.

---

## 5. Verification & Test Suite

The Phase 11 subsystem is verified by a dedicated test suite:
- `tests/unit/test_rendering/test_floor_plan_renderer.py`: 8 unit tests covering single-floor, multi-floor, irregular plots, publication monochrome mode, orientation presence vs. absence, rendering immutability, deterministic reproducibility, and error handling.
- `tests/unit/test_export/test_json_exporter.py`: 5 unit tests covering ID preservation, alternative serialization, optional field tolerance, immutability, and error handling.
- `tests/unit/test_export/test_report_exporter.py`: 5 unit tests covering report structure, neutral multi-alternative presentation, validation status distinction, invalid candidate preservation, and alternative report generation.
- `tests/unit/test_export/test_bundle_exporter.py`: 5 unit tests covering directory hierarchy creation, multi-floor isolation, ZIP archiving, integrity verification, and input immutability.
- `tests/integration/test_export_and_rendering_pipeline.py`: 3 end-to-end integration tests verifying complete pipeline execution from user briefs to exported bundles, multi-design alternatives, and publication mode rendering.

**Full Repository Test Status:**
- Total tests: **408 passed, 0 failed** in ~10 seconds.

# PlanForge AI — Research Evaluation & Benchmarking Methodology

This document specifies the research evaluation framework, benchmark cases, quantitative metrics, baseline comparisons, controlled ablations, reproducibility protocol, empirical findings, and limitations for PlanForge AI: *“Agentic AI Framework for Intelligent Residential Floor Plan Generation Using Adaptive Space Allocation Algorithm (ASAA)”*.

---

## 1. Experimental Setup & Architecture Invariants

### 1.1 Architectural Separation of Concerns
The PlanForge AI architecture enforces a strict invariant separation across stages:
- **Requirement Agent (`WHAT`):** Normalizes natural language briefs into structured, unit-standardized requirements.
- **Planning Agent (`ORGANIZE`):** Formulates topological specifications, room priorities, adjacency graphs, and vertical staircase coordination.
- **ASAA (`WHERE`):** Deterministically partitions buildable space into candidate macro-spatial allocation regions. ASAA determines *where* functional zones reside; it does *not* draft physical walls or doors.
- **Architectural Design LLM (`HOW`):** Proposes room-level dimensions, aspects, and opening intents strictly within allocated regions.
- **Geometry Engine (`CONSTRUCT`):** Deterministically constructs 2D polygonal room boundaries, walls, doors, windows, and staircases.
- **Independent Validator (`VERIFY`):** Authoritative arbiter of building codes, boundary containment, overlap, and connectivity.
- **Refinement Agent (`CORRECT`):** Revises architectural intents using structured validation feedback without mutating upstream requirements or ASAA allocations.

### 1.2 Evaluation Environment
- **Platform:** Python 3.14 on Windows (win32)
- **Harness:** Deterministic offline evaluation runner (`app/evaluation/runner.py`)
- **LLM Configuration:** `MockLLMClient` with deterministic rule-based architectural proposal synthesis (enables offline reproducibility without live API quota or non-deterministic sampling noise).
- **Execution Seed:** Fixed seed (`42`) across all trials.

---

## 2. Benchmark Case Dataset

The benchmark suite consists of 16 canonical residential architectural design briefs categorized into 11 benchmark tags:

| Case ID | Name | Category Tag | Floors | Target Area ($m^2$) | Key Architectural Challenges |
|---|---|---|:---:|:---:|---|
| `case_01_small_single_floor` | Small Single-Floor Bungalow | `SINGLE_FLOOR` | 1 | 50.17 | Compact layout, setback clearances, open living-dining |
| `case_02_medium_single_floor` | Medium Single-Floor Suburban Residence | `SINGLE_FLOOR` | 1 | 89.19 | Master suite, kitchen work triangle, guest bath |
| `case_03_large_single_floor` | Large Single-Floor Estate Villa | `SINGLE_FLOOR` | 1 | 148.64 | Extensive footprint, study, formal dining, multi-zone HVAC |
| `case_04_two_floor_family` | Two-Floor Family Residence | `MULTI_FLOOR`, `STAIRCASE` | 2 | 87.79 | Vertical staircase alignment, private upstairs zoning |
| `case_05_three_floor_townhouse` | Three-Floor Urban Townhouse | `MULTI_FLOOR`, `STAIRCASE`, `TIGHT_SPACE` | 3 | 81.75 | Vertical stacking, ground entry, roof terrace access |
| `case_06_irregular_l_plot` | Irregular L-Shaped Boundary Residence | `SINGLE_FLOOR`, `IRREGULAR_PLOT` | 1 | 67.35 | Non-convex boundary, setback polygon computation |
| `case_07_tight_urban` | Constrained Narrow Urban Infill | `SINGLE_FLOOR`, `TIGHT_SPACE` | 1 | 42.27 | High setback-to-width ratio, linear corridor circulation |
| `case_08_multi_bedroom` | Four-Bedroom Extended Family Layout | `SINGLE_FLOOR` | 1 | 118.92 | Multiple bedroom clustering, social separation |
| `case_09_attached_suite` | Master Bedroom Attached Suite | `SINGLE_FLOOR`, `ATTACHED_SUITE` | 1 | 67.35 | Direct bedroom-to-bathroom ensuite adjacency coupling |
| `case_10_separation_heavy` | Separation Heavy Acoustic Layout | `SINGLE_FLOOR`, `SEPARATION_HEAVY` | 1 | 70.61 | Living room acoustically isolated from bedrooms |
| `case_11_adjacency_heavy` | Adjacency Heavy Social Flow | `SINGLE_FLOOR`, `ADJACENCY_HEAVY` | 1 | 73.86 | Kitchen-dining-living continuous open circulation |
| `case_12_preferred_relationships` | Preferred Relationship Flexible Program | `SINGLE_FLOOR` | 1 | 86.40 | Soft advisory relations vs hard geometric constraints |
| `case_13_staircase_core` | Multi-Level Vertical Staircase Coordination | `MULTI_FLOOR`, `STAIRCASE` | 2 | 83.61 | Stairwell footprint reservation and identical $(x, y)$ core |
| `case_14_orientation_east` | East-Facing Solar & Entrance Orientation | `SINGLE_FLOOR`, `ORIENTATION` | 1 | 70.14 | Morning daylighting, east facade entrance intent |
| `case_15_feasibility_edge` | High-Density Feasibility Edge Case | `SINGLE_FLOOR`, `FEASIBILITY_EDGE_CASE`, `TIGHT_SPACE` | 1 | 59.46 | Near 100% buildable area utilization stress test |
| `case_16_infeasible_deficit` | Infeasible Room Deficit Program | `SINGLE_FLOOR`, `INFEASIBLE` | 1 | 153.29 | Intentional negative control: 153.3 m² requested in 12.8 m² buildable plot |

All cases are deterministically defined in `app/evaluation/benchmark.py`.

---

## 3. Authoritative Metric Definitions & Classification

All 20 metrics are computed by `app.evaluation.metrics.MetricCalculator` from canonical pipeline artifacts:

| # | Metric Name | Formulation / Definition | Unit | Aggregation | Type | Direction | Ground Truth Source |
|:--|:---|:---|:---:|:---:|:---:|:---:|:---|
| 1 | `req_room_coverage` | $\frac{N_{\text{matched\_rooms}}}{N_{\text{req\_rooms}}} \times 100\%$ | % | Mean | Hard | Higher | Parsed `Requirements` |
| 2 | `room_count_accuracy` | $\max\left(0, 1 - \frac{\sum |N_{\text{req}} - N_{\text{gen}}|}{\sum N_{\text{req}}}\right) \times 100\%$ | % | Mean | Hard | Higher | Parsed `Requirements` |
| 3 | `area_min_compliance` | $\frac{N(\text{usable\_area} \ge \text{min\_area} - 0.1)}{N_{\text{total\_rooms}}} \times 100\%$ | % | Mean | Hard | Higher | `PlanningSpec.min_area_sqm` |
| 4 | `area_preferred_mae` | $\frac{1}{N} \sum |\text{usable\_area}_i - \text{target\_area}_i|$ | $\text{m}^2$ | Mean | Soft | Lower | User target areas |
| 5 | `allocation_adjacency_compliance` | $\frac{N_{\text{satisfied\_adj\_pairs}}}{N_{\text{total\_adj\_pairs}}} \times 100\%$ | % | Mean | Soft/Hard | Higher | `PlanningSpec.adjacency_matrix` |
| 6 | `separation_compliance` | $\frac{N_{\text{disjoint\_avoid\_pairs}}}{N_{\text{total\_avoid\_pairs}}} \times 100\%$ | % | Mean | Soft/Hard | Higher | `PlanningSpec.avoid_matrix` |
| 7 | `attached_suite_compliance` | $\frac{N_{\text{attached\_pairs\_adjacent}}}{N_{\text{total\_attached\_pairs}}} \times 100\%$ | % | Mean | Hard | Higher | `attached_to_room_id` |
| 8 | `boundary_compliance` | $100\%$ if all rooms $\subset \text{BuildableBoundary}$; else $0\%$ | % | Mean | Hard | Higher | Setback polygon |
| 9 | `overlap_free` | Boolean: $\text{IntersectionArea}(r_i, r_j) \le 0.01\,\text{m}^2 \quad \forall i \ne j$ | Bool | Rate | Hard | Higher | Shapely intersection |
| 10 | `connectivity_rate` | $\frac{N_{\text{rooms\_reachable\_from\_entrance}}}{N_{\text{total\_rooms}}} \times 100\%$ | % | Mean | Hard | Higher | Door circulation graph |
| 11 | `door_alignment_rate` | $\frac{N_{\text{doors\_on\_shared\_wall}}}{N_{\text{total\_doors}}} \times 100\%$ | % | Mean | Hard | Higher | Wall geometry |
| 12 | `window_exterior_rate` | $\frac{N_{\text{windows\_on\_exterior\_wall}}}{N_{\text{total\_windows}}} \times 100\%$ | % | Mean | Hard | Higher | Building envelope |
| 13 | `staircase_compliance` | Vertical core alignment across multi-floor programs | % | Mean | Hard | Higher | Multi-floor stair bounds |
| 14 | `validation_success` | Independent validator certification: zero hard errors | Bool | Rate | Hard | Higher | `ValidationReport.overall_valid` |
| 15 | `refinement_error_reduction` | Initial hard errors $-$ Final hard errors | count | Sum/Mean | Dynamic | Higher | `RefinementResult.iterations` |
| 16 | `diversity_mean_distance` | Mean pairwise Jaccard topological graph distance | $[0, 1]$ | Mean | Metric | Higher | Alternative graph signatures |
| 17 | `alternative_validity_rate` | $\frac{N_{\text{valid\_alternatives}}}{N_{\text{generated\_alternatives}}} \times 100\%$ | % | Mean | Hard | Higher | Validator certification |
| 18 | `trace_stage_coverage` | $\frac{N_{\text{logged\_stages}}}{N_{\text{total\_stages}}} \times 100\%$ | % | Mean | Audit | Higher | `DecisionTrace.stages` |
| 19 | `trace_no_fabrication_audit` | Boolean: zero synthetic CoT or scratchpad leakage | Bool | Rate | Audit | Higher | Trace audit gate |
| 20 | `pipeline_runtime_ms` | Total end-to-end wall-clock latency | ms | Mean | Perf | Lower | Process timer |

### Constraint Semantics
- **Hard Constraints:** Must be strictly satisfied for a design to be certified valid (`boundary_compliance`, `overlap_free`, `req_room_coverage`, `attached_suite_compliance`, `connectivity_rate`, `staircase_compliance`).
- **Soft Preferences:** Optimization objectives that guide spatial positioning and room sizing (`area_preferred_mae`, advisory adjacency flow, daylight orientation, diversity distance).

---

## 4. Controlled Baseline Allocator

`BaselineSpatialAllocator` (`app/evaluation/baselines.py`) provides an independent, deterministic reference implementation:
1. Derives identical buildable boundaries from `PlanningSpec` setbacks using `BuildableBoundaryCalculator`.
2. Reserves vertical circulation core for multi-floor programs.
3. Slices remaining buildable space proportionally along the primary axis in sequential room order, priority-blind.
4. Does **not** perform 2D orthogonal tree bisection, multi-candidate generation, relational force scoring, or boundary refinement.
5. Evaluated via the exact same `MetricCalculator` and `Validator`.

---

## 5. Controlled Ablation Results

### 5.1 Ablation B: ASAA vs. Baseline Spatial Allocator
Evaluated across canonical representative cases (`case_01`, `case_02`, `case_04`, `case_09`):

| Case ID | Metric | ASAA | Baseline | Delta | Geometry Evidence / Findings |
|---|---|:---:|:---:|:---:|---|
| `case_01_small_single_floor` | Quality Score <br> Area MAE <br> Warnings <br> Adjacency | **91.0** <br> **2.81 m²** <br> **3** <br> **100%** | 79.0 <br> 10.94 m² <br> 7 <br> 100% | **+12.0** <br> **-8.13 m²** <br> **-4** <br> 0.0% | Compact single-floor bungalow; ASAA reduces area error by 8.13 m². |
| `case_02_medium_single_floor` | Quality Score <br> Area MAE <br> Warnings <br> Adjacency | **91.0** <br> **2.75 m²** <br> **3** <br> **100%** | 76.0 <br> 17.09 m² <br> 8 <br> 100% | **+15.0** <br> **-14.34 m²** <br> **-5** <br> 0.0% | Suburban home; ASAA reduces area MAE by 14.34 m² and eliminates 5 warnings. |
| `case_04_two_floor_family` | Quality Score <br> Area MAE <br> Warnings <br> Adjacency | **92.5** <br> **12.90 m²** <br> **5** <br> **100%** | 89.5 <br> 24.05 m² <br> 7 <br> 100% | **+3.0** <br> **-11.15 m²** <br> **-2** <br> 0.0% | Multi-floor residence; both align staircase, but ASAA reduces area MAE by 11.15 m². |
| `case_09_attached_suite` | Quality Score <br> Area MAE <br> Warnings <br> **Adjacency** | **76.0** <br> **5.85 m²** <br> **8** <br> **100.0%** | 70.0 <br> 8.36 m² <br> 10 <br> **33.3%** | **+6.0** <br> **-2.51 m²** <br> **-2** <br> **+66.7%** | **Key Adjacency Defect in Baseline:** 1D slicing isolated Dining at slice 5, failing contact with Living (slice 1) and Kitchen (slice 2). ASAA 2D partitioning maintained 100% adjacency. |

### 5.2 Adjacency Audit Across All Cases
- Total required adjacency pairs across all benchmark programs: **37**
- ASAA compliance: **37 / 37 (100.0%)**
- Baseline compliance: **35 / 37 (94.6%)** (failed 2 pairs in `case_09` due to 1D topological ordering).

---

## 6. Deterministic Reproducibility Audit

`ReproducibilityAuditor` executed repeated runs ($N=3$) per benchmark case under fixed seed ($42$):
- Canonicalized stage outputs across: `REQUIREMENTS`, `PLANNING`, `ASAA`, `GEOMETRY`, `VALIDATION`.
- Stripped volatile execution metadata (timestamps, UUIDs).
- **Result:** $100\%$ deterministic canonical fingerprint stability across all stages.
- **Scientific Claim:** *"Deterministic canonical fingerprint reproducibility"* (byte-for-byte identical canonical representations across runs).

---

## 7. Failure Case & Limitations Analysis

### 7.1 Negative Control Case 16
- **Case:** `case_16_infeasible_deficit`
- **Specification:** 153.3 m² requested room area on a 20×20 ft plot with 2m setbacks (buildable area = 12.8 m²).
- **Observed Behavior:** Correctly caught by `AreaBudgeter` feasibility gate with `InfeasibleAllocationError` (deficit of 109.9 m²). Pipeline status recorded as `failed` / `infeasible_brief`.
- **Classification:** **Requirement Stage** infeasibility gating.

### 7.2 Advisory Warnings Analysis
- 15/15 feasible cases achieved **0 hard errors** and were certified `overall_valid: true`.
- Feasible cases averaged 4.6 advisory warnings (primarily daylighting openings in secondary bathrooms or compact corridor aspect ratios).

### 7.3 Research Limitations
1. **Sample Size ($N=16$):** The 16 canonical benchmark cases represent standard residential typologies but do not constitute a statistically large population for parametric hypothesis testing (e.g. ANOVA).
2. **Offline Mock Environment:** Latencies reported reflect local deterministic execution (`~150–250 ms`), not live cloud LLM network round-trip time.
3. **Rectilinear Architectural Focus:** Current geometry builders prioritize orthogonal and rectilinear room envelopes.

---

## 8. Reproduction Instructions

To reproduce all experimental results, tables, and plots from a clean environment:

```bash
# Execute complete benchmark suite, ablations, and reproducibility audit
python scripts/run_evaluation.py --output-dir results/evaluation_run

# Verify evaluation unit tests
python -m pytest tests/unit/test_evaluation/ -v
```

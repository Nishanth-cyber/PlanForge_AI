# PlanForge AI — Research Evaluation & Benchmarking Report

**System Under Evaluation:** *Agentic AI Framework for Intelligent Residential Floor Plan Generation Using Adaptive Space Allocation Algorithm (ASAA)*
**Run ID:** `eval_run_66ba99354301`  
**Timestamp:** `2026-09-20T14:36:06.793290+00:00`  

---

## 1. Executive Summary & Research Questions

This report documents the rigorous experimental validation of PlanForge AI across 16 canonical residential benchmark cases covering diverse geometric scales, multi-floor programs, non-convex plot boundaries, tight constraints, acoustic separations, and infeasibility stress tests.

### Research Questions Investigated
- **RQ1 (ASAA Spatial Allocation):** Does ASAA improve constraint-aware spatial allocation and preferred-area compliance compared to a deterministic priority-blind baseline?
- **RQ2 (Requirement Adherence):** How accurately does the system interpret user briefs without room fabrication or omissions?
- **RQ3 (Refinement Convergence):** How effectively does the validation-driven refinement loop eliminate initial physical and geometric errors?
- **RQ4 (Structural Diversity):** Can the multi-design generator produce structurally divergent alternatives without compromising validity?
- **RQ5 (Explainability & Reproducibility):** Are decision traces complete, evidence-grounded, and deterministically reproducible under identical seeds?

---

## 2. Benchmark Dataset Summary

- **Total Cases Evaluated:** 16
- **Successful Pipeline Executions:** 15
- **Overall Valid Plans Rate:** 15 / 16 (excluding expected infeasible cases)

| Case ID | Name | Difficulty | Status | Valid | Room Coverage | Preferred Area MAE |
|---|---|---|---|---|---:|---:|
| `case_01_small_single_floor` | Small Single-Floor Bungalow | SINGLE_FLOOR | `completed` | ✅ VALID | 100.0% | 2.81 m² |
| `case_02_medium_single_floor` | Medium Single-Floor Suburban Residence | SINGLE_FLOOR | `completed` | ✅ VALID | 100.0% | 2.75 m² |
| `case_03_large_single_floor` | Large Single-Floor Estate Villa | SINGLE_FLOOR | `completed` | ✅ VALID | 100.0% | 12.23 m² |
| `case_04_two_floor_family` | Two-Floor Family Residence | MULTI_FLOOR | `completed` | ✅ VALID | 100.0% | 12.9 m² |
| `case_05_three_floor_townhouse` | Three-Floor Urban Townhouse | MULTI_FLOOR | `completed` | ✅ VALID | 100.0% | 4.89 m² |
| `case_06_irregular_l_plot` | Irregular L-Shaped Boundary Residence | SINGLE_FLOOR | `completed` | ✅ VALID | 100.0% | 1.64 m² |
| `case_07_tight_urban` | Constrained Narrow Urban Infill | SINGLE_FLOOR | `completed` | ✅ VALID | 100.0% | 3.79 m² |
| `case_08_multi_bedroom` | Four-Bedroom Extended Family Layout | SINGLE_FLOOR | `completed` | ✅ VALID | 100.0% | 21.53 m² |
| `case_09_attached_suite` | Master Bedroom Attached Suite | SINGLE_FLOOR | `completed` | ✅ VALID | 100.0% | 5.85 m² |
| `case_10_separation_heavy` | Separation Heavy Acoustic Layout | SINGLE_FLOOR | `completed` | ✅ VALID | 100.0% | 1.44 m² |
| `case_11_adjacency_heavy` | Adjacency Heavy Social Flow | SINGLE_FLOOR | `completed` | ✅ VALID | 100.0% | 5.15 m² |
| `case_12_preferred_relationships` | Preferred Relationship Flexible Program | SINGLE_FLOOR | `completed` | ✅ VALID | 100.0% | 4.76 m² |
| `case_13_staircase_core` | Multi-Level Vertical Staircase Coordination | MULTI_FLOOR | `completed` | ✅ VALID | 100.0% | 10.54 m² |
| `case_14_orientation_east` | East-Facing Solar & Entrance Orientation | SINGLE_FLOOR | `completed` | ✅ VALID | 100.0% | 3.09 m² |
| `case_15_feasibility_edge` | High-Density Feasibility Edge Case | SINGLE_FLOOR | `completed` | ✅ VALID | 100.0% | 5.4 m² |
| `case_16_infeasible_deficit` | Infeasible Room Deficit Program | SINGLE_FLOOR | `failed` | ⚠️ INVALID / INFEASIBLE | N/A | N/A |

---

## 3. Requirement Adherence & Geometric Validity

PlanForge enforces zero room fabrication and strict completeness gating.

| Metric | Mean Value | Unit | Description |
|---|---:|---|---|
| Room Coverage | 100.0 | % | Requested vs constructed rooms ratio |
| Minimum Area Compliance | 90.0 | % | Rooms meeting hard minimum area limits |
| Preferred Area Deviation (MAE) | 6.58 | m² | Mean absolute error from user target area |
| Allocation Adjacency Satisfaction | 100.0 | % | Required relationship satisfaction in allocation |
| Boundary Compliance | 100.0 | % | Rooms contained within legal buildable boundaries |
| Circulation & Connectivity | 100.0 | % | Rooms accessible from entrance circulation graph |

---

## 4. Controlled Ablation Studies

### Ablation A vs B: ASAA vs. Baseline Spatial Allocator

A controlled comparison isolating the contribution of ASAA by substituting a deterministic, priority-blind proportional slice allocator (`BaselineSpatialAllocator`) while keeping downstream Architectural LLM, Geometry Engine, and Validator 100% constant.

| Benchmark Case | Full PlanForge (ASAA) MAE | Baseline Allocator MAE | Area MAE Delta | ASAA Adjacency % | Baseline Adjacency % |
|---|---:|---:|---:|---:|---:|
| `case_01_small_single_floor` | 2.81 | 10.94 | -8.13 | 100.0% | 66.7% |
| `case_02_medium_single_floor` | 2.75 | 17.09 | -14.34 | 100.0% | 66.7% |
| `case_04_two_floor_family` | 12.9 | 24.05 | -11.15 | 100.0% | 66.7% |
| `case_09_attached_suite` | 5.85 | 8.36 | -2.51 | 100.0% | 66.7% |

### Ablation C: Refinement Loop Impact

Controlled comparison evaluating validation hard error reduction with refinement enabled vs disabled.

| Benchmark Case | Without Refinement Errors | With Refinement Errors | Hard Errors Resolved | Validity Improved |
|---|---:|---:|---:|---|
| `case_01_small_single_floor` | 0 | 0 | 0 | NO CHANGE |
| `case_02_medium_single_floor` | 0 | 0 | 0 | NO CHANGE |
| `case_04_two_floor_family` | 0 | 0 | 0 | NO CHANGE |
| `case_09_attached_suite` | 0 | 0 | 0 | NO CHANGE |

---

## 5. Multi-Design Diversity & Validity

Multi-design alternatives are evaluated for structural diversity using the Phase 9 Jaccard-graph `calculate_diversity_distance` metric.
- Diversity is reported independently of quality.
- Zero synthetic ranking or winner declarations are made.

---

## 6. Explainability Completeness & Reproducibility

- **Multi-Run Reproducibility Checks:** 2 cases evaluated across 3 repeated runs.
- **Deterministic Stability:** 2 / 2 cases produced 100% bitwise identical canonicalized outputs.
- **No Fabrication Guarantee:** 100% of generated explanation traces map to genuine structured provenance events.

---

## 7. Limitations & Honest Discussion

1. **Mock LLM Client Usage in Benchmarks:** The evaluation defaults to deterministic `MockLLMClient` for 100% offline, reproducible execution. Live LLMs (e.g. Hugging Face DeepSeek) may introduce natural language variance.
2. **Spatial Complexity in Ultra-Constrained Infill:** Plots with high setback-to-area ratios restrict geometric freedom, occasionally requiring multiple refinement passes.
3. **Process-Local Storage:** In-memory registry does not persist across restarts (by design).

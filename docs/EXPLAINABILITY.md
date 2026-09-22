# PlanForge AI — Explainability & Decision Trace

This document describes the architecture, data contracts, and operational guarantees of the **Explainability & Decision Trace System** implemented in `app/explainability/`.

---

## 1. Purpose & Core Design Invariants

PlanForge AI implements a multi-stage autonomous architectural generative pipeline. To maintain full scientific auditability, client transparency, and regulatory compliance, the Explainability & Decision Trace system records **every architectural decision and its factual evidence** from initial raw brief to final multi-alternative floor plans.

The Explainability system is governed by five authoritative invariants:

1. **Decisions and Evidence, NOT Chain-of-Thought**:
   - The trace records *what was decided*, *why it was decided* (explicit architectural rationale), and *what factual evidence supported it* (dimensions, areas, graph connections, constraint checks).
   - Zero internal deliberation, hidden reasoning traces, token-level thought, or model scratchpads are stored.
2. **Zero Fabrication**:
   - Only facts and metrics actually computed by pipeline algorithms (e.g. actual ASAA score components, validated dimensions, polygon areas) may be reported.
   - If an attribute, candidate breakdown, or rationale is absent upstream, the system explicitly reports `"Rationale not provided"` or notes the absence rather than synthesizing plausible-sounding justifications.
3. **Read-Only / Immutability**:
   - The trace system observes and records. It never modifies, wraps, or mutates source pipeline models (`Requirements`, `PlanningSpec`, `AllocationSet`, `ArchitecturalDesignSet`, `FloorPlanSet`, `ValidationReport`, `RefinementResult`, `DesignAlternativeSet`).
4. **Full Entity Lifecycle Traceability**:
   - Every room maintains an unbroken lineage connecting its source requirement, planning room spec, ASAA allocated region, architectural proposal, constructed geometry, validation findings, and iterative refinement modifications.
5. **100% Deterministic & Offline**:
   - Serialization and rendering execute deterministically without live LLM calls, internet access, or non-repeatable heuristics.

---

## 2. Pipeline Stages

The decision trace captures events across 9 authoritative pipeline stages:

```
[1. Requirement System]    (User Brief & Parsing)
          ↓
[2. Strategic Planning]    (Program Formulation & Adjacency)
          ↓
[3. ASAA Allocation]       (Spatial Bisection & Bounding Regions)
          ↓
[4. Architectural Design]  (Room Shapes, Door/Window Intents)
          ↓
[5. Geometry Engine]       (Dual Polygons, Physical Walls & Swings)
          ↓
[6. Independent Validator] (Deterministic Compliance Verification)
          ↓
[7. Refinement Loop]       (Closed-Loop Issue Resolution)
          ↓
[8. Diversity Generation]  (Design Signatures & Distance Matrices)
          ↓
[9. Final Selection]       (Alternative Acceptance & Rejection Logging)
```

| Stage Enum (`StageName`) | Stage Description |
|---|---|
| `requirement` | User-specified boundary, setback, orientation, and room requirements. |
| `planning` | Room functional classification, priority ranking, and relationship graphs. |
| `asaa_allocation` | Spatial partitioning, buildable envelope bisection, and region assignment. |
| `architectural_design` | Room shape selection, dimensions, door intents, and window orientations. |
| `geometry` | Deterministic physical construction of walls, usable polygons, and door swings. |
| `validation` | Independent deterministic verification across 18 check groups. |
| `refinement` | Iterative closed-loop corrections linking changes to validation issues. |
| `diversity` | Structural design signature extraction and pairwise distance evaluation. |
| `final_selection` | Acceptance of certified alternatives and rejection logging with reasons. |

---

## 3. Provenance Sources

Every event explicitly identifies the authoritative entity or algorithm that produced the decision (`ProvenanceSource`):

| Source Enum (`ProvenanceSource`) | Description |
|---|---|
| `user` | Explicitly stated by the user in the prompt or requirements. |
| `system_derived` | Deterministically derived by rule or pipeline conventions. |
| `requirement_agent` | Extracted during requirement parsing and normalization. |
| `planning_agent` | Strategic reasoning and graph synthesis by PlanningAgent. |
| `asaa` | Computational spatial partitioning and optimization by ASAA. |
| `architectural_llm` | Spatial layout and intent proposals from ArchitecturalAgent. |
| `geometry_engine` | Deterministic coordinate and polygon calculation by GeometryEngine. |
| `independent_validator`| Legal, geometric, and physical compliance rules from FloorPlanValidator. |
| `refinement_llm` | Targeted corrective adjustments from RefinementAgent. |
| `diversity_agent` | Structural variety evaluation and distance matrix computation. |

---

## 4. Decision Types Catalogue

`DecisionType` enumerates 23 standardized decision and evidence event types:

- **Requirement Stage**:
  - `requirement_parsed`: Plot boundaries, setbacks, orientation, or room requirements parsed.
  - `requirement_inferred`: Default constraints or system defaults applied.
- **Planning Stage**:
  - `room_classified`: Functional categorization (`social`, `private`, `service`, `circulation`).
  - `priority_assigned`: Priority weighting (`high`, `normal`, `low`) with functional rationale.
  - `adjacency_enforced`: Required or preferred room relationship formulated.
  - `circulation_planned`: Entrance, spine, or core connectivity intent defined.
- **ASAA Allocation Stage**:
  - `allocation_assigned`: Spatial region partitioned and allocated with area/score facts.
  - `buildable_bounded`: Setback-adjusted buildable boundary polygon computed.
  - `candidate_scored`: Objective score components computed for candidate layout.
- **Architectural Design Stage**:
  - `room_shape_selected`: Shape (`rectangular`, `square`, `l_shaped`) and dimensions selected.
  - `room_dimensions_selected`: Width and length proportions chosen within ASAA bounds.
  - `door_intent_created`: Functional access intent connecting spaces specified.
  - `window_intent_created`: Daylight and ventilation orientation intent specified.
  - `staircase_intent_created`: Multi-floor vertical core transition specified.
- **Geometry Stage**:
  - `geometry_constructed`: Physical usable polygon, walls, and openings materialized.
- **Validation Stage**:
  - `validation_passed`: All 18 check groups satisfied.
  - `validation_failed`: Critical errors or legal non-compliance detected.
  - `validation_warning`: Soft architectural advisory warning recorded.
- **Refinement Stage**:
  - `refinement_applied`: Design modification linked directly to validation issue.
  - `refinement_converged`: Design achieved zero errors after iterative correction.
  - `refinement_terminated`: Iteration limit reached or infeasibility diagnosed.
- **Diversity Stage**:
  - `alternative_accepted`: Layout certified as valid and structurally diverse.
  - `alternative_rejected`: Candidate rejected due to schema, validation, duplicate, or near-duplicate status.

---

## 5. End-to-End Entity Lifecycle Traceability

A central architectural feature is the **unbroken room entity chain** (`EntityTraceChain`). Because different pipeline stages produce specialized representations of a room, PlanForge maintains strict ID linkage across all stages:

```
User Requirement
  └─ id: "req_living"
       ↓
Planning RoomSpec
  ├─ id: "room_living_01"
  └─ source_requirement_id: "req_living"
       ↓
ASAA AllocatedRegion
  ├─ id: "region_living_01"
  └─ room_spec_id: "room_living_01"
       ↓
Architectural RoomDesign
  ├─ id: "design_living_01"
  └─ allocated_region_id: "region_living_01"
       ↓
Geometry GeoRoom
  ├─ id: "geo_living_01"
  └─ architectural_room_id: "design_living_01"
       ↓
Validation Issues & Refinement Changes
  ├─ ValidationIssue.entity_id: "geo_living_01" / "room_living_01"
  └─ RefinementChange.room_id: "design_living_01" / "room_living_01"
```

Calling `trace.get_entity_chain(room_id)` with *any* of the room's identifiers (`r_spec.id`, `region.id`, `room_design.id`, `geo_room.id`, or `source_requirement_id`) returns the exact same complete lifecycle chain containing:
- `chain.requirement_event`: Initial user request.
- `chain.planning_event`: Functional categorization and priority assignment.
- `chain.allocation_event`: ASAA spatial bounding region and area score.
- `chain.architectural_event`: Room shape, dimensions, and architectural rationale.
- `chain.geometry_event`: Usable polygon construction, wall counts, and opening counts.
- `chain.validation_events`: Any validation findings pertaining to the room.
- `chain.refinement_events`: Any iterative adjustments made to the room.

---

## 6. Human-Readable Explanation Rendering

`ExplanationRenderer` transforms structured decision traces into clean, deterministic markdown reports across six distinct levels:

1. **Project Explanation** (`render_project_explanation`):
   - Executive summary of project dimensions, floor counts, total decisions recorded, and high-level milestones.
2. **Alternative Narrative** (`render_alternative_explanation`):
   - Strategy overview, architectural characteristics, validation status, refinement summary, and pairwise diversity scores.
3. **Room Narrative** (`render_room_narrative`):
   - Complete room lifecycle story from user requirement through planning, allocation, design proposal, and geometry.
   - Strictly reports factual metrics; falls back gracefully to `"Rationale not provided"` without hallucination.
4. **Validation Explanation** (`render_validation_explanation`):
   - Overall compliance score and status.
   - Structured list of errors and warnings with rule IDs, affected rooms, expected values, and observed measurements.
5. **Refinement Narrative** (`render_refinement_explanation`):
   - Iteration history, convergence status, and chronological audit of modifications mapped to the issues that triggered them.
6. **Diversity Comparison** (`render_diversity_explanation`):
   - Side-by-side structural comparison of two design alternatives.
   - Evaluates 5 topological features: Circulation Topology, Entrance Room Type, Social Flow Sequence, Private Zone Clustering, and Vertical Core Relationship.

---

## 7. Serialization & Immutability Guarantees

- `DecisionTrace.to_dict()` and `to_json()` export full traces to portable JSON.
- `DecisionTrace.from_dict()` and `from_json()` provide round-trip deserialization.
- Pydantic v2 convention methods (`model_dump()`, `model_dump_json()`) are natively supported.
- `DecisionTraceBuilder.build()` is strictly non-invasive: input data models remain bitwise identical before and after trace generation.

# PlanForge — Refinement Agent & Iterative Correction (Phase 8)

This document describes the design, responsibilities, contracts, and invariants of the
**Refinement Agent** and **Refinement Loop** established in Phase 8.

---

## 1. Role in the PlanForge Pipeline

```
User Input
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
  ↓ ◄────────────────────────────────────────────────────┐
Refinement Agent            → Revised ArchitecturalDesign│ (CORRECT)
  ↓                                                      │
Geometry Engine             → Reconstructed GeometrySet  │
  ↓                                                      │
Validator                   → ValidationReport ──────────┘
  ↓ (When valid or terminated)
Final Output                → RefinementResult / FloorPlanSet
```

In the PlanForge pipeline, the Refinement Agent is responsible for **CORRECT**:
- It receives a `ValidationReport` from the Independent Validator alongside the current `ArchitecturalDesignSet` and locked `AllocationSet`.
- It analyzes validation failures (missing doors, floating doors, exterior/interior wall mismatches, dimension bounds, connectivity breaks).
- It produces an updated `ArchitecturalDesignSet` specifying architectural intent corrections.
- It hands the revised design back to the **Geometry Engine** to reconstruct physical geometry and to the **Validator** to re-verify compliance.

---

## 2. Core Invariants & Boundaries

1. **Zero Direct Geometry Mutation:**
   The Refinement Agent **never** touches `GeometrySet`, `GeoRoom`, `GeoWall`, `GeoDoor`, `GeoWindow`, or Shapely polygons. All corrections are expressed purely as modifications to `RoomDesign`, `DoorIntent`, or `WindowIntent`.
2. **ASAA Allocation Immutability:**
   Allocated functional bounding regions (`AllocatedRegion.polygon`, IDs, room associations) are locked by ASAA. The Refinement Agent cannot alter allocation boundaries or re-assign rooms to different regions.
3. **Room Preservation:**
   Rooms cannot be silently dropped, added, or renamed. The exact set of rooms from the original architectural design must be strictly preserved.
4. **Floor Assignment Preservation:**
   Rooms cannot be moved across floors. Every room remains strictly on its assigned floor.
5. **No Self-Certification:**
   The Refinement Agent never declares a floor plan valid. Only the Independent Validator (`FloorPlanValidator`) can certify validity.
6. **Controlled Termination:**
   The refinement loop strictly terminates upon convergence, reaching `max_iterations`, detecting design oscillation, or detecting that the agent produced an unchanged design.

---

## 3. Data Contracts

### 3.1 `RefinementStatus` (`app.models.refinement.RefinementStatus`)
Enum describing the terminal status of the refinement loop:
- `VALID_ON_INITIAL_PASS`: Initial design passed validation without requiring refinement.
- `CONVERGED`: Validator certified the design as valid after one or more refinement iterations.
- `MAX_ITERATIONS_REACHED`: Refinement reached the maximum configured iterations without resolving all validation errors.
- `REFINEMENT_FAILED`: Refinement agent failed to produce a valid response or produced no changes.
- `OSCILLATION_DETECTED`: Refinement agent cycled back to an architectural design state seen in an earlier iteration.

### 3.2 `RefinementChange` (`app.models.refinement.RefinementChange`)
Structured record of an individual architectural change made during refinement:
- `floor_number`: Target floor (int).
- `room_id`: Affected room ID (str).
- `change_type`: Category (`dimension`, `door_add`, `door_modify`, `door_remove`, `window_add`, `window_modify`, `window_remove`, `shape`).
- `description`: Human-readable explanation.
- `before`: Value prior to refinement (dict or None).
- `after`: Value after refinement (dict or None).

### 3.3 `RefinementIterationRecord` (`app.models.refinement.RefinementIterationRecord`)
Captures a complete snapshot of a single iteration for auditability and research logging:
- `iteration`: Iteration number (0 = initial validation).
- `design_version`: Version number of `ArchitecturalDesignSet`.
- `validation_report`: Full `ValidationReport` produced by the Validator for this iteration.
- `is_valid`: Boolean flag indicating if all floors passed.
- `score`: Overall validation score.
- `changes_applied`: List of `RefinementChange` objects applied by the agent (empty for iteration 0).
- `error_count` / `warning_count`: Quantitative metrics of issues in this iteration.
- `timestamp`: UTC ISO timestamp.

### 3.4 `RefinementResult` (`app.models.refinement.RefinementResult`)
Final output returned by `RefinementLoop.run()`:
- `status`: `RefinementStatus`.
- `is_valid`: Whether the final design is valid.
- `total_iterations`: Total iterations executed.
- `final_design`: The terminal `ArchitecturalDesignSet`.
- `final_floor_plans`: The reconstructed `FloorPlanSet` (or None if unconstructed).
- `final_validation_report`: The terminal `ValidationReport`.
- `iterations`: Complete history of all `RefinementIterationRecord`s.
- `termination_reason`: Diagnostic explanation of termination.

---

## 4. Components

### 4.1 `RefinementContext` & `RefinementContextBuilder`
Located in `app/agents/refinement_agent/context.py`.
- Formulates an immutable, focused context specifically for refinement.
- Prioritizes issues deterministically:
  - Errors are placed before warnings.
  - Categories are prioritized by structural dependency:
    `completeness` → `boundary` → `allocation` → `dimension` → `relationship` → `staircase` → `connectivity` → `door` → `window`.
- Identifies invalid floors so the agent can preserve valid floors untouched.
- Formats structured issue diagnostic summaries with actionable suggestions.

### 4.2 `RefinementOutputValidator`
Located in `app/agents/refinement_agent/output_validator.py`.
- Validates that the LLM response is compliant with architectural contracts before accepting it:
  - Validates JSON format and top-level schema.
  - Enforces 100% room preservation (rejects invented rooms and dropped rooms).
  - Enforces allocation preservation (`allocated_region_id` cannot change).
  - Rejects raw geometry keys (`walls`, `polygon`, `vertices`, `coordinates`).
  - Verifies room dimensions stay within allocated region bounds.
- Extracts granular `RefinementChange` records by comparing previous vs. revised `RoomDesign`s.

### 4.3 `RefinementAgent`
Located in `app/agents/refinement_agent/agent.py`.
- Orchestrates LLM prompt construction, invocation, and response parsing.
- Implements minimal change discipline: floors that are already valid in the input report are preserved identically without invoking the LLM.
- Includes a smart deterministic mock generator (`_deterministic_mock_refinement_generator`) for offline testing that analyzes validation diagnostics and synthesizes precise, compliant corrections.

### 4.4 `RefinementLoop`
Located in `app/agents/refinement_agent/loop.py`.
- Orchestrates the iterative cycle:
  `Design (v) → Geometry Engine → Validator → Refinement Agent → Design (v+1) → ...`
- Iteration 0: Evaluates initial design. If already valid, exits immediately with `VALID_ON_INITIAL_PASS`.
- Oscillation Prevention: Maintains SHA-256 canonical fingerprints of normalized architectural designs. If a fingerprint matches any previously visited iteration, terminates with `OSCILLATION_DETECTED`.
- No-Change Detection: If the agent returns an identical design or zero changes, terminates with `REFINEMENT_FAILED`.
- Iteration Limit: Enforces `max_iterations` (default 3), terminating with `MAX_ITERATIONS_REACHED` if errors persist.

---

## 5. Verification & Test Suite

The Refinement Agent implementation is validated across unit and integration test suites:
- `tests/unit/test_refinement/test_refinement_context.py`: Immutability, issue prioritization, diagnostic formatting.
- `tests/unit/test_refinement/test_refinement_prompts.py`: System prompt invariants, floor prompt construction.
- `tests/unit/test_refinement/test_refinement_output_validator.py`: Schema validation, rejection of invented/missing rooms, rejection of raw geometry, change extraction.
- `tests/unit/test_refinement/test_refinement_agent.py`: Single-floor door issue resolution, preservation of valid floors.
- `tests/unit/test_refinement/test_refinement_loop_coordinator.py`: Initial pass termination, no-change detection, max iterations enforcement.
- `tests/integration/test_refinement_loop.py`: End-to-end multi-room refinement correction with full Geometry Engine and Validator in the loop, and infeasible scenario termination.

**Current Test Status:** 336 passed, 0 failed across the entire PlanForge repository.

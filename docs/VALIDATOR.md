# PlanForge AI — Independent Validator (Phase 7)

## 1. Architectural Role & Responsibility

The **Independent Validator** (`FloorPlanValidator` / `Validator`) is the authoritative verification authority in the PlanForge AI architecture.

```
User Input
    ↓
Requirement Agent (WHAT)
    ↓
Planning Agent (ORGANIZE)
    ↓
ASAA (WHERE)
    ↓
Architectural LLM (HOW)
    ↓
Geometry Engine (CONSTRUCT)
    ↓
Independent Validator (VERIFY)   ← THIS COMPONENT (Phase 7)
    ↓
Refinement Agent (CORRECT)       ← Downstream (Phase 8)
    ↓
Final Floor Plan
```

### Authoritative Invariants

1. **Zero LLM Calls**: The Validator is 100% deterministic, rule-based, and computational. It performs zero model inferences or heuristic stochastic decisions.
2. **Zero Geometry Mutation**: The Validator never modifies, scales, moves, trims, snaps, or repairs coordinates. It is strictly read-only inspection.
3. **Zero Self-Certification**: Geometry Engine outputs remain unvalidated (`is_valid=False`, `validation=None`) until explicitly verified by the Validator.
4. **Hard vs. Soft Constraint Discipline**:
   - **Hard Errors** (`severity="error"`): Invalidate the floor plan (`floor_plan.is_valid = False`, `report.overall_valid = False`).
   - **Soft Warnings** (`severity="warning"`): Do NOT invalidate the floor plan (`overall_valid = True`), but are clearly reported and penalize the overall quality score.
   - Soft warnings are **NEVER** marked as `checks_passed`.
5. **Entity Traceability**: Every issue records `check`, `category`, `severity`, `target_id`, `room_id`, `floor_number`, and structured `details`.

---

## 2. Input / Output Contracts

### Input Contract
- `floor_plan_set: FloorPlanSet`: Constructed multi-floor floor plans containing physical geometry (`GeoRoom`, `GeoWall`, `GeoDoor`, `GeoWindow`, `GeoStaircase`).
- `requirements: Optional[Requirements]`: Upstream user requirements (room counts, minimum areas, plot dimensions, setbacks, relationships).
- `planning_spec: Optional[PlanningSpec]`: Upstream spatial program and topological adjacency graphs.
- `allocation_set: Optional[AllocationSet]`: Upstream ASAA allocated regions.
- `architectural_design_set: Optional[ArchitecturalDesignSet]`: Upstream architectural room design proposals.
- `plot_boundary: Optional[List[Point2D]]`: Property boundary coordinates (falls back to requirements).
- `buildable_boundary: Optional[List[Point2D]]`: Setback-adjusted buildable boundary (falls back to requirements).

### Output Contract
- `ValidationReport`:
  - `results: list[ValidationResult]` (one per floor)
  - `overall_valid: bool` (`True` iff all floors have zero error-level issues)
  - `overall_score: float` (average score 0.0 – 100.0 across all floors)
  - `total_errors: int`, `total_warnings: int`
  - `all_issues() -> list[ValidationIssue]`
- Updates target `FloorPlan` instances in-place:
  - `floor_plan.validation = result`
  - `floor_plan.is_valid = result.is_valid`
  - `floor_plan_set.validation_report = report`

---

## 3. The 18 Check Groups

The Validator enforces 18 comprehensive check groups divided into specialized, modular validators:

| Check Group | Category | Severity | Description | Specialized Validator |
|---|---|---|---|---|
| **1. Structural Completeness** | `completeness` | `error` | Verifies all required rooms exist; detects missing or unrequested rooms. | `RoomValidator` |
| **2. Boundary Containment** | `boundary` | `error` | Zero tolerance for plot boundary spill; buildable envelope containment. | `BoundaryValidator` |
| **3. Floor Assignments** | `completeness` | `error` | Rooms must appear on their planned/required floor. | `RoomValidator` |
| **4. Usable Area Compliance** | `dimension` | `error` / `warning` | Hard minimum area threshold; soft target area variance warnings. | `DimensionValidator` |
| **5. Overlap Prevention** | `overlap` | `error` | Pairwise interior room and staircase intersection must be zero. | `OverlapValidator` |
| **6. Required Adjacencies** | `relationship` | `error` | Mandatory adjacency via direct door or shared wall ($\ge 0.30$m). | `RelationshipValidator` |
| **7. Preferred Adjacencies** | `relationship` | `warning` | Preferred adjacencies advisory notifications. | `RelationshipValidator` |
| **8. Separation & Avoidance** | `relationship` | `error` | Prohibited adjacencies must not share walls or direct doors. | `RelationshipValidator` |
| **9. Attached Suites** | `relationship` | `error` | Attached rooms (e.g. ensuite bath) must connect directly to master room. | `RelationshipValidator` |
| **10. Door Wall Attachment** | `door` | `error` | Doors must lie on walls within tolerance; no floating doors. | `DoorValidator` |
| **11. Door Swing Clearance** | `door` | `warning` | Door swing arc clearance without colliding with opposite walls. | `DoorValidator` |
| **12. Window Wall Placement** | `window` | `error` / `warning` | Windows must be on exterior walls; sill $\ge 0$; orientation matching. | `WindowValidator` |
| **13. Staircase Geometry** | `staircase` | `error` | Multi-floor staircase presence, riser/tread counts, core containment. | `StaircaseValidator` |
| **14. Connectivity & Access** | `connectivity` | `error` | BFS door graph reachability; room isolation detection; entrance access. | `ConnectivityValidator` |
| **15. Multi-Floor Consistency** | `multi_floor` | `error` | Vertical core alignment across floors; floor count matching. | `StaircaseValidator` / `CirculationValidator` |
| **16. ASAA Containment** | `allocation` | `error` | Room usable polygon must be contained in allocated ASAA region. | `RoomValidator` |
| **17. Wall Thickness & Closure** | `room_geometry` | `error` | Enclosed rooms must have non-zero thickness walls and proper vertices. | `RoomValidator` |
| **18. Geometry Topology** | `room_geometry` | `error` | Valid polygons, zero self-intersections, non-degenerate coordinates. | `RoomValidator` |

---

## 4. Scoring Algorithm

The score is deterministically computed for each floor and averaged across the building:

$$\text{Floor Score} = \max(0.0, 100.0 - (15.0 \times N_{\text{errors}}) - (3.0 \times N_{\text{warnings}}))$$

- **Base Score**: 100.0 points.
- **Error Penalty**: $-15.0$ points per hard error.
- **Warning Penalty**: $-3.0$ points per advisory warning.
- **Pass Invariant**: A floor plan is only marked `is_valid = True` if $N_{\text{errors}} = 0$. Soft warnings degrade the score but allow `is_valid = True`.

---

## 5. Usage Example

```python
from app.validation.validator import FloorPlanValidator

# Instantiate the independent validator
validator = FloorPlanValidator()

# Validate complete FloorPlanSet
report = validator.validate(
    floor_plan_set=floor_plan_set,
    requirements=requirements,
    planning_spec=planning_spec,
    allocation_set=allocation_set,
    architectural_design_set=design_set,
)

if not report.overall_valid:
    print(f"Floor plan rejected with {report.total_errors} errors:")
    for issue in report.all_issues():
        if issue.severity == "error":
            print(f"[{issue.category.upper()}] {issue.check}: {issue.message} (Floor {issue.floor_number})")
else:
    print(f"Floor plan passed verification! Quality score: {report.overall_score}/100.0")
```

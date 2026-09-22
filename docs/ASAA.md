# Adaptive Space Allocation Algorithm (ASAA) — Technical Specification

## 1. ASAA Purpose
The Adaptive Space Allocation Algorithm (ASAA) is the spatial planning engine of PlanForge AI. Its sole responsibility is to answer **WHERE** each room and functional zone should be allocated within the buildable footprint.

ASAA maps the strategic spatial program defined in `PlanningSpec` (Phase 3) into an `AllocationSet` (Phase 4) containing abstract 2D bounding regions (`AllocatedRegion`) for each floor.

---

## 2. Input Contracts
ASAA consumes a validated `PlanningSpec` containing:
- `global_constraints`: Plot dimensions (`plot_width_m`, `plot_depth_m`), `plot_area_sqm`, `plot_polygon`, `setbacks`, `orientation`.
- `floors`: List of `FloorPlanSpec` objects per floor.
- `room_specs`: List of `RoomSpec` objects detailing target/min/max areas, priorities, categories, and attachments.
- `adjacency_matrix` and `avoid_matrix`: Relationship graphs capturing required/preferred adjacencies and separation requirements.
- `circulation_zones` and `circulation_notes`: Circulation intent.
- `entrance_intent`: Facing direction and preferred access room.
- `staircase_intent`: Multi-floor vertical circulation intent.

ASAA operates solely on structured planning models and never directly parses raw user text.

---

## 3. Output Contracts
ASAA outputs an `AllocationSet` containing:
- `allocations`: List of `Allocation` objects (one per floor).
  - `floor_number`, `floor_name`, `total_area_sqm`, `circulation_area_sqm`, `score`.
  - `allocated_regions`: List of `AllocatedRegion` objects:
    - `id`: Unique region identifier.
    - `room_type`: Canonical room type string.
    - `room_spec_id`: Traceable link to `RoomSpec.id`.
    - `floor_number`: Assigned floor.
    - `target_area_sqm`: Requested area target.
    - `area_sqm`: Actual allocated region area.
    - `approximate_dimensions`: `(width, length)` in meters.
    - `polygon`: List of `(x, y)` 2D boundary vertices.
    - `centroid`: `(x, y)` geometric center.
    - `priority`: Planning priority (`high`, `normal`, `low`).
    - `adjacency_regions`: List of region IDs sharing physical boundary contact.
    - `zone_type`: `"room"`, `"circulation"`, `"entrance"`, `"staircase"`.
    - `score`: Candidate quality score.
- `staircase_aligned`: Boolean confirming identical vertical alignment of staircase zones across floors.

---

## 4. Strict "WHERE" Responsibility Boundary
ASAA determines:
- Where rooms and zones are positioned relative to each other and plot boundaries.
- Allocated area, approximate dimensions, and bounding polygon for each region.
- Physical boundary adjacency between neighboring regions.
- Placement of entrance, staircase, and circulation zones.
- Candidate allocation quality scores.

ASAA strictly does **NOT** determine:
- Final architectural room shape or detailed room dimensions chosen by the architect.
- Wall geometry, wall thickness, or wall centerline offsets.
- Doors, door placement, door swings, or door widths.
- Windows, window openings, or sill heights.
- Detailed corridor geometry or staircase tread/riser geometry.
- Final architectural detailing or CAD layouts.

Those responsibilities belong strictly to downstream stages (Phase 5: Architectural LLM, Phase 6: Geometry Engine).

---

## 5. Area Allocation & Two-Pass Budgeting
Implemented in `AreaBudgeter` (`app/asaa/area_budgeter.py`):
1. **Circulation Allowance**: Reserves 10%–15% of buildable area for circulation corridors and entrance foyer, plus 8.0 m² for vertical staircase cores when required.
2. **Infeasibility Gating**: Evaluates whether $\sum \text{min\_area} + \text{staircase} + \text{min\_circulation} \le \text{buildable\_area}$. If infeasible, immediately raises a structured `InfeasibleAllocationError` detailing the available area, requested area, deficit, and offending rooms.
3. **Two-Pass Allocation**:
   - **Pass 1**: Allocates each room its explicit `min_area_sqm` (or 80% baseline if unstated).
   - **Pass 2**: Distributes the remaining room budget proportionally based on the target area gap and priority weights (`high` = 1.5, `normal` = 1.0, `low` = 0.7).
   - Enforces `max_area_sqm` bounds where specified.
4. **Guarantees**: Never silently removes requested rooms; never reduces room area below an explicit user minimum.

---

## 6. Boundary Handling & Setbacks
Implemented in `BuildableBoundaryCalculator` (`app/asaa/boundary.py`):
- **Plot Boundary vs. Buildable Boundary**:
  - If setbacks are explicitly specified (directional `front`, `rear`, `left`, `right` or uniform `all`), they are subtracted from the plot boundary.
  - If setbacks are not specified, buildable boundary equals the plot boundary without assumed offsets.
- **Rectangular Plots**: Direct insets applied to axis-aligned coordinates.
- **Irregular & L-Shaped Polygons**: Preserves actual polygon boundary using Shapely buffer/clipping operations. **Never silently replaces an irregular polygon with its bounding box.**
- Validates that buildable area is non-empty; raises `BoundaryConstraintError` if excessive setbacks eliminate the buildable area.

---

## 7. Spatial Partitioning
Implemented in `SpatialPartitioner` (`app/asaa/spatial_partitioner.py`):
- Replaces naive modulo grid stride placement with computational 2D space-filling recursive bisection.
- Partitions the exact buildable boundary (rectangles, L-shapes, irregular polygons) into convex/near-convex sub-regions matching each room's area budget.
- Slices polygons along the optimal aspect axis using binary search cutting planes and Shapely intersections.
- Guarantees:
  - 100% boundary containment ($\text{region} \subseteq \text{buildable}$).
  - Zero overlap between any pair of allocated regions ($\text{area}(\text{region}_i \cap \text{region}_j) = 0$).

---

## 8. Relationship-Aware Allocation
Implemented in `CandidateScorer` and `SpatialPartitioner`:
- **Required Adjacency**: Rooms requiring direct contact must share physical boundary edges ($\text{length} \ge 0.1\text{m}$).
- **Preferred Adjacency**: Generates soft score bonus when preferred pairs touch.
- **Avoid / Separation**: Penalizes candidates if separated rooms share boundary contact.
- **Attached Rooms**: Enforces shared boundary contact between suites (e.g. attached bathroom and master bedroom).
- Evaluates actual spatial boundary contact rather than proxy distance heuristics.

---

## 9. Priority-Aware Allocation
- Priority (`high`, `normal`, `low`) guides area surplus distribution and optimal zone placement (e.g. high-priority social spaces anchored to front/entrance facing).
- Priority is an optimization factor and never overrides hard constraints (minimum area, boundary containment, non-overlap, explicit floor assignments).

---

## 10. Orientation & Facing
- If plot orientation or entrance facing is provided (e.g. North, South, East, West), ASAA aligns social rooms (living, dining, foyer) towards the preferred facade.
- Evaluated as a soft score component in candidate scoring.

---

## 11. Entrance Zone
- Allocates an entrance zone (`zone_type="entrance"`, room type `"foyer"`) anchored at the plot entrance facade.
- Does **NOT** construct entrance doors or door geometry.

---

## 12. Circulation Allocation
- Distinguishes and reserves circulation zones:
  - Public circulation: connecting entrance foyer, living, dining.
  - Private circulation: connecting bedrooms and bathrooms.
  - Vertical circulation: staircase core.
- Emits dedicated `AllocatedRegion` with `zone_type="circulation"`.
- Does **NOT** construct final hallway walls or corridor openings.

---

## 13. Staircase Zone Allocation & Multi-Floor Alignment
- For multi-floor projects, carves out a vertical staircase zone (`zone_type="staircase"`) of 6.0–8.0 m².
- **Vertical Alignment**: Floor 1 staircase boundary polygon is locked and replicated identically on Floor 2 and upper floors.
- Populates `AllocationSet.staircase_aligned = True` when coordinates match across all floors.
- Does **NOT** construct staircase treads, risers, landings, or railing geometry.

---

## 14. Multi-Floor Handling
- Allocates each floor independently within its footprint while coordinating vertical circulation.
- Strictly preserves explicit room-to-floor assignments.
- Never invents rooms on Floor 2.
- Never moves rooms across floors.

---

## 15. Candidate Generation
Implemented in `CandidateGenerator` (`app/asaa/candidate_generator.py`):
- Generates multiple distinct allocation candidates using 4 architectural strategies:
  1. `front_to_back`: Social spaces at front, private bedrooms at rear.
  2. `lateral`: Lateral wing partitioning (social wing vs. private sleeping wing).
  3. `radial`: Central core circulation with perimeter room distribution.
  4. `orientation_aligned`: Solar and facing-optimized room placement.

---

## 16. Candidate Scoring
Implemented in `CandidateScorer` (`app/asaa/scoring.py`):
- **Hard Constraints (Pass/Fail)**: Boundary containment, non-overlap, minimum area compliance.
- **Soft Score Components (0–100)**:
  - Area suitability (25%)
  - Relationship satisfaction (25%)
  - Shape compactness (15%)
  - Circulation connectivity (15%)
  - Orientation preference (10%)
  - Priority satisfaction (10%)
- Produces explainable `score_breakdown` dictionary.

---

## 17. Adaptive Refinement
Implemented in `AdaptiveRefiner` (`app/asaa/refiner.py`):
- Iteratively evaluates candidate allocations and applies allocation-level operations:
  - `SWAP`: Exchanges room assignments between compatible regions if doing so improves relationship satisfaction or orientation without violating minimum area or boundary constraints.
- Re-evaluates modified allocation and accepts improvements until plateau is reached.
- Strictly never modifies doors, windows, walls, or architectural details.

---

## 18. Determinism & Seeds
- ASAA execution is 100% deterministic given identical `PlanningSpec` and `seed`.
- Random number generators are explicitly seeded.

---

## 19. Explainability
- Every allocated region tracks its `target_area_sqm`, `area_sqm`, `priority`, `approximate_dimensions`, and physical `adjacency_regions`.
- Candidate evaluations record full metric breakdowns and structured rejection reasons.

---

## 20. Previous-Project Component Reuse
- **Reused**: Two-pass area allocation concept (`area_allocator.py`), priority-weighted distribution, multi-strategy generation concepts (`diverse_generator.py`), and adaptation operator concepts (`adaptation.py`).
- **Rejected & Excluded**: Direct door generation (`geometry/doors.py`), final room polygon construction with wall offsetting (`shape_generator.py`), inline door repair loops (`refinement_engine.py`), and modulo grid placement.

---

## 21. Limitations & Future Enhancements
- Non-orthogonal cut angles (currently orthogonal X/Y bisection).
- Curvilinear boundaries (polygonal approximations used).
- Detailed daylight/shadow analysis (soft orientation proxy currently used).

# PlanForge Data Contracts Specification (Phase 1)

This document specifies the authoritative data contracts for the seven-stage PlanForge pipeline.

```
User Input
  ↓
Requirement Agent           → Requirements
  ↓
Planning Agent              → PlanningSpec
  ↓
ASAA (Spatial Allocation)   → AllocationSet (WHERE)
  ↓
LLM Architectural Designer  → ArchitecturalDesignSet (HOW)
  ↓
Geometry Engine             → GeometrySet (CONSTRUCT)
  ↓
Validator                   → ValidationReport (VERIFY)
  ↓
Refinement Agent            → Revised ArchitecturalDesignSet (CORRECT)
  ↓
Final Output                → FloorPlanSet
```

---

## 1. Core Principles & Separation of Concerns

Each data contract has a single, strictly enforced responsibility boundary:

| Stage | Data Contract | Primary Question | Owns | Must NOT Own |
|---|---|---|---|---|
| **Requirement** | `Requirements`, `FloorRequirement`, `RoomRequirement` | **WHAT** does the user want? | User-stated room counts, area bounds, preferred/avoid adjacencies, plot dimensions, setbacks, orientation. | Geometry, coordinate math, invented rooms/floors. |
| **Planning** | `PlanningSpec`, `FloorPlanSpec`, `RoomSpec` | **STRATEGY:** How is the program organized? | Room zoning (public/private/service), priorities, relationship matrices, circulation intent, entrance/staircase intent. | Room polygons, wall coordinates, door swing geometry. |
| **ASAA** | `AllocationSet`, `Allocation`, `AllocatedRegion` | **WHERE** are functional spaces located? | Spatial partitioning, 2D allocated bounding regions, approximate centroids, circulation zones, vertical stair zones. | Final wall offsets, door swing arcs, window openings, architectural detailing. |
| **Architectural LLM** | `ArchitecturalDesignSet`, `ArchitecturalDesign`, `RoomDesign` | **HOW** are spaces shaped & connected? | Room shape proposals within regions, local wall alignments, door intents, window intents, staircase intents, design rationales. | Deterministic wall buffering, exact coordinate snapping, geometry validation. |
| **Geometry Engine** | `GeometrySet`, `Geometry`, `GeoRoom`, `GeoWall`, `GeoDoor`, `GeoWindow`, `GeoStaircase` | **CONSTRUCT:** What is the physical layout? | Deterministic wall lines and footprints, usable/built polygons, door cutouts and swing arcs, window openings, stair treads/risers. | Architectural decisions or intent generation. |
| **Validator** | `ValidationReport`, `ValidationResult`, `ValidationIssue` | **VERIFY:** Is the layout legally/physically sound? | Deterministic verification of boundaries, room overlap, dimensions, door accessibility, graph connectivity, staircase alignment. | Modifying geometry or design proposals. |
| **Refinement Agent** | Revised `ArchitecturalDesignSet` | **CORRECT:** How to resolve validation issues? | Structured modifications to door/window/room proposals based on validator feedback. | Directly mutating final Shapely polygons in bypass of Geometry Engine. |
| **Floor Plan** | `FloorPlanSet`, `FloorPlan` | **AGGREGATE:** What is the final deliverable? | Validated geometries per floor, validation reports, plot/buildable boundaries, generation metadata. | Algorithmic logic. |
| **Explainability** | `EventLog`, `Event` | **AUDIT:** Why were decisions made? | Chronological, structured record of stage inputs, outputs, rationales, and execution metrics. | Business logic. |

---

## 2. Model Specifications

### 2.1. Identifier Foundation (`app.utils.ids`)
- `generate_id(prefix: Optional[str] = None) -> str`: Generates collision-resistant identifiers using truncated UUID4 tokens. When a prefix is supplied (e.g. `"room"`), formats as `"{prefix}_{token}"`.

### 2.2. Requirement Models (`app.models.requirements`)
- **`RoomRequirement`**:
  - `id: str`: Unique requirement identifier.
  - `room_type: str`: Canonical room category name.
  - `min_count: int`: Minimum required count (default: 1).
  - `max_count: Optional[int]`: Maximum count if bounded.
  - `preferred_area_sqm: Optional[float]`: User's ideal room area.
  - `min_area_sqm: Optional[float]`: Hard lower bound.
  - `max_area_sqm: Optional[float]`: Hard upper bound.
  - `adjacency: list[str]`: Target rooms this room should touch.
  - `separation: list[str]`: Target rooms this room must NOT touch.
  - `attached_to: Optional[str]`: Explicit parent room if attached (e.g. ensuite attached to master bedroom).
  - `source: str`: Requirement provenance (`"user"`, `"derived"`, `"default"`).
- **`FloorRequirement`**:
  - `floor_number: int`: 1-based floor index.
  - `room_requirements: list[RoomRequirement]`: Explicit rooms on this floor.
  - `circulation_required: bool`: Whether hallways/circulation are needed.
  - `staircase_required: bool`: Whether vertical access is required.
  - `total_rooms() -> int`: Sum of `min_count` across floor room requirements.
- **`Requirements`**:
  - `plot_area_sqm: Optional[float]`: Gross plot area.
  - `plot_dimensions: Optional[tuple[float, float]]`: (width, depth) in meters.
  - `plot_shape: Optional[tuple[tuple[float, float], ...]]`: Boundary polygon vertices.
  - `setbacks: dict[str, float]`: Boundary setbacks (`"front"`, `"rear"`, `"left"`, `"right"`).
  - `orientation: Optional[str]`: Plot orientation (e.g. `"north"`).
  - `entrance_facing: Optional[str]`: Main entrance facing direction.
  - `floors: list[FloorRequirement]`: Explicit per-floor requirements.
  - `total_rooms() -> int`: Accurate sum across all floors.

### 2.3. Planning Models (`app.models.planning`)
- **`RoomSpec`**: Programmatic room specification with category (`"social"`, `"private"`, `"service"`, `"circulation"`), priority (`"high"`, `"normal"`, `"low"`), target area, adjacency lists, and avoidance lists.
- **`FloorPlanSpec`**: Floor-level planning specification with adjacency matrix, avoid matrix, circulation zones, entrance intent, and staircase intent.
- **`PlanningSpec`**: Project-level planning container with `all_room_specs()` and `total_target_area()` helpers.

### 2.4. Allocation Models (`app.models.allocation`)
- **`AllocatedRegion`**:
  - Spatial 2D bounding region allocated by ASAA.
  - Contains `polygon: list[tuple[float, float]]`, `centroid: tuple[float, float]`, and `approximate_dimensions: tuple[float, float]`.
  - Tagged by `zone_type`: `"room"`, `"circulation"`, `"entrance"`, or `"staircase"`.
- **`Allocation`**: Single floor spatial layout with `allocated_regions`, `circulation_area_sqm`, and zone query helpers.
- **`AllocationSet`**: Multi-floor allocation collection tracking `staircase_aligned: bool` for verified vertical core alignment across floors.

### 2.5. Architectural Intent vs. Constructed Geometry

PlanForge maintains a strict distinction between **Architectural Intent** (what the LLM proposes) and **Constructed Geometry** (what the Geometry Engine constructs):

```
Architectural Proposal (HOW)           Constructed Geometry (CONSTRUCT)
----------------------------           --------------------------------
DoorIntent                             GeoDoor (wall_id, position, swing_arc)
WindowIntent                           GeoWindow (wall_id, position, sill_height)
StaircaseIntent                        GeoStaircase (treads, risers, exact polygon)
RoomDesign (intended shape/dims)       GeoRoom (usable_polygon, built_polygon)
```

- **`DoorIntent`** (`app.models.doors`): Proposes a door between two spaces, wall orientation, door type, and architectural rationale. (Alias: `DoorSpec`).
- **`WindowIntent`** (`app.models.windows`): Proposes natural light openings, wall orientation, window type, and recommended dimensions. (Alias: `WindowSpec`).
- **`StaircaseIntent`** (`app.models.staircase`): Proposes vertical circulation, connecting floors, stair typology, and approximate anchor location. (Alias: `StaircaseSpec`).
- **`RoomDesign`** (`app.models.architectural_design`): Proposes room proportions, intended shape, proposed boundaries within ASAA regions, door intents, and window intents. (Alias: `RoomDesignProposal`).
- **`ArchitecturalDesignSet`**: Multi-floor collection of architectural proposals.

### 2.6. Geometry Models (`app.models.geometry`)
- **`GeoWall`**: Constructed wall segment with `start`, `end`, `thickness`, `height`, 2D footprint `polygon`, and associated room IDs.
- **`GeoDoor`**: Constructed door located at exact wall coordinates with a calculated `swing_arc` polygon and reference to upstream `intent_id`.
- **`GeoWindow`**: Constructed window opening with exact wall placement, width, height, sill height, and upstream `intent_id`.
- **`GeoStaircase`**: Constructed staircase with exact footprint polygon, riser count, tread depth, and upstream `intent_id`.
- **`GeoRoom`**: Dual-polygon representation containing `usable_polygon` (interior usable space) and `built_polygon` (wall centerline/exterior footprint).
- **`Geometry`**: Single-floor constructed layout containing all rooms, walls, doors, windows, staircases, and `buildable_polygon`.
- **`GeometrySet`**: Multi-floor constructed layout collection.

### 2.7. Validation Models (`app.models.validation`)
- **`ValidationIssue`**:
  - `severity`: `"error"` (causes check failure and invalidates plan), `"warning"` (advisory, does not invalidate plan), `"info"` (informational).
  - `category`: Category name (`"boundary"`, `"overlap"`, `"dimension"`, `"connectivity"`, `"relationship"`, `"staircase"`, `"door"`, `"window"`).
  - `target_id`: Optional ID of affected entity.
- **`ValidationResult`**:
  - `checks_failed: list[str]`: Categories that encountered error-level issues.
  - `checks_warned: list[str]`: Categories that encountered warning-level issues.
  - `checks_passed: list[str]`: Categories that passed cleanly with no errors.
  - **Critical Invariant:** Warnings do NOT mark a category as passed (`add_issue()` appends to `checks_warned` without adding to `checks_passed`).
- **`ValidationReport`**: Multi-floor composite report tracking `overall_valid`, `overall_score`, `total_errors`, `total_warnings`, and refinement loop `iteration`.

### 2.8. Floor Plan Models (`app.models.floor_plan`)
- **`FloorPlan`**: Validated deliverable for a single floor pairing `Geometry` with `ValidationResult`.
- **`FloorPlanSet`**: Multi-floor aggregate containing:
  - Explicit per-floor `floor_plans: list[FloorPlan]`.
  - Global `plot_boundary` and `buildable_boundary`.
  - Aggregate properties: `all_valid`, `total_usable_area`.
  - **No Floor-1 Mirroring:** Eliminates legacy bug where top-level fields mirrored Floor 1 only.

### 2.9. Event Models (`app.models.events`)
- **`Event`**: Structured record capturing stage, event type, timestamp, execution time in milliseconds, and arbitrary data payload.
- **`EventLog`**: Chronological event tracker with filtering by stage and event type.

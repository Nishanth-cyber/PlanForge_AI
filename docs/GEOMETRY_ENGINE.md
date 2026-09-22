# Geometry Engine — Architectural Documentation

## 1. Purpose

The **Geometry Engine** is the deterministic physical construction layer of PlanForge AI.
In the seven-stage architecture:
- **Requirement Agent** = WHAT the user wants
- **Planning Agent** = ORGANIZE strategic requirements & spatial connectivity
- **ASAA** = WHERE spaces are allocated into spatial regions
- **Architectural LLM** = HOW allocated spaces should be designed
- **Geometry Engine** (Phase 6) = **CONSTRUCT exact CAD geometry**
- **Validator** (Phase 7) = VERIFY geometric correctness
- **Refinement Agent** (Phase 8) = CORRECT invalid proposals

The Geometry Engine strictly realizes upstream proposals without performing architectural redesign. It does NOT decide which room goes where, whether a room should move to another floor, or whether a different layout is superior. If an architectural design violates allocation bounds or physical possibility, the engine raises a structured `GeometryConstructionError` rather than silently redesigning.

---

## 2. Input Contract

The Geometry Engine takes clean, structured architectural inputs:
- `ArchitecturalDesignSet` / `ArchitecturalDesign`:
  - `RoomDesign`: Semantic room shapes (`rectangular`, `square`, `l_shaped`), intended dimensions/proportions, proposed boundary, door intents, window intents.
  - `DoorIntent`: Functional connection requests (`connects_from`, `connects_to`, `wall_orientation`, `recommended_width`, `door_type`).
  - `WindowIntent`: Natural lighting/ventilation requests (`room_id`, `wall_orientation`, `sill_height`, `recommended_width`, `window_type`).
  - `StaircaseIntent`: Vertical circulation requests (`from_floor`, `to_floor`, `recommended_width`, `stair_type`).
- `AllocationSet` / `Allocation`:
  - `AllocatedRegion`: 2D spatial boundary polygons allocated by ASAA for habitable rooms, circulation, and staircase cores.
- `plot_boundary`: 2D polygonal coordinates of the property boundary.
- `buildable_boundary`: 2D polygonal coordinates of the buildable footprint after setback enforcement.

---

## 3. Output Contract

The Geometry Engine produces:
- `Geometry`: Geometric assembly for a single floor:
  - `rooms: list[GeoRoom]`: Rooms with dual `usable_polygon` (interior usable clear dimension) and `built_polygon` (wall boundary footprint).
  - `walls: list[GeoWall]`: Physical wall segments with thickness, height, type (`exterior`, `interior`), and 2D footprint polygons.
  - `doors: list[GeoDoor]`: Physical doors placed along wall segments with 90° swing arc polygon vertices.
  - `windows: list[GeoWindow]`: Physical window openings placed on matching exterior walls.
  - `staircases: list[GeoStaircase]`: Physical staircase footprints with treads, risers, and multi-floor alignment.
  - `plot_polygon` and `buildable_polygon`.
- `GeometrySet`: Aggregated geometry across all floors.
- `FloorPlanSet`: Final CAD-ready assembly containing `FloorPlan` instances per floor.
  - **Stage boundary enforcement**: `is_valid` is set to `False` and `validation` is `None`. Validation is strictly executed in Phase 7.

---

## 4. Room Construction & Dual Polygons

Every constructed room maintains a strict dual-polygon representation:
1. `built_polygon`: Outer boundary of the room along the wall centerline or exterior perimeter.
2. `usable_polygon`: Inward-buffered interior polygon representing clear usable floor area inside finished walls.
   $$\text{Usable Offset} = -\frac{t_{\text{wall}}}{2}$$
3. `area_sqm`: Computed directly from `usable_polygon`.

---

## 5. Shape Construction

Constructed deterministically by `PolygonBuilder`:
- **Rectangular (`rectangular`)**: Constructed within the envelope of the assigned ASAA allocated region. Supports automatic 90° orientation alignment if the LLM's $(w, l)$ aspect ratio matches the $(l, w)$ orientation of the region.
- **Square (`square`)**: Side $s = \sqrt{\text{area}}$, centered or aligned within the region.
- **L-Shaped (`l_shaped`)**: 6-vertex orthogonal polygon formed by removing a quadrant cutout. If the ASAA allocated region is already 6-vertex L-shaped, it is realized directly.

---

## 6. Wall Generation & Deduplication

Implemented in `WallBuilder`:
- Iterates over all room boundary segments.
- Detects shared wall segments between adjacent rooms using Shapely intersection.
- Deduplicates shared walls: exactly **one** `GeoWall` of type `"interior"` is constructed, referencing both adjacent room IDs.
- Unshared boundary segments become `"exterior"` walls.
- Generates 2D footprint polygons for each wall using specified thickness ($t_{\text{ext}} = 0.20\text{m}$, $t_{\text{int}} = 0.15\text{m}$).

---

## 7. Door Construction & Swing Arcs

Implemented in `DoorBuilder`:
- Realizes `DoorIntent` into physical `GeoDoor`.
- **Interior doors**: Placed on shared partition walls between source and target rooms.
- **Entrance & Balcony doors**: Placed on exterior walls of the source room.
- Computes door center position along the wall segment.
- Constructs deterministic 90° circular sector polygon from the hinge point representing door swing clearance.
- Raises `DoorPlacementError` if two rooms requesting a direct connection are non-adjacent.

---

## 8. Window Construction

Implemented in `WindowBuilder`:
- Realizes `WindowIntent` into physical `GeoWindow`.
- Filters room walls for exterior walls matching `window_intent.wall_orientation`.
- If requested orientation is available, centers window on that wall; falls back to other exterior walls of the room if the requested orientation wall is too narrow.
- Raises `WindowPlacementError` if the room has no exterior walls.

---

## 9. Corridor & Staircase Geometry

- **Corridors** (`CorridorBuilder`): Converts ASAA circulation regions into physical `GeoRoom(is_corridor=True, room_type="circulation")` with inward usable buffer.
- **Staircases** (`StaircaseBuilder`): Realizes `StaircaseIntent` inside the locked ASAA staircase region. Computes riser count (e.g. 16 risers) and tread depth (0.28m), maintaining identical $(x, y)$ coordinates across floors.

---

## 10. Irregular Plots & Non-Bounding-Box Handling

- True polygonal boundaries are fully preserved without bounding-box substitution.
- L-shaped and irregular plots maintain their exact coordinate vertices in `plot_polygon` and `buildable_polygon`.
- Rooms and walls follow the actual polygonal boundaries.

---

## 11. Determinism & Traceability

- Identical `ArchitecturalDesignSet` + `AllocationSet` produces bitwise-identical geometry coordinates. Zero uncontrolled randomness is used.
- Full end-to-end traceability is preserved:
  - `GeoRoom.architectural_room_id` $\to$ `RoomDesign.id`
  - `GeoDoor.intent_id` $\to$ `DoorIntent.id`
  - `GeoWindow.intent_id` $\to$ `WindowIntent.id`
  - `GeoStaircase.intent_id` $\to$ `StaircaseIntent.id`
  - `GeoWall.room_ids` $\to$ List of adjacent `GeoRoom.id`s

---

## 12. Structured Error Handling

The Geometry Engine defines a comprehensive exception hierarchy in `app.geometry.exceptions`:
- `GeometryConstructionError`
  - `InvalidRoomGeometryError`: Degenerate or self-intersecting polygon.
  - `RoomOutOfBoundsError`: Room extends outside allocated region.
  - `ImpossibleDimensionsError`: Requested dimensions exceed region envelope.
  - `InvalidShapeParametersError`: Inconsistent shape cutouts.
  - `DoorPlacementError`: Door cannot be physically placed (e.g. non-adjacent rooms).
  - `WindowPlacementError`: Window cannot be placed on exterior wall.
  - `StaircaseConstructionError`: Staircase core missing or too narrow.
  - `CorridorConstructionError`: Degenerate circulation region.

---

## 13. Previous Project Reuse Assessment

| Old Component | New Component | Decision | Rationale |
|---|---|---|---|
| `geometry/polygon.py` | `geometry_utils.py` | REUSED | Shapely polygon conversion, validation, and measurement utilities ported cleanly. |
| `geometry/walls.py` | `room_builder.py` | REUSED & MODIFIED | Buffer-based usable vs. built polygon offset concept reused; decoupled from ASAA. |
| `geometry/doors.py` | `door_builder.py` | REUSED & MODIFIED | Swing arc geometry math reused; auto-decision logic stripped in favor of `DoorIntent`. |
| `src/asaa/candidate_generator.py` | `polygon_builder.py` | REWRITTEN | Converted from ASAA-internal candidate loop to deterministic intent realization. |
| `src/geometry/staircase.py` (None in old) | `staircase_builder.py` | NEW | Old project lacked dedicated staircase geometry; built fresh. |
| `src/geometry/windows.py` (None in old) | `window_builder.py` | NEW | Old project had no window realization; built fresh. |

---

## 14. Phase 7 (Validator) Handoff

The Geometry Engine completes Phase 6 by delivering assembled `FloorPlanSet` instances with physical coordinates.
It does **not** evaluate pass/fail criteria, calculate compliance scores, or trigger refinement loops.
Phase 7 (Validator) will independently consume these physical geometries to perform deterministic verification.

# Architectural LLM Designer — Technical Specification

## 1. Purpose
The Architectural LLM Designer represents Stage 4 of the PlanForge AI pipeline. Its sole responsibility is to answer **HOW** allocated spatial regions should be designed into architectural rooms.

ASAA has already determined **WHERE** spaces are allocated (`AllocatedRegion`). The Architectural LLM decides the internal architectural layout, semantic shapes, proportions, dimensions, door intents, window intents, and architectural rationales within the assigned ASAA spatial regions.

---

## 2. Input Contracts
The Architectural LLM receives an immutable `ArchitecturalContext` payload constructed by `ContextBuilder` (`app/agents/architectural_agent/context.py`):
- `project_name`: Name of the architectural project.
- `global_constraints`: Plot dimensions, plot orientation, setbacks.
- `floors`: Tuple of `FloorDesignContext` objects:
  - `floor_number`, `floor_name`.
  - `rooms`: List of `RoomDesignContext` objects containing:
    - `room_id`, `room_type`, `floor_number`, `priority`, `category`.
    - `target_area_sqm`, `min_area_sqm`, `max_area_sqm`.
    - `allocated_region_id`: Traceable foreign key to ASAA's `AllocatedRegion.id`.
    - `allocated_area_sqm`: Authoritative allocated area in m².
    - `approximate_dimensions`: `(width, length)` in meters.
    - `adjacent_region_ids` and `adjacent_room_types`: Touching spatial neighbors.
    - `user_required_adjacencies`: Explicit user connections.
    - `system_preferred_adjacencies`: Inferred architectural preferences.
    - `avoid_rooms`: Separation requirements.
    - `attached_to_room_id`: Parent suite ID (e.g. for ensuite bathrooms).
  - `circulation_zones`, `circulation_notes`.
  - `entrance_intent`: Facing direction and preferred access room.
  - `staircase_intent` and `staircase_region_id`.

---

## 3. ASAA Interaction & Spatial Authority
ASAA spatial allocations are **authoritative**:
- The Architectural LLM is prohibited from moving rooms between allocated regions.
- The Architectural LLM is prohibited from moving rooms to different floors.
- The Architectural LLM cannot alter the position or centroid of an allocated region.
- If an allocation is architecturally awkward, the LLM records this in its rationale; it does not silently rewrite the spatial partition.

---

## 4. Output Contract
The Architectural LLM outputs an `ArchitecturalDesignSet` (`app/models/architectural_design.py`):
- `id`: Unique identifier.
- `allocation_set_id`: Foreign key referencing ASAA's `AllocationSet.id`.
- `designs`: List of `ArchitecturalDesign` objects (one per floor):
  - `id`, `floor_number`, `floor_name`.
  - `allocation_id`: Foreign key referencing ASAA's `Allocation.id`.
  - `rooms`: List of `RoomDesign` objects:
    - `id`: Unique room design proposal ID.
    - `room_type`: Canonical room type.
    - `allocated_region_id`: Reference to ASAA's `AllocatedRegion.id`.
    - `floor_number`: Assigned floor.
    - `intended_shape`: Semantic descriptor (`"rectangular"`, `"square"`, `"l_shaped"`, `"custom"`).
    - `intended_dimensions`: Optional `(width, length)` in meters.
    - `intended_area_sqm`: Proposed interior area in m².
    - `doors`: List of `DoorIntent` objects.
    - `windows`: List of `WindowIntent` objects.
    - `connected_spaces`: List of target connected room types or circulation zones.
    - `design_rationale`: Structured reasoning string.
  - `staircase_intent`: Proposed `StaircaseIntent` for vertical circulation.
  - `design_rationale`: Overall floor design summary.

---

## 5. Room Design & Proportions
For each room, the LLM determines:
- Primary functional orientation and aspect ratio.
- Internal proportions matching habitable function (e.g. rectangular for living and bedrooms, compact square/rectangular for bathrooms and kitchens).
- Proposed width and length matching the allocated area budget.

---

## 6. Semantic Shape Representation
The LLM describes room shapes using high-level semantic descriptors rather than arbitrary coordinate arrays:
- `"rectangular"`: Standard 4-corner room with width and length.
- `"square"`: Balanced 1:1 proportion.
- `"l_shaped"`: L-shaped room (e.g. for open living-dining or wrapped suites).
- `"custom"`: Other non-standard shapes.

Detailed geometric construction (usable polygons, wall offsets, built polygons) is strictly deferred to the Geometry Engine (Phase 6).

---

## 7. Dimension Handling & Bounds
- Proposed dimensions must be positive ($w > 0, l > 0$).
- Proposed area must not exceed the ASAA allocated region area ($\text{intended\_area\_sqm} \le \text{allocated\_area\_sqm} \times 1.05$).
- Proposed area must not violate explicit user minimum area ($\text{intended\_area\_sqm} \ge \text{min\_area\_sqm} - 0.2$).
- Exceeding dimensions trigger `DimensionExceedsAllocationError`.

---

## 8. Door Intent (`DoorIntent`)
The LLM proposes door placement intent:
- `connects_from`: Source room ID.
- `connects_to`: Target room ID, room type, or `"circulation"`.
- `wall_orientation`: Optional facade wall (`"north"`, `"south"`, `"east"`, `"west"`).
- `door_type`: `"interior"`, `"entrance"`, `"balcony"`, `"pocket"`.
- `recommended_width`: Width in meters (default 0.9m for rooms, 1.0m for entrance).
- `recommended_height`: Height in meters (default 2.1m).
- `rationale`: Architectural reason for placement.

The LLM does **NOT** generate door cutouts, door polygons, or swing arc geometry.

---

## 9. Window Intent (`WindowIntent`)
The LLM proposes window placement intent:
- `room_id`: Room ID receiving natural light/ventilation.
- `wall_orientation`: External wall orientation (`"north"`, `"south"`, `"east"`, `"west"`).
- `window_type`: `"standard"`, `"bay"`, `"skylight"`, `"ventilation"`.
- `recommended_width`: Width in meters (e.g. 1.2m–2.0m for living, 0.8m for bathroom).
- `recommended_height`: Height in meters (e.g. 1.2m–1.5m).
- `sill_height`: Sill height above floor (e.g. 0.9m standard, 1.4m ventilation).
- `rationale`: Daylight and cross-ventilation intent.

The LLM does **NOT** generate physical wall openings or window frame polygons.

---

## 10. Local Connections (Direct vs. Circulation)
- **Direct Connection**: Rooms sharing physical adjacency and intended for direct access (e.g. Living $\leftrightarrow$ Dining).
- **Circulation Connection**: Rooms accessing common circulation corridors or foyers (e.g. Bedroom $\leftrightarrow$ Corridor).
- **Ensuite Connection**: Attached bathroom connected directly to master bedroom suite.

---

## 11. Attached Rooms
Attached bathrooms and walk-in closets are directly coupled to their parent suite:
- `attached_to_room_id` in context links the ensuite to the master bedroom.
- Direct `DoorIntent` connecting the parent room to the attached room.
- Prohibited from moving the attached room outside its allocated region.

---

## 12. Multi-Floor Handling
- Each floor is designed independently within its allocated boundary.
- Room identities and floor numbers are strictly preserved.
- Staircase cores are coordinated across floors via `StaircaseIntent` referencing the locked ASAA staircase zone (`allocated_region_id`).

---

## 13. LLM Provider Abstraction
Implemented in `app/llm/`:
- `LLMClient` protocol defining `generate(prompt: str, system_prompt: Optional[str]) -> str`.
- `MockLLMClient`: In-memory deterministic mock client for offline testing.
- `HuggingFaceClient`: HTTP client connecting to Hugging Face Serverless Inference API (e.g. DeepSeek-R1-Distill-Qwen-7B).
- `LLMConfig`: Configuration model (`provider`, `model_name`, `temperature`, `timeout_seconds`, `api_base_url`, `api_key`).
- `create_llm_client`: Factory returning configured client.

---

## 14. Mock Testing Strategy
- Unit and integration tests run entirely against `MockLLMClient`.
- Zero external network calls or LLM daemon requirements during test execution.
- Deterministic mock generator produces valid structured architectural designs matching prompt inputs.

---

## 15. Schema Validation & Error Handling
Implemented in `ArchitecturalOutputValidator` (`app/agents/architectural_agent/structured_output.py`):
- `MalformedLLMResponseError`: Invalid JSON or missing `'rooms'` list.
- `RoomCoverageError`: Missing rooms or invented rooms.
- `AllocationMismatchError`: Citing wrong `allocated_region_id` or `floor_number`.
- `DimensionExceedsAllocationError`: Dimensions exceeding allocation or non-positive.
- `InvalidShapeError`: Unsupported shape type.

---

## 16. Explainability
Every proposed room carries a `design_rationale` explaining:
- Why the shape was chosen.
- Why doors connect to specific spaces.
- Why windows face particular compass directions.

---

## 17. No-Invention Rule
- The Architectural LLM must account for **all** rooms provided by ASAA.
- The Architectural LLM must **never** invent additional rooms.
- The Architectural LLM must **never** drop requested rooms.

---

## 18. Architectural Boundaries
- **ASAA**: WHERE (spatial partitions, bounding regions).
- **Architectural LLM**: HOW (shapes, dimensions, door/window intent, rationales).
- **Geometry Engine**: CONSTRUCT (walls, exact cutouts, swing arcs, polygons).
- **Validator**: VERIFY (authoritative checks).

---

## 19. Previous-Project Component Reuse
- **Reused**: Model configuration concepts, structured JSON prompt patterns, response parsing heuristics.
- **Rejected**: Bypassing ASAA, direct geometry construction inside the LLM agent, hardcoded regex parsers masquerading as LLMs, and unvalidated self-approval.

---

## 20. Limitations
- Curved or organic architectural wall shapes are not supported in the semantic schema (focus is on orthogonal and L-shaped forms).
- Sizing recommendations are indicative intents subject to downstream wall-thickness buffering in Phase 6.

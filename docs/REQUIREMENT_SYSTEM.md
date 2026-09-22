# PlanForge — Requirement System (Phase 2)

This document is the authoritative specification and user guide for the **Requirement System** (Phase 2) in PlanForge.

---

## 1. Responsibilities & Pipeline Overview

The Requirement Agent's sole responsibility is: **UNDERSTAND WHAT THE USER WANTS**.

It converts unstructured natural language briefs into structured, normalized, validated `Requirements` objects without inventing requirements or deciding layout geometry.

```
RAW USER INPUT
      ↓
INPUT PARSING (RequirementParser)
      ↓
STRUCTURED REQUIREMENTS (Requirements, FloorRequirement, RoomRequirement)
      ↓
NORMALIZATION (RequirementNormalizer)
      ↓
COMPLETENESS CHECK & MULTI-FLOOR GATING (CompletenessGate)
      ↓
REQUIREMENT VALIDATION (RequirementValidator)
      ↓
READY FOR PLANNING (Planning-compatible Output)
```

---

## 2. Core Rule: Absolute Non-Invention Guarantee

The system **never silently invents user requirements**.

- If the user specifies $N$ floors (e.g. "two-floor house") but only specifies rooms for Floor 1:
  - The system creates a shell `FloorRequirement` for Floor 2 with `room_requirements=[]`.
  - The `CompletenessGate` reports `is_complete=False` with `missing_floors=[2]`.
  - The system generates structured clarification questions asking what rooms belong on Floor 2.
  - The system does **not** inject default master bedrooms, bedrooms, study rooms, or bathrooms.
- System suggestions are strictly opt-in and non-binding:
  - If `allow_suggestions=True` is provided (e.g. user explicitly requests or authorizes suggestions), candidate options are provided in `suggestions`, but the `Requirements` data model remains unmutated until user approval.

---

## 3. Supported Input Types & Extraction Rules

### 3.1. Plot Extraction
- **Linear Dimensions**:
  - `15m x 20m`, `15 x 20`, `15 by 20`, `15 × 20`, `15*20`
  - `30 feet by 40 feet`, `30ft x 40ft`, `25' x 50'`
  - Normalized to width and depth in SI metres.
- **Gross Area**:
  - `250 sqm`, `2000 sqft`, `5 marla`, `1 kanal`, `0.5 acres`, `1 hectare`.
  - Derived from width $\times$ depth when dimensions exist, or extracted standalone.
- **Polygon Boundaries**:
  - Vertex coordinates: `(0, 0), (15, 0), (15, 20), (0, 20)`.
- **Orientation**:
  - `north-facing`, `facing east`, `southwest facing plot`.
  - Standardized to lowercase cardinal directions (`north`, `south`, `east`, `west`, `northeast`, `northwest`, `southeast`, `southwest`).
- **Setbacks**:
  - `front setback 3m`, `rear setback 2m`, `left setback 1.5m`, `setback of 1m on right`.
- **Main Entrance**:
  - Facing direction: `entrance from north`, `main entrance facing east`.
  - Preferred entry room: `entrance leads to living room`, `entry connects to foyer`.

### 3.2. Floor Counts & Headers
- **Floor Counts**:
  - `G+1` $\rightarrow$ 2 floors, `G+2` $\rightarrow$ 3 floors.
  - `single storey` $\rightarrow$ 1 floor, `two-storey` / `double storey` / `two-floor` $\rightarrow$ 2 floors.
  - `3 floors`, `4 storeys`.
- **Floor Section Splitting**:
  - `Ground Floor:`, `Floor 1:`, `1st Floor:`, `First Floor:`.
  - `Floor 2:`, `2nd Floor:`, `Second Floor:`, `Upper Floor:`, `Upstairs:`.
  - `Floor 3:`, `3rd Floor:`, `Third Floor:`.
  - Content before the first explicit floor header is preserved as Floor 1 (avoiding discarded rooms bug).

### 3.3. Rooms, Counts, and BHK Expansion
- **Room Types**: Canonical mapping covering social, private, service, and circulation spaces.
- **Counts**: Word numbers (`one`, `two`, `three`, `a`, `an`) and digits.
- **BHK Shorthand**:
  - `3BHK` $\rightarrow$ 3 bedrooms, 1 living room, 1 kitchen.
  - `2BHK` $\rightarrow$ 2 bedrooms, 1 living room, 1 kitchen.

### 3.4. Room Area Isolation (No Area Bleeding)
- Room areas are extracted strictly within their isolated clause/line:
  - `Master bedroom 150 sq ft\nBedroom 120 sq ft\nStudy 80 sq ft` correctly assigns 150 sq ft to master bedroom, 120 sq ft to bedroom, and 80 sq ft to study.
- **Area Range Support**:
  - `Living room between 200 and 300 sq ft` $\rightarrow$ `min_area_sqm`, `max_area_sqm`, `preferred_area_sqm`.
  - `Kitchen min 100 sq ft` $\rightarrow$ `min_area_sqm`.
  - `Dining max 150 sq ft` $\rightarrow$ `max_area_sqm`.

### 3.5. Relationships
- **Adjacency**: `kitchen next to dining`, `living adjacent to entrance`.
- **Separation**: `garage away from bedroom`, `toilet separated from kitchen`.
- **Attached Rooms**: `master bedroom with attached bathroom` $\rightarrow$ sets `attached_to="master_bedroom"` and establishes adjacency.
- **Circulation & Staircase**:
  - Automatic staircase requirement when `target_floors > 1` or explicit mention (`internal stairs`).

---

## 4. Normalization Rules

`RequirementNormalizer` ensures uniform terminology:

| Raw Token | Canonical Room Type |
|---|---|
| `bed`, `bedroom`, `bed rooms`, `guest room`, `kids room` | `bedroom` |
| `master bed`, `master bedroom`, `primary bedroom` | `master_bedroom` |
| `washroom`, `toilet`, `wc`, `bath room`, `powder room`, `attached bath` | `bathroom` |
| `lounge`, `drawing room`, `living room`, `sitting room` | `living` |
| `dining`, `dining room`, `dining area` | `dining` |
| `kitchen`, `kitchenette`, `open kitchen` | `kitchen` |
| `study`, `study room`, `home office`, `library` | `study` |
| `storage`, `store`, `store room`, `storeroom`, `utility` | `storage` |
| `foyer`, `hallway`, `corridor`, `passage`, `entry` | `circulation` |

Floor labels are consistently mapped:
- `ground`, `ground floor`, `first floor`, `1st floor`, `floor 1` $\rightarrow$ `1`
- `second floor`, `2nd floor`, `floor 2`, `upper floor`, `upstairs` $\rightarrow$ `2`
- `third floor`, `3rd floor`, `floor 3` $\rightarrow$ `3`

---

## 5. Completeness & Gating

The `CompletenessGate` outputs a `CompletenessResult` with status:
- `COMPLETE`: Plot, target floors, and rooms for all floors are present.
- `INCOMPLETE`: Missing plot, target floors, or floor room specifications.
- `AMBIGUOUS`: Conflicting or contradictory requirements.
- `INVALID`: Unphysical parameters (e.g. non-positive dimensions).

---

## 6. Semantic Validation

`RequirementValidator` verifies:
- Positive plot width, depth, and area.
- Non-negative setbacks; combined setbacks less than plot dimensions.
- Positive room areas with `min_area <= preferred_area <= max_area`.
- Room counts $\ge 1$ and `max_count >= min_count`.
- Sequential floor numbers starting at 1.
- Relationship sanity (no self-adjacency, no self-separation, no conflicting adjacency + separation).
- Valid cardinal directions for orientation and entrance.

---

## 7. Known Previous Bugs Resolved

1. **Ordinal Floor Parsing Crash**: Fixed regex handling of `1st floor`, `2nd floor`, `3rd floor`.
2. **Room Area Bleeding**: Fixed line/clause scoping and span overlap prevention so room areas remain isolated to their respective rooms.
3. **Missing Floor 1 Header Dropping Rooms**: Preserves unheaded initial room descriptions as Floor 1.
4. **Silent Floor 2 Room Invention (`default_f2`)**: Completely eliminated; missing floors gate planning and generate clarification requests.
5. **Default Room Injections**: Minimal prompts only contain user-specified rooms.
6. **Apostrophe Dimension Parsing**: Corrected `parse_dimension_m` pattern in `app/utils/units.py` for values like `30'`.

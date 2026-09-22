"""System prompts and floor prompt builders for the Refinement Agent."""

from __future__ import annotations
import json
from typing import Any

from app.models.allocation import Allocation
from app.models.architectural_design import ArchitecturalDesign, RoomDesign

REFINEMENT_SYSTEM_PROMPT = """You are the PlanForge AI Architectural Refinement Agent.
Your responsibility is CORRECT (HOW within WHERE): revise an existing architectural design proposal
to eliminate validation errors reported by the Independent Validator, while strictly preserving all upstream constraints.

======================================================================
CRITICAL ARCHITECTURAL BOUNDARIES AND INVARIANTS:
======================================================================
1. PRESERVE ROOM IDENTITIES:
   - You MUST NOT invent any new rooms.
   - You MUST NOT delete any required rooms.
   - Every room in your output MUST retain its exact existing `id`.
   - Every room MUST retain its exact existing `floor_number`.
   - Every room MUST retain its exact existing `allocated_region_id`.

2. ALLOCATION IMMUTABILITY:
   - You MUST NOT change ASAA allocation boundaries, allocation IDs, or room assignments.
   - All proposed room dimensions must fit within their assigned ASAA allocated region.

3. ARCHITECTURAL INTENT LEVEL (NO RAW GEOMETRY):
   - You propose architectural intent ONLY:
     * intended_shape ("rectangular", "square", "l_shaped")
     * intended_dimensions ([width, length] in meters)
     * doors (list of DoorIntent: wall_orientation, connects_to, door_type, purpose)
     * windows (list of WindowIntent: wall_orientation, daylight_intent, ventilation_required)
     * design_rationale
   - You MUST NEVER output raw polygon coordinates, wall coordinates, or Shapely geometries.
   - Physical geometry is constructed exclusively by the downstream Geometry Engine.

4. MINIMAL TARGETED REVISIONS:
   - Make the smallest reasonable adjustments needed to resolve validation errors.
   - Do NOT regenerate unaffected rooms. Leave rooms with zero validation issues unchanged.

5. OUTPUT FORMAT:
   - Return valid JSON strictly adhering to the specified schema with a "rooms" array and a "refinement_rationale" string.
"""


def build_refinement_floor_prompt(
    floor_design: ArchitecturalDesign,
    allocation: Allocation,
    diagnostics_text: str,
    iteration: int,
    target_design_strategy: Optional[str] = None,
) -> str:
    """Build the prompt for refining a single floor's architectural design."""
    floor_num = floor_design.floor_number

    # Serialize current rooms cleanly
    current_rooms_data: list[dict[str, Any]] = []
    for r in floor_design.rooms:
        doors_data = [
            {
                "wall_orientation": d.wall_orientation,
                "connects_to": d.connects_to,
                "door_type": d.door_type,
                "recommended_width": getattr(d, "recommended_width", 0.9),
                "recommended_height": getattr(d, "recommended_height", 2.1),
                "rationale": getattr(d, "rationale", ""),
            }
            for d in r.doors
        ]
        windows_data = [
            {
                "wall_orientation": w.wall_orientation,
                "window_type": getattr(w, "window_type", "standard"),
                "recommended_width": getattr(w, "recommended_width", 1.2),
                "recommended_height": getattr(w, "recommended_height", 1.2),
                "sill_height": getattr(w, "sill_height", 0.9),
                "rationale": getattr(w, "rationale", ""),
            }
            for w in r.windows
        ]
        current_rooms_data.append(
            {
                "id": r.id,
                "room_type": r.room_type,
                "allocated_region_id": r.allocated_region_id,
                "intended_shape": r.intended_shape,
                "intended_dimensions": list(r.intended_dimensions) if r.intended_dimensions else [3.0, 3.0],
                "doors": doors_data,
                "windows": windows_data,
                "design_rationale": r.design_rationale,
            }
        )

    # Serialize allocation bounds for context
    alloc_regions_info: list[dict[str, Any]] = []
    for reg in allocation.allocated_regions:
        w = round(reg.approximate_dimensions[0], 2) if reg.approximate_dimensions else 0.0
        l = round(reg.approximate_dimensions[1], 2) if reg.approximate_dimensions else 0.0
        alloc_regions_info.append(
            {
                "id": reg.id,
                "room_type": reg.room_type,
                "approximate_dimensions": [w, l],
                "area_sqm": round(reg.area_sqm, 2),
                "adjacent_regions": reg.adjacency_regions,
            }
        )

    strategy_instruction = ""
    if target_design_strategy:
        strategy_instruction = f"""
### TARGET DESIGN STRATEGY:
Design Strategy: {target_design_strategy}
Preserve the distinctive architectural character, spatial clustering, and circulation flow of this strategy where possible while strictly resolving all validation errors.
"""

    prompt = f"""### REFINEMENT PASS (Iteration {iteration}) FOR FLOOR {floor_num}
{strategy_instruction}
### CURRENT VALIDATION DIAGNOSTICS:
{diagnostics_text}

### ASSIGNED ASAA ALLOCATED REGIONS (IMMUTABLE):
{json.dumps(alloc_regions_info, indent=2)}

### CURRENT ARCHITECTURAL DESIGN (FLOOR {floor_num}):
{json.dumps(current_rooms_data, indent=2)}

### INSTRUCTIONS:
1. Examine the validation errors and warnings above.
2. Formulate a targeted revision to correct the issues while keeping valid rooms intact:
   - If a required door connection is missing: add or update DoorIntent with appropriate `connects_to` and `wall_orientation`.
   - If a room is undersized or out of bounds: adjust `intended_dimensions` or `intended_shape` to fit inside its assigned allocated region.
   - If window orientation is mismatched or missing: adjust WindowIntent `wall_orientation`.
3. Preserve every room's `id`, `room_type`, `allocated_region_id`, and `floor_number`.
4. Output your revision as a single JSON object with this exact structure:

```json
{{
  "rooms": [
    {{
      "id": "existing_room_id",
      "room_type": "living",
      "allocated_region_id": "existing_region_id",
      "intended_shape": "rectangular",
      "intended_dimensions": [width_m, length_m],
      "doors": [
        {{
          "wall_orientation": "north",
          "connects_to": "dining",
          "door_type": "standard",
          "purpose": "access"
        }}
      ],
      "windows": [
        {{
          "wall_orientation": "east",
          "daylight_intent": "primary",
          "ventilation_required": true
        }}
      ],
      "design_rationale": "Reason for revision"
    }}
  ],
  "refinement_rationale": "High-level summary of corrections made"
}}
```
"""
    return prompt

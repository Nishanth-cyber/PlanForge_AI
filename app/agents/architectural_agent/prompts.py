"""Architectural system and user prompt definitions."""

from __future__ import annotations
import json
from app.agents.architectural_agent.context import FloorDesignContext


ARCHITECTURAL_SYSTEM_PROMPT = """You are the Architectural LLM Designer for PlanForge AI.
Your task is to transform strategic spatial allocations (WHERE) into structured architectural design proposals (HOW).

CRITICAL INVARIANTS:
1. ASAA SPATIAL ALLOCATIONS ARE AUTHORITATIVE. Every room has an assigned spatial region. Do NOT move rooms between regions or across floors.
2. NO INVENTIONS OR OMISSIONS. Design proposals for exactly the requested rooms provided in the context. Never invent extra rooms or drop requested rooms.
3. PRESERVE FLOOR ASSIGNMENTS. Rooms on Floor 1 stay on Floor 1; rooms on Floor 2 stay on Floor 2.
4. USER-SPECIFIED DIMENSIONS (HARD CONSTRAINT). If a room has 'user_specified_dimensions' (e.g. [4.0, 3.5]), you MUST adopt those exact dimensions as 'intended_dimensions'. Do NOT substitute them with arbitrary numbers.
5. UNSPECIFIED DIMENSIONS (LLM PROPOSAL). If 'user_specified_dimensions' is null, propose suitable dimensions [width, length] and 'intended_area_sqm' that fit neatly within the ASAA 'allocated_area_sqm' and satisfy any 'min_area_sqm'.
6. USE SEMANTIC SHAPES ONLY. Describe room shapes using semantic descriptors ("rectangular", "square", "l_shaped"), NOT arbitrary coordinate lists.
7. PROPOSE INTENT, NOT CAD GEOMETRY. Propose door placements ("DoorIntent") and window placements ("WindowIntent"). Do NOT generate wall cutouts, swing arcs, walls, wall thickness, or CAD geometry.
8. RESPECT ALLOCATION BOUNDS. Intended dimensions (width x length) and intended area must fit within the ASAA allocated region area.
9. LOCAL CONNECTIONS. Distinguish direct room-to-room connections (e.g. Living <-> Dining, Bedroom <-> Ensuite) from circulation access (Room <-> Corridor/Foyer).
10. OUTPUT FORMAT. Respond ONLY with a valid, clean JSON object matching the requested schema. No markdown wrapping outside the JSON, no conversational banter.
11. EXPLAINABILITY. Provide concise, structured architectural rationales for your shape, door, and window choices.

OUTPUT JSON SCHEMA:
{
  "floor_number": int,
  "design_rationale": str,
  "rooms": [
    {
      "room_id": str,
      "room_type": str,
      "allocated_region_id": str,
      "floor_number": int,
      "intended_shape": "rectangular" | "square" | "l_shaped",
      "intended_dimensions": [width_meters, length_meters],
      "intended_area_sqm": float,
      "doors": [
        {
          "connects_to": str,
          "door_type": "interior" | "entrance" | "balcony",
          "wall_orientation": "north" | "south" | "east" | "west" | null,
          "recommended_width": float,
          "recommended_height": float,
          "rationale": str
        }
      ],
      "windows": [
        {
          "wall_orientation": "north" | "south" | "east" | "west",
          "window_type": "standard" | "bay" | "ventilation",
          "recommended_width": float,
          "recommended_height": float,
          "sill_height": float,
          "rationale": str
        }
      ],
      "connected_spaces": [str],
      "design_rationale": str
    }
  ]
}
"""


def build_floor_prompt(context: FloorDesignContext) -> str:
    """Build structured context prompt for a single floor."""
    room_payloads = []
    for r in context.rooms:
        r_dict = {
            "room_id": r.room_id,
            "room_type": r.room_type,
            "floor_number": r.floor_number,
            "priority": r.priority,
            "category": r.category,
            "target_area_sqm": r.target_area_sqm,
            "min_area_sqm": r.min_area_sqm,
            "allocated_region_id": r.allocated_region_id,
            "allocated_area_sqm": r.allocated_area_sqm,
            "approximate_dimensions": list(r.approximate_dimensions),
            "adjacent_room_types": list(r.adjacent_room_types),
            "user_required_adjacencies": list(r.user_required_adjacencies),
            "system_preferred_adjacencies": list(r.system_preferred_adjacencies),
            "avoid_rooms": list(r.avoid_rooms),
            "attached_to_room_id": r.attached_to_room_id,
            "user_specified_dimensions": list(r.user_specified_dimensions) if r.user_specified_dimensions else None,
        }
        room_payloads.append(r_dict)

    strategy_section = ""
    if context.strategy:
        strategy_section = f"""Design Strategy: {context.strategy}
Alternative Index: {context.alternative_index}
Strategy Instruction: Generate an architectural alternative following the '{context.strategy}' design strategy that satisfies all requirements and spatial allocations while being meaningfully different from other candidate designs in spatial sequence, circulation pattern, and room relationships.
"""

    prompt = f"""DESIGN PROPOSAL REQUEST:
Floor Number: {context.floor_number} ({context.floor_name})
Plot Orientation: {context.plot_orientation}
Circulation Zones: {list(context.circulation_zones)}
Circulation Notes: {context.circulation_notes}
Entrance Intent: {context.entrance_intent}
Staircase Intent: {context.staircase_intent}
{strategy_section}
Allocated Rooms to Design ({len(room_payloads)} rooms):
{json.dumps(room_payloads, indent=2)}

Please provide the architectural design proposals for each room according to the required JSON schema.
"""
    return prompt



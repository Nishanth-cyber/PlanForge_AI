"""Intelligent Edit Intent Detection for PlanForge AI.

Distinguishes between:
- EDIT_DESIGN: General modifications to existing floor plan.
- ADD_ELEMENT: Adding rooms, doors, windows, balconies, or openings.
- REMOVE_ELEMENT: Removing rooms, doors, windows, or walls.
- MODIFY_DIMENSIONS: Changing room dimensions, width, length, or area.
- MODIFY_LAYOUT: Changing spatial layout, adjacency, or positions.
- MODIFY_OPENINGS: Updating doors, windows, or orientations.
- MODIFY_SHAPE: Changing shape (e.g., L-shaped, rectangular, square).
- CLARIFICATION_REQUIRED: Ambiguous or underspecified modifications.
- NEW_DESIGN: Explicitly starting a new design from scratch.

Technical classification labels are never shown to the user; intent is handled internally.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class EditIntentType(str, Enum):
    """Internal fine-grained edit intent categories."""

    EDIT_DESIGN = "EDIT_DESIGN"
    ADD_ELEMENT = "ADD_ELEMENT"
    REMOVE_ELEMENT = "REMOVE_ELEMENT"
    MODIFY_DIMENSIONS = "MODIFY_DIMENSIONS"
    MODIFY_LAYOUT = "MODIFY_LAYOUT"
    MODIFY_OPENINGS = "MODIFY_OPENINGS"
    MODIFY_SHAPE = "MODIFY_SHAPE"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    NEW_DESIGN = "NEW_DESIGN"


@dataclass
class EditIntentResult:
    """Outcome of edit intent detection."""

    intent: EditIntentType
    confidence: float
    target_room_type: Optional[str] = None
    target_element_type: Optional[str] = None  # "door", "window", "room", "entrance", "staircase"
    requested_changes: Dict[str, Any] = field(default_factory=dict)
    clarification_question: Optional[str] = None
    rationale: str = ""


# ---------------------------------------------------------------------------
# Regex Patterns
# ---------------------------------------------------------------------------

_NEW_DESIGN_PATTERNS = re.compile(
    r"\b(?:"
    r"new\s+(?:project|design|plan|house)|"
    r"start\s+(?:over|fresh|from\s+scratch|a\s+new)|"
    r"restart\s+(?:from\s+scratch|the\s+project)?|"
    r"discard\s+(?:this|everything|current)|"
    r"create\s+(?:a\s+)?new\s+(?:design|plan|project)|"
    r"generate\s+(?:a\s+)?new\s+(?:design|plan|project)\s+from\s+scratch"
    r")\b",
    re.I,
)

_ROOM_TYPES = [
    ("master_bedroom", r"\b(?:master\s+bed\s?room|master\s+bed|master)\b"),
    ("bedroom", r"\b(?:bed\s?rooms?|guest\s+bed\s?room|kids?\s+bed\s?room)\b"),
    ("living", r"\b(?:living(?:\s+room)?|hall|drawing\s+room|lounge|family\s+room)\b"),
    ("kitchen", r"\b(?:kitchen|cooking\s+area|pantry)\b"),
    ("dining", r"\b(?:dining(?:\s+room)?|eating\s+area)\b"),
    ("bathroom", r"\b(?:bath\s?rooms?|baths?|washrooms?|restrooms?|toilets?|powder\s+room|wc)\b"),
    ("study", r"\b(?:study(?:\s+room)?|home\s+office|office|library)\b"),
    ("pooja", r"\b(?:pooja(?:\s+room)?|prayer\s+room|mandir)\b"),
    ("balcony", r"\b(?:balcon(?:y|ies)|terrace|deck|patio)\b"),
    ("corridor", r"\b(?:corridor|hallway|passage|circulation)\b"),
    ("foyer", r"\b(?:foyer|entryway|entrance\s+lobby|vestibule)\b"),
    ("staircase", r"\b(?:stair(?:case)?s?|steps)\b"),
    ("utility", r"\b(?:utility(?:\s+room)?|laundry|storage|store\s?room)\b"),
]

_SHAPE_KEYWORDS = re.compile(
    r"\b(?:"
    r"l[- ]shaped?|square(?!\s+(?:meters?|metres?|feet|ft|m\b|yards?|inches?))|rectang(?:le|ular)|t[- ]shaped?|u[- ]shaped?|"
    r"proportions?|aspect\s+ratio|shape"
    r")\b",
    re.I,
)

_DIMENSION_KEYWORDS = re.compile(
    r"\b(?:"
    r"larg(?:er|est)|big(?:ger|gest)|small(?:er|est)|enlarge|expand|shrink|reduce|"
    r"widen|narrow|spacious|compact|increase(?:\s+the)?\s+area|decrease(?:\s+the)?\s+area|"
    r"dimensions?|size|sqm|sqft|square\s+meters?|square\s+feet|met(?:ers?|res?)\b"
    r")\b",
    re.I,
)

_NUMERIC_AREA = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:sqm|sq\.?\s*m|square\s+meters?|m2|m\u00b2)",
    re.I,
)

_NUMERIC_DIMENSIONS = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:x|\u00d7|by)\s*(\d+(?:\.\d+)?)\s*(?:m|meters?|ft|feet)?",
    re.I,
)

_WINDOW_KEYWORDS = re.compile(r"\bwindows?\b", re.I)
_DOOR_KEYWORDS = re.compile(r"\bdoors?\b", re.I)
_ENTRANCE_KEYWORDS = re.compile(r"\b(?:entrance|main\s+door|entry|entryway)\b", re.I)
_CIRCULATION_KEYWORDS = re.compile(r"\b(?:circulation|flow|hallway|corridor|passage|access)\b", re.I)

_ADD_VERBS = re.compile(r"\b(?:add|insert|include|put\s+in|install|introduce|create)\b", re.I)
_REMOVE_VERBS = re.compile(r"\b(?:remove|delete|eliminate|drop|get\s+rid\s+of|take\s+out|scrap)\b", re.I)
_MOVE_VERBS = re.compile(r"\b(?:move|shift|relocate|swap|switch|reposition|place|bring|push|put)\b", re.I)

_ORIENTATION_KEYWORDS = re.compile(
    r"\b(?:north|south|east|west|northeast|northwest|southeast|southwest)\s*(?:side|wall|facing)?\b",
    re.I,
)


def _extract_room_type(text: str) -> Optional[str]:
    """Identify the primary target room type in the text."""
    lower = text.lower()
    for rtype, pat in _ROOM_TYPES:
        if re.search(pat, lower):
            return rtype
    return None


def _extract_all_room_types(text: str) -> List[str]:
    """Identify all room types mentioned in text."""
    lower = text.lower()
    found: List[str] = []
    for rtype, pat in _ROOM_TYPES:
        if re.search(pat, lower) and rtype not in found:
            found.append(rtype)
    return found


def _extract_orientation(text: str) -> Optional[str]:
    """Extract cardinal orientation if mentioned."""
    m = _ORIENTATION_KEYWORDS.search(text.lower())
    if m:
        val = m.group(0).strip().lower()
        for base in ["northwest", "northeast", "southwest", "southeast", "north", "south", "east", "west"]:
            if base in val:
                return base
    return None


def detect_edit_intent(instruction: str, project_context: Optional[Dict[str, Any]] = None) -> EditIntentResult:
    """Classify user editing instruction and extract structured intent components.

    Args:
        instruction: Natural language edit instruction from the user.
        project_context: Optional structured snapshot of current project for grounding.

    Returns:
        EditIntentResult with classified intent type, affected elements, and parsed parameters.
    """
    clean = (instruction or "").strip()
    lower = clean.lower()

    if not clean:
        return EditIntentResult(
            intent=EditIntentType.CLARIFICATION_REQUIRED,
            confidence=0.9,
            clarification_question="What modification would you like to make to your floor plan?",
            rationale="empty_instruction",
        )

    # 1. Explicit request to restart or create a completely new design
    if _NEW_DESIGN_PATTERNS.search(lower):
        return EditIntentResult(
            intent=EditIntentType.NEW_DESIGN,
            confidence=0.98,
            rationale="explicit_new_design_requested",
        )

    room_type = _extract_room_type(clean)
    all_rooms = _extract_all_room_types(clean)
    orientation = _extract_orientation(clean)

    is_add = bool(_ADD_VERBS.search(lower))
    is_remove = bool(_REMOVE_VERBS.search(lower))
    is_move = bool(_MOVE_VERBS.search(lower))
    has_window = bool(_WINDOW_KEYWORDS.search(lower))
    has_door = bool(_DOOR_KEYWORDS.search(lower))
    has_entrance = bool(_ENTRANCE_KEYWORDS.search(lower))
    has_circ = bool(_CIRCULATION_KEYWORDS.search(lower))
    has_shape = bool(_SHAPE_KEYWORDS.search(lower))
    has_dims = bool(_DIMENSION_KEYWORDS.search(lower))

    # Area or dimension values
    area_match = _NUMERIC_AREA.search(lower)
    dim_match = _NUMERIC_DIMENSIONS.search(lower)

    # 2. Openings: Window modifications
    if has_window:
        if is_remove:
            return EditIntentResult(
                intent=EditIntentType.REMOVE_ELEMENT,
                confidence=0.95,
                target_room_type=room_type,
                target_element_type="window",
                requested_changes={"orientation": orientation},
                rationale="remove_window",
            )
        if is_add:
            return EditIntentResult(
                intent=EditIntentType.ADD_ELEMENT,
                confidence=0.95,
                target_room_type=room_type,
                target_element_type="window",
                requested_changes={"orientation": orientation},
                rationale="add_window",
            )
        return EditIntentResult(
            intent=EditIntentType.MODIFY_OPENINGS,
            confidence=0.9,
            target_room_type=room_type,
            target_element_type="window",
            requested_changes={"orientation": orientation},
            rationale="modify_window",
        )

    # 3. Openings: Door modifications
    if has_door:
        connects_to = None
        if len(all_rooms) >= 2:
            connects_to = all_rooms[1]
        elif "exterior" in lower or "outside" in lower:
            connects_to = "exterior"
        elif "circulation" in lower or "corridor" in lower or "hallway" in lower:
            connects_to = "circulation"

        if is_remove:
            return EditIntentResult(
                intent=EditIntentType.REMOVE_ELEMENT,
                confidence=0.95,
                target_room_type=room_type,
                target_element_type="door",
                requested_changes={"connects_to": connects_to, "orientation": orientation},
                rationale="remove_door",
            )
        if is_add:
            return EditIntentResult(
                intent=EditIntentType.ADD_ELEMENT,
                confidence=0.95,
                target_room_type=room_type,
                target_element_type="door",
                requested_changes={"connects_to": connects_to, "orientation": orientation},
                rationale="add_door",
            )
        return EditIntentResult(
            intent=EditIntentType.MODIFY_OPENINGS,
            confidence=0.9,
            target_room_type=room_type,
            target_element_type="door",
            requested_changes={"connects_to": connects_to, "orientation": orientation},
            rationale="modify_door",
        )

    # 4. Entrance modifications (e.g. "Move the entrance to the east side")
    if has_entrance:
        return EditIntentResult(
            intent=EditIntentType.MODIFY_LAYOUT,
            confidence=0.95,
            target_element_type="entrance",
            requested_changes={"orientation": orientation or "east"},
            rationale="modify_entrance_position",
        )

    # 5. Dimensions and Area modifications with numeric values (e.g. "Increase kitchen to 15 square meters", "10x12 m")
    if area_match or dim_match:
        changes: Dict[str, Any] = {}
        if area_match:
            changes["target_area_sqm"] = float(area_match.group(1))
        elif dim_match:
            changes["intended_dimensions"] = (float(dim_match.group(1)), float(dim_match.group(2)))
        return EditIntentResult(
            intent=EditIntentType.MODIFY_DIMENSIONS,
            confidence=0.96,
            target_room_type=room_type,
            target_element_type="room",
            requested_changes=changes,
            rationale="modify_dimensions_numeric",
        )

    # 6. Room Shape modifications (e.g. "Change the living room to an L-shaped design")
    if has_shape:
        target_shape = "l_shaped" if "l[- ]shape" in lower or "l-shaped" in lower or "l shaped" in lower else "rectangular"
        if "square" in lower and not re.search(r"square\s+(?:meters?|metres?|feet|ft|m\b)", lower):
            target_shape = "square"
        return EditIntentResult(
            intent=EditIntentType.MODIFY_SHAPE,
            confidence=0.95,
            target_room_type=room_type,
            target_element_type="room",
            requested_changes={"intended_shape": target_shape},
            rationale=f"modify_room_shape_to_{target_shape}",
        )

    # 6. Dimensions and Area modifications (e.g. "Make the master bedroom larger", "Increase kitchen to 15 sqm")
    if has_dims or area_match or dim_match or "spacious" in lower:
        changes: Dict[str, Any] = {}
        if area_match:
            changes["target_area_sqm"] = float(area_match.group(1))
        elif dim_match:
            changes["intended_dimensions"] = (float(dim_match.group(1)), float(dim_match.group(2)))
        elif "larger" in lower or "bigger" in lower or "expand" in lower or "enlarge" in lower or "spacious" in lower:
            changes["scale_factor"] = 1.25  # 25% increase
        elif "smaller" in lower or "reduce" in lower or "shrink" in lower or "compact" in lower:
            changes["scale_factor"] = 0.85  # 15% decrease

        return EditIntentResult(
            intent=EditIntentType.MODIFY_DIMENSIONS,
            confidence=0.92,
            target_room_type=room_type,
            target_element_type="room",
            requested_changes=changes,
            rationale="modify_dimensions",
        )

    # 7. Spatial Layout and Room Adjacency / Relocation (e.g. "Move the kitchen closer to the dining room")
    if is_move or "closer" in lower or "next to" in lower or "adjacent" in lower or "beside" in lower:
        target_neighbor = all_rooms[1] if len(all_rooms) >= 2 else None
        return EditIntentResult(
            intent=EditIntentType.MODIFY_LAYOUT,
            confidence=0.9,
            target_room_type=room_type,
            target_element_type="room",
            requested_changes={
                "target_neighbor": target_neighbor,
                "orientation": orientation,
                "proximity": "closer" if "closer" in lower or "next to" in lower else "separated",
            },
            rationale="modify_room_position_or_adjacency",
        )

    # 8. Circulation improvement (e.g. "Improve the circulation without changing the number of rooms")
    if has_circ or "circulation" in lower or "flow" in lower:
        return EditIntentResult(
            intent=EditIntentType.MODIFY_LAYOUT,
            confidence=0.9,
            target_element_type="circulation",
            requested_changes={"enhance_corridors": True},
            rationale="modify_circulation_flow",
        )

    # 9. Add or remove room elements explicitly
    if is_add and room_type:
        return EditIntentResult(
            intent=EditIntentType.ADD_ELEMENT,
            confidence=0.9,
            target_room_type=room_type,
            target_element_type="room",
            requested_changes={"room_type": room_type},
            rationale="add_room",
        )

    if is_remove and room_type:
        return EditIntentResult(
            intent=EditIntentType.REMOVE_ELEMENT,
            confidence=0.9,
            target_room_type=room_type,
            target_element_type="room",
            requested_changes={"room_type": room_type},
            rationale="remove_room",
        )

    # 10. General edit with clear target
    if room_type:
        return EditIntentResult(
            intent=EditIntentType.EDIT_DESIGN,
            confidence=0.75,
            target_room_type=room_type,
            target_element_type="room",
            requested_changes={"general_edit": clean},
            rationale="general_room_edit",
        )

    # 11. Ambiguous instruction
    return EditIntentResult(
        intent=EditIntentType.CLARIFICATION_REQUIRED,
        confidence=0.5,
        clarification_question=(
            f"Which room or architectural element would you like to modify? For example: "
            f"'Make the master bedroom larger', 'Add a window to the kitchen', or 'Change the living room to L-shaped'."
        ),
        rationale="underspecified_edit_target",
    )

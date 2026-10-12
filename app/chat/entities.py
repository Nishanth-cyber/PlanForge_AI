"""Deterministic entity helpers for the conversational layer.

These helpers do *not* decide architecture. They:

* interpret a short answer in the context of the question that was just asked
  (``contextualize_message``),
* detect which export formats a user is asking about,
* diff two requirement summaries so the response can report ``requirements_updated``,
* hold the canonical capability answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

CAPABILITY_REPLY = (
    "I can help you design single-floor bungalows, two-floor duplex residences, three-floor "
    "townhouses, and custom residential layouts. You can specify plot dimensions, rooms, floor "
    "count, orientation, setbacks, and room relationships. I can then help generate floor plans, "
    "validate the resulting geometry, compare design alternatives, and export supported files."
)

#: Export formats PlanForge can actually produce (see the export routes).
SUPPORTED_EXPORTS: Dict[str, str] = {
    "png": "PNG floor-plan images",
    "svg": "SVG vector drawings",
    "dxf": "DXF CAD drawings",
    "json": "JSON project data",
    "zip": "a ZIP bundle of all exported files",
}

_EXPORT_ALIASES: Dict[str, str] = {
    "png": "png", "image": "png", "images": "png",
    "svg": "svg", "vector": "svg",
    "dxf": "dxf", "cad": "dxf", "autocad": "dxf",
    "json": "json",
    "zip": "zip", "bundle": "zip", "archive": "zip",
}
_UNSUPPORTED_EXPORT_TERMS = (
    "pdf", "dwg", "rvt", "revit", "ifc", "skp", "sketchup", "obj", "stl", "step",
    "jpg", "jpeg", "gif", "docx", "xlsx",
)

_DIRECTION_ANSWER_RE = re.compile(
    r"^(?:the\s+)?(north|south|east|west)(?:\s*[- ]?\s*(?:side|direction|facing))?$"
)
_FLOOR_ROOMS_KEY_RE = re.compile(r"^floor_(\d+)_rooms$")
_EXPLICIT_FLOOR_RE = re.compile(
    r"\bfloor\s*\d+\b|\b\d+(?:st|nd|rd|th)\s+floor\b|\bground\b|\bupstairs\b|\bdownstairs\b|"
    r"\b(?:first|second|third|fourth)\s+floor\b",
    re.I,
)
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4}


@dataclass(frozen=True)
class ContextualizedMessage:
    """A user message rewritten (only when safe) so the Requirement Agent can parse the answer."""

    text: str
    active_floor: Optional[int] = None
    rewritten: bool = False


def contextualize_message(message: str, pending_field: Optional[str]) -> ContextualizedMessage:
    """Interpret a short reply in the context of the question the assistant just asked.

    Examples (``pending_field`` -> user reply -> text for the Requirement Agent):

    * ``target_floors``       "2"          -> "2 floors"
    * ``entrance_facing``     "north"      -> "Entrance facing North"
    * ``staircase_location``  "near entrance" -> "Staircase near entrance"
    * ``floor_2_rooms``       "2 bedrooms" -> unchanged text, ``active_floor=2``

    Only the answer's *meaning* is clarified; nothing is invented.
    """
    text = (message or "").strip()
    if not pending_field or not text:
        return ContextualizedMessage(text=text)

    low = re.sub(r"\s+", " ", text.lower()).strip(" .!?,")

    if pending_field == "target_floors":
        if re.fullmatch(r"\d+|one|two|three|four", low):
            n = int(low) if low.isdigit() else _NUMBER_WORDS[low]
            if 1 <= n <= 20:
                return ContextualizedMessage(text=f"{n} floors", rewritten=True)

    elif pending_field == "entrance_facing":
        m = _DIRECTION_ANSWER_RE.match(low)
        if m:
            return ContextualizedMessage(text=f"Entrance facing {m.group(1).title()}", rewritten=True)

    elif pending_field == "staircase_location":
        if "stair" not in low:
            return ContextualizedMessage(text=f"Staircase {text}", rewritten=True)

    else:
        m = _FLOOR_ROOMS_KEY_RE.match(pending_field)
        if m:
            floor_no = int(m.group(1))
            if floor_no > 1 and not _EXPLICIT_FLOOR_RE.search(text):
                return ContextualizedMessage(text=text, active_floor=floor_no)

    return ContextualizedMessage(text=text)


def detect_export_formats(message: str) -> Tuple[List[str], List[str]]:
    """Return ``(supported_formats, unsupported_terms)`` mentioned in a message."""
    low = (message or "").lower()
    supported: List[str] = []
    for token, fmt in _EXPORT_ALIASES.items():
        if re.search(rf"\b{re.escape(token)}\b", low) and fmt not in supported:
            supported.append(fmt)
    unsupported = [t for t in _UNSUPPORTED_EXPORT_TERMS if re.search(rf"\b{re.escape(t)}\b", low)]
    return supported, unsupported


def _summary_view(summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Flatten a ``requirements_summary`` dict into comparable scalar fields."""
    if not summary:
        return {}
    view: Dict[str, Any] = {}
    dims = summary.get("plot_dimensions")
    if dims:
        view["plot_dimensions"] = tuple(round(float(v), 2) for v in dims)
    elif summary.get("plot_area_sqm"):
        view["plot_dimensions"] = ("area", round(float(summary["plot_area_sqm"]), 1))
    if summary.get("target_floors"):
        view["target_floors"] = summary["target_floors"]
    if summary.get("entrance_facing") or summary.get("orientation"):
        view["entrance_facing"] = summary.get("entrance_facing") or summary.get("orientation")
    for fl in summary.get("floors") or []:
        rooms = sorted(
            (r.get("room_type"), r.get("count"), r.get("preferred_area_sqm")) for r in (fl.get("rooms") or [])
        )
        if rooms:
            view[f"floor_{fl.get('floor_number')}_rooms"] = tuple(rooms)
    return view


def diff_summaries(before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]) -> List[str]:
    """Names of requirement fields that were added or changed between two summaries."""
    b, a = _summary_view(before), _summary_view(after)
    return sorted(k for k, v in a.items() if b.get(k) != v)

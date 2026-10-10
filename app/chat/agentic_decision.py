"""Agentic Decision Engine for PlanForge AI.

When the user delegates a decision to the AI (e.g. "decide by you", "your choice",
"surprise me"), this module analyses the current partial requirements and
autonomously fills every remaining gap using architectural best-practice heuristics
— without inventing rooms not warranted by the plot or floor count.

Design principles
-----------------
* Context-sensitive: decisions adapt to plot area, floor count, and entrance direction.
* Proportional: more rooms are added only when the plot can accommodate them.
* Transparent: every autonomous choice is explained to the user.
* Non-destructive: only fills *missing* fields; never overwrites what the user said.
* No LLM required: the engine is purely deterministic so it works in mock mode.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.models.requirements import FloorRequirement, Requirements, RoomRequirement


# ---------------------------------------------------------------------------
# Room programme templates — keyed by (floor_number, density_band)
# density_band: "compact" (<80 m²/floor), "standard" (80-160), "spacious" (>160)
# ---------------------------------------------------------------------------

# Each entry is (room_type, min_count, preferred_area_sqm, adjacency, attached_to)
_GROUND_FLOOR_COMPACT: List[Tuple] = [
    ("living",       1, 18.0, [],            None),
    ("kitchen",      1, 10.0, ["dining"],    None),
    ("dining",       1,  9.0, ["kitchen"],   None),
    ("bathroom",     1,  4.0, [],            None),
    ("porch",        1,  4.0, [],            None),
]

_GROUND_FLOOR_STANDARD: List[Tuple] = [
    ("living",       1, 22.0, [],                    None),
    ("kitchen",      1, 12.0, ["dining"],             None),
    ("dining",       1, 12.0, ["kitchen", "living"],  None),
    ("bedroom",      1, 13.0, [],                     None),
    ("bathroom",     1,  5.0, [],                     "bedroom"),
    ("porch",        1,  5.0, [],                     None),
]

_GROUND_FLOOR_SPACIOUS: List[Tuple] = [
    ("living",       1, 28.0, [],                     None),
    ("kitchen",      1, 14.0, ["dining"],              None),
    ("dining",       1, 14.0, ["kitchen", "living"],   None),
    ("master_bedroom", 1, 18.0, [],                    None),
    ("bedroom",      1, 14.0, [],                      None),
    ("bathroom",     1,  6.0, [],                      "master_bedroom"),
    ("bathroom",     1,  5.0, [],                      "bedroom"),
    ("pooja",        1,  5.0, [],                      None),
    ("porch",        1,  6.0, [],                      None),
]

_UPPER_FLOOR_COMPACT: List[Tuple] = [
    ("bedroom",      1, 12.0, [],      None),
    ("bathroom",     1,  4.0, [],      "bedroom"),
    ("balcony",      1,  5.0, [],      None),
]

_UPPER_FLOOR_STANDARD: List[Tuple] = [
    ("master_bedroom", 1, 16.0, [],    None),
    ("bedroom",      1, 12.0, [],      None),
    ("bathroom",     2,  5.0, [],      None),
    ("balcony",      1,  6.0, [],      None),
]

_UPPER_FLOOR_SPACIOUS: List[Tuple] = [
    ("master_bedroom", 1, 20.0, [],    None),
    ("bedroom",      2, 14.0, [],      None),
    ("bathroom",     2,  6.0, [],      None),
    ("study",        1, 10.0, [],      None),
    ("balcony",      1,  8.0, [],      None),
    ("family_lounge", 1, 14.0, [],     None),
]

_THIRD_FLOOR_STANDARD: List[Tuple] = [
    ("bedroom",      1, 12.0, [],      None),
    ("bathroom",     1,  5.0, [],      "bedroom"),
    ("terrace",      1, 20.0, [],      None),
]

_THIRD_FLOOR_SPACIOUS: List[Tuple] = [
    ("bedroom",      1, 14.0, [],      None),
    ("bathroom",     1,  5.0, [],      "bedroom"),
    ("gym",          1, 12.0, [],      None),
    ("terrace",      1, 24.0, [],      None),
]


# ---------------------------------------------------------------------------
# Staircase location heuristics
# ---------------------------------------------------------------------------

def _decide_staircase(entrance_facing: Optional[str], plot_w: float, plot_d: float) -> str:
    """Pick a sensible staircase position from plot geometry."""
    ratio = plot_w / max(plot_d, 0.1)
    if ratio < 0.6:          # narrow-deep plot → central spine
        return "Central Core"
    if ratio > 1.6:          # wide-shallow → one side near entrance
        return "Near Entrance"
    # Default: central core is usually safest for multi-floor residential
    return "Central Core"


# ---------------------------------------------------------------------------
# Density band helper
# ---------------------------------------------------------------------------

def _density(area_per_floor: float) -> str:
    if area_per_floor < 80:
        return "compact"
    if area_per_floor < 160:
        return "standard"
    return "spacious"


def _template_for(floor_number: int, band: str) -> List[Tuple]:
    if floor_number == 1:
        return {
            "compact":  _GROUND_FLOOR_COMPACT,
            "standard": _GROUND_FLOOR_STANDARD,
            "spacious": _GROUND_FLOOR_SPACIOUS,
        }[band]
    if floor_number == 2:
        return {
            "compact":  _UPPER_FLOOR_COMPACT,
            "standard": _UPPER_FLOOR_STANDARD,
            "spacious": _UPPER_FLOOR_SPACIOUS,
        }[band]
    # floor 3+
    return {
        "compact":  _THIRD_FLOOR_STANDARD,
        "standard": _THIRD_FLOOR_STANDARD,
        "spacious": _THIRD_FLOOR_SPACIOUS,
    }[band]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class AgentDecision:
    """Result returned by the agentic decision engine."""
    requirements: Requirements          # Updated in-place
    filled_fields: List[str] = field(default_factory=list)   # Human-readable descriptions
    rationale: List[str] = field(default_factory=list)       # Per-decision explanations
    all_gaps_filled: bool = False       # True when no further questions remain
    target_floor_decided: Optional[int] = None
    density_band: str = "standard"

    @property
    def explanation_markdown(self) -> str:
        """Short Markdown summary of what the agent decided."""
        if not self.filled_fields:
            return "No gaps found — your requirements are already complete."
        lines = [
            "**PlanForge AI has autonomously filled the remaining requirements** "
            "based on your plot and project context:\n"
        ]
        for item, reason in zip(self.filled_fields, self.rationale):
            lines.append(f"- **{item}**: {reason}")
        if self.all_gaps_filled:
            lines.append(
                "\n✅ All requirements are now complete! "
                "Review the summary below and click **Generate Floor Plan** whenever you are ready."
            )
        else:
            lines.append(
                "\nYou can still adjust any of these choices by typing your preference "
                "(e.g. *'Add a study room'* or *'Change bedroom to 14×16 ft'*)."
            )
        return "\n".join(lines)


def decide(reqs: Requirements) -> AgentDecision:
    """Analyse *reqs* and autonomously fill every missing gap.

    Modifies *reqs* in-place and returns an AgentDecision describing every
    choice made so the UI can explain them to the user.
    """
    decision = AgentDecision(requirements=reqs)

    # ── 1. Plot dimensions ──────────────────────────────────────────────────
    if not reqs.plot_dimensions and not reqs.plot_area_sqm and not reqs.plot_shape:
        # Default: a comfortable urban residential plot
        w, d = 9.144, 12.192           # 30ft × 40ft in metres
        reqs.plot_dimensions = (w, d)
        reqs.plot_area_sqm = round(w * d, 2)
        decision.filled_fields.append("Plot dimensions")
        decision.rationale.append(
            "Defaulted to 30ft × 40ft (9.1m × 12.2m) — a common urban residential plot size."
        )

    # ── Compute useful dimensions ───────────────────────────────────────────
    if reqs.plot_dimensions:
        pw, pd = reqs.plot_dimensions
        plot_area = pw * pd
    elif reqs.plot_area_sqm:
        plot_area = reqs.plot_area_sqm
        side = math.sqrt(plot_area)
        pw = pd = side
    elif reqs.plot_shape:
        # Estimate area from polygon via shoelace
        verts = list(reqs.plot_shape)
        n = len(verts)
        area = abs(sum(
            verts[i][0] * verts[(i + 1) % n][1] - verts[(i + 1) % n][0] * verts[i][1]
            for i in range(n)
        )) / 2.0
        plot_area = area
        pw = pd = math.sqrt(plot_area)
    else:
        plot_area = 111.48      # fallback 30×40 ft
        pw = pd = math.sqrt(plot_area)

    # ── 2. Target floors ────────────────────────────────────────────────────
    if reqs.target_floors is None:
        # Choose floors based on plot area
        if plot_area < 80:
            tf = 1
            tf_reason = f"single floor suits the compact plot ({round(plot_area, 0):.0f} m²)."
        elif plot_area < 200:
            tf = 2
            tf_reason = f"two floors make best use of the {round(plot_area, 0):.0f} m² plot while keeping ground-floor living spacious."
        else:
            tf = 2
            tf_reason = f"two floors recommended for a {round(plot_area, 0):.0f} m² plot; a third floor can be added if needed."
        reqs.target_floors = tf
        decision.target_floor_decided = tf
        decision.filled_fields.append("Number of floors")
        decision.rationale.append(f"Chose **{tf} floor(s)** — {tf_reason}")
    else:
        tf = reqs.target_floors
        decision.target_floor_decided = tf

    # ── Ensure floor objects exist ──────────────────────────────────────────
    for fn in range(1, tf + 1):
        if reqs.get_floor(fn) is None:
            reqs.floors.append(FloorRequirement(
                floor_number=fn,
                floor_name="Ground Floor" if fn == 1 else f"Floor {fn}",
                source="agent",
            ))

    # ── 3. Entrance facing ──────────────────────────────────────────────────
    if reqs.entrance_facing is None and reqs.orientation is None:
        reqs.entrance_facing = "north"
        decision.filled_fields.append("Entrance facing")
        decision.rationale.append(
            "Defaulted to **North** — north-facing entrances receive indirect sunlight "
            "and keep the living areas cooler in tropical and sub-tropical climates."
        )

    # ── 4. Floor room programmes ────────────────────────────────────────────
    area_per_floor = plot_area / tf
    band = _density(area_per_floor)
    decision.density_band = band

    for fn in range(1, tf + 1):
        floor = reqs.get_floor(fn)
        if floor is None:
            continue  # Should not happen after step above
        if floor.room_requirements:
            continue  # User already specified rooms — respect them

        template = _template_for(fn, band)
        added_types: List[str] = []

        for room_type, min_count, pref_area, adjacency, attached_to in template:
            # De-duplicate: if same canonical type already in list, skip
            if any(r.room_type == room_type for r in floor.room_requirements):
                continue
            floor.room_requirements.append(RoomRequirement(
                room_type=room_type,
                min_count=min_count,
                max_count=min_count,
                preferred_area_sqm=pref_area,
                adjacency=list(adjacency),
                attached_to=attached_to,
                source="agent",
            ))
            added_types.append(room_type.replace("_", " ").title())

        if added_types:
            floor_label = "Ground Floor" if fn == 1 else f"Floor {fn}"
            decision.filled_fields.append(f"{floor_label} rooms")
            decision.rationale.append(
                f"Selected **{', '.join(added_types)}** — "
                f"a standard {band} {floor_label.lower()} programme for a "
                f"{round(area_per_floor, 0):.0f} m²/floor plot."
            )

    # ── 5. Staircase note (multi-floor) ─────────────────────────────────────
    if tf >= 2 and "stair" not in reqs.raw_input.lower():
        stair_placement = _decide_staircase(reqs.entrance_facing or reqs.orientation, pw, pd)
        # Append to raw_input so the completeness gate doesn't ask again
        reqs.raw_input = (reqs.raw_input + f" staircase {stair_placement.lower()}").strip()
        decision.filled_fields.append("Staircase placement")
        decision.rationale.append(
            f"Placed at **{stair_placement}** — optimal for the plot's "
            f"{'narrow-deep' if pw / max(pd, 0.1) < 0.6 else 'wide' if pw / max(pd, 0.1) > 1.6 else 'balanced'} geometry."
        )

    decision.all_gaps_filled = True
    return decision

"""Priority Calculator — computes explainable planning priorities for rooms.

Priority represents spatial allocation urgency and structural importance during planning.
It is NOT a subjective ranking; it is grounded in functional architectural logic:
- Primary functional anchors (Living, Master Bedroom, Kitchen) = 'high'
- Standard habitable & sanitary spaces (Bedrooms, Dining, Bathrooms, Study) = 'normal'
- Attached dependencies (Ensuite, Attached Bath) = 'normal' (linked to parent)
- Secondary utilities & peripheral outdoor spaces (Storage, Laundry, Balconies) = 'low'
"""

from __future__ import annotations

from typing import Optional


# Default priority tiers and rationales by canonical room type
PRIORITY_RULES: dict[str, tuple[str, str]] = {
    # High priority: Core architectural anchors
    "living": (
        "high",
        "Primary social anchor connecting entrance and daytime circulation.",
    ),
    "master_bedroom": (
        "high",
        "Primary sleeping space anchoring the private zone.",
    ),
    "kitchen": (
        "high",
        "Core service anchor requiring exterior ventilation and dining access.",
    ),
    # Normal priority: Standard habitable, sanitary, and circulation spaces
    "bedroom": (
        "normal",
        "Standard private sleeping room requiring privacy and quiet circulation.",
    ),
    "dining": (
        "normal",
        "Intermediate social space linking living and kitchen zones.",
    ),
    "bathroom": (
        "normal",
        "Essential sanitary service space requiring plumbing access.",
    ),
    "attached_bathroom": (
        "normal",
        "Private sanitary suite directly attached to parent bedroom.",
    ),
    "study": (
        "normal",
        "Habitable private workspace requiring acoustic buffering.",
    ),
    "foyer": (
        "normal",
        "Primary entrance circulation transition between exterior and interior.",
    ),
    "staircase": (
        "normal",
        "Vertical circulation core connecting multiple floor levels.",
    ),
    "pooja": (
        "normal",
        "Dedicated quiet space for contemplation or prayer.",
    ),
    "prayer": (
        "normal",
        "Dedicated quiet space for contemplation or prayer.",
    ),
    # Low priority: Secondary service and peripheral outdoor spaces
    "storage": (
        "low",
        "Flexible non-habitable storage space with low placement urgency.",
    ),
    "storeroom": (
        "low",
        "Flexible non-habitable storage space with low placement urgency.",
    ),
    "utility": (
        "low",
        "Secondary service space for appliances or domestic operations.",
    ),
    "utility_room": (
        "low",
        "Secondary service space for appliances or domestic operations.",
    ),
    "laundry": (
        "low",
        "Secondary washing and utility service area.",
    ),
    "pantry": (
        "low",
        "Secondary food storage space ancillary to the kitchen.",
    ),
    "servant_room": (
        "low",
        "Ancillary staff quarters positioned on the service periphery.",
    ),
    "balcony": (
        "low",
        "Peripheral outdoor extension subordinate to adjoining habitable room.",
    ),
    "terrace": (
        "low",
        "Peripheral outdoor rooftop or setback space.",
    ),
    "porch": (
        "low",
        "Semi-covered outdoor entry or vehicle shelter.",
    ),
    "veranda": (
        "low",
        "Peripheral semi-covered exterior transition space.",
    ),
    "garage": (
        "low",
        "Vehicular parking area isolated from primary habitable spaces.",
    ),
}


class PriorityCalculator:
    """Calculates explainable planning priority ('high', 'normal', 'low') and rationale."""

    @staticmethod
    def calculate_priority(
        room_type: str,
        attached_to: Optional[str] = None,
        has_adjacencies: bool = False,
        user_override: Optional[str] = None,
    ) -> tuple[str, str]:
        """Compute the planning priority and structured explainability rationale.

        Args:
            room_type:       Canonical room type string.
            attached_to:     Name or ID of parent room if attached.
            has_adjacencies: True if explicit required adjacencies were requested.
            user_override:   Explicit priority requested by the user, if any.

        Returns:
            A tuple of ``(priority_level, rationale_string)``.
        """
        clean = room_type.lower().strip()

        # 1. User override if explicitly supplied
        if user_override and user_override.lower() in ("high", "normal", "low"):
            lvl = user_override.lower()
            return (lvl, f"Explicit user-specified priority: {lvl}.")

        # 2. Attached room special handling
        if attached_to:
            return (
                "normal",
                f"Attached room directly coupled to {attached_to.replace('_', ' ').title()}.",
            )

        # 3. Canonical dictionary lookup
        if clean in PRIORITY_RULES:
            base_priority, rationale = PRIORITY_RULES[clean]
            # If standard room has multiple explicit required adjacencies, bump note
            if base_priority == "normal" and has_adjacencies:
                return (
                    base_priority,
                    f"{rationale} (Constrained by explicit user adjacency requirements).",
                )
            return (base_priority, rationale)

        # 4. Fallback heuristics for unlisted room types
        if any(w in clean for w in ("bed", "live", "kitch")):
            return ("high", "Primary habitable functional anchor.")
        if any(w in clean for w in ("bath", "toilet", "dine", "study")):
            return ("normal", "Standard habitable or sanitary space.")
        return ("low", "Secondary or ancillary functional space.")

"""Room Categorizer — maps room types and names to architectural functional categories.

Maintains strict separation between:
1. Canonical planning room type (e.g. 'master_bedroom', 'attached_bathroom', 'living')
2. Functional architectural zone ('social', 'private', 'service', 'circulation', 'outdoor', 'other')
3. Display / original user label (preserving raw user phrasing for explainability)
"""

from __future__ import annotations

from typing import Optional


# Functional zone mapping for canonical room types
ROOM_FUNCTIONAL_ZONES: dict[str, str] = {
    # Social / Public zones
    "living": "social",
    "dining": "social",
    "drawing_room": "social",
    "lounge": "social",
    "family_room": "social",
    "reception": "social",
    # Private sleeping / quiet zones
    "bedroom": "private",
    "master_bedroom": "private",
    "guest_bedroom": "private",
    "kids_room": "private",
    "study": "private",
    "home_office": "private",
    "library": "private",
    # Service / Wet zones
    "kitchen": "service",
    "kitchenette": "service",
    "bathroom": "service",
    "attached_bathroom": "service",
    "powder_room": "service",
    "storage": "service",
    "storeroom": "service",
    "utility": "service",
    "utility_room": "service",
    "laundry": "service",
    "pantry": "service",
    "servant_room": "service",
    # Circulation / Ingress zones
    "foyer": "circulation",
    "entrance_foyer": "circulation",
    "hallway": "circulation",
    "corridor": "circulation",
    "passage": "circulation",
    "circulation": "circulation",
    "entry": "circulation",
    "staircase": "circulation",
    # Outdoor / Semi-covered zones
    "balcony": "outdoor",
    "terrace": "outdoor",
    "porch": "outdoor",
    "veranda": "outdoor",
    "garage": "outdoor",
    "carport": "outdoor",
    # Other cultural / specialized zones
    "pooja": "other",
    "prayer": "other",
    "gym": "other",
    "home_theatre": "other",
}


class RoomCategorizer:
    """Categorizes rooms into functional zones while preserving original labels."""

    @staticmethod
    def get_functional_zone(room_type: str) -> str:
        """Return functional architectural zone ('social', 'private', 'service', 'circulation', 'outdoor', 'other')."""
        clean = room_type.lower().strip()
        if clean in ROOM_FUNCTIONAL_ZONES:
            return ROOM_FUNCTIONAL_ZONES[clean]

        # Check partial matching
        if any(k in clean for k in ("bed", "study", "office")):
            return "private"
        if any(k in clean for k in ("living", "dining", "hall", "lounge")):
            return "social"
        if any(k in clean for k in ("bath", "toilet", "kitchen", "wash", "store", "util")):
            return "service"
        if any(k in clean for k in ("foyer", "corridor", "stair", "entry")):
            return "circulation"
        if any(k in clean for k in ("balcony", "terrace", "deck", "porch", "garage")):
            return "outdoor"

        return "other"

    @staticmethod
    def format_display_name(room_type: str, original_label: Optional[str] = None) -> str:
        """Format a human-readable display name, preserving user phrasing if available."""
        if original_label and original_label.strip():
            return original_label.strip()
        return room_type.replace("_", " ").title()

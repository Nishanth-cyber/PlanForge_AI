"""Requirement Normalizer — standardises terminology and values.

Normalises:
- Room synonyms to canonical room types (e.g., 'washroom' -> 'bathroom', 'master bed' -> 'master_bedroom').
- Floor labels to consistent 1-based integers ('ground floor' -> 1, '1st floor' -> 1, '2nd floor' -> 2).
- Word numbers ('three' -> 3, 'a' -> 1).
- Preserves original raw text for explainability without distorting user intent.
"""

from __future__ import annotations

import re
from typing import Optional
from app.utils.units import parse_area_sqm, parse_dimension_m


# ---------------------------------------------------------------------------
# Canonical room types and synonyms table
# ---------------------------------------------------------------------------

ROOM_SYNONYMS: dict[str, str] = {
    # Living / Social
    "living room": "living",
    "living": "living",
    "lounge": "living",
    "sitting room": "living",
    "drawing room": "living",
    "reception": "living",
    "family room": "living",
    "living hall": "living",
    # Dining
    "dining room": "dining",
    "dining": "dining",
    "dining area": "dining",
    "dining space": "dining",
    # Kitchen
    "kitchen": "kitchen",
    "kitchenette": "kitchen",
    "open kitchen": "kitchen",
    "modular kitchen": "kitchen",
    "dirty kitchen": "kitchen",
    # Master Bedroom
    "master bedroom": "master_bedroom",
    "master bed": "master_bedroom",
    "primary bedroom": "master_bedroom",
    "mbr": "master_bedroom",
    # Bedroom
    "bedroom": "bedroom",
    "bed room": "bedroom",
    "bed": "bedroom",
    "guest room": "bedroom",
    "guest bedroom": "bedroom",
    "kids room": "bedroom",
    "children bedroom": "bedroom",
    "children room": "bedroom",
    # Bathroom
    "bathroom": "bathroom",
    "bath room": "bathroom",
    "bath": "bathroom",
    "washroom": "bathroom",
    "toilet": "bathroom",
    "wc": "bathroom",
    "lavatory": "bathroom",
    "powder room": "bathroom",
    "half bath": "bathroom",
    "ensuite": "bathroom",
    "attached bathroom": "bathroom",
    "attached bath": "bathroom",
    # Study / Office
    "study": "study",
    "study room": "study",
    "office": "study",
    "home office": "study",
    "workroom": "study",
    "library": "study",
    # Storage / Utility
    "storage": "storage",
    "store": "storage",
    "storeroom": "storage",
    "store room": "storage",
    "utility": "storage",
    "utility room": "storage",
    "pantry": "storage",
    # Laundry
    "laundry": "laundry",
    "laundry room": "laundry",
    "washing area": "laundry",
    # Servant / Staff
    "servant room": "servant_room",
    "maid room": "servant_room",
    "maid's room": "servant_room",
    "servant's quarter": "servant_room",
    "servant quarter": "servant_room",
    "staff room": "servant_room",
    # Porch / Veranda
    "porch": "porch",
    "veranda": "porch",
    "verandah": "porch",
    "portico": "porch",
    "deck": "porch",
    "patio": "porch",
    # Garage / Parking
    "garage": "garage",
    "car porch": "garage",
    "parking": "garage",
    "car park": "garage",
    "carport": "garage",
    # Balcony / Terrace
    "balcony": "balcony",
    "terrace": "balcony",
    # Circulation / Foyer / Entry
    "foyer": "circulation",
    "entrance foyer": "circulation",
    "hallway": "circulation",
    "corridor": "circulation",
    "passage": "circulation",
    "entry": "circulation",
    "entryway": "circulation",
    "lobby": "circulation",
    # Pooja / Prayer room (common in regional contexts)
    "pooja": "pooja",
    "pooja room": "pooja",
    "prayer room": "pooja",
    "mandir": "pooja",
}

#: Number words to integers
WORD_NUMBERS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
    "a": 1, "an": 1, "single": 1, "double": 2,
}

#: Floor label normalization mapping
FLOOR_LABEL_TO_NUMBER: dict[str, int] = {
    "ground": 1,
    "ground floor": 1,
    "gf": 1,
    "g": 1,
    "lower": 1,
    "lower floor": 1,
    "first": 1,
    "first floor": 1,
    "1st": 1,
    "1st floor": 1,
    "floor 1": 1,
    "level 1": 1,
    "second": 2,
    "second floor": 2,
    "2nd": 2,
    "2nd floor": 2,
    "floor 2": 2,
    "level 2": 2,
    "upper": 2,
    "upper floor": 2,
    "upstairs": 2,
    "1st upper": 2,
    "first upper": 2,
    "top": 2,
    "top floor": 2,
    "third": 3,
    "third floor": 3,
    "3rd": 3,
    "3rd floor": 3,
    "floor 3": 3,
    "level 3": 3,
    "2nd upper": 3,
    "second upper": 3,
    "fourth": 4,
    "fourth floor": 4,
    "4th": 4,
    "4th floor": 4,
    "floor 4": 4,
    "fifth": 5,
    "fifth floor": 5,
    "5th": 5,
    "5th floor": 5,
    "floor 5": 5,
}

CARDINAL_DIRECTIONS: set[str] = {
    "north", "south", "east", "west",
    "northeast", "northwest", "southeast", "southwest",
}


class RequirementNormalizer:
    """Normalizes natural-language requirement expressions into canonical representations."""

    @staticmethod
    def canonical_room_type(phrase: str) -> Optional[str]:
        """Convert phrase to canonical room type or return None."""
        phrase_clean = phrase.lower().strip()
        if phrase_clean in ROOM_SYNONYMS:
            return ROOM_SYNONYMS[phrase_clean]

        # Try word boundary match against sorted synonyms
        for syn in sorted(ROOM_SYNONYMS.keys(), key=len, reverse=True):
            if re.search(r"\b" + re.escape(syn) + r"\b", phrase_clean):
                return ROOM_SYNONYMS[syn]
        return None

    @staticmethod
    def normalize_floor_number(label: str) -> Optional[int]:
        """Normalize floor label/string to 1-based integer floor number."""
        clean = label.lower().strip().rstrip(":")
        if clean in FLOOR_LABEL_TO_NUMBER:
            return FLOOR_LABEL_TO_NUMBER[clean]

        # Check for numeric pattern like "floor 2", "floor 3"
        m = re.search(r"\bfloor\s*(\d+)\b", clean)
        if m:
            return int(m.group(1))

        # Check for ordinal pattern like "1st", "2nd", "3rd", "4th"
        m = re.search(r"\b(\d+)(?:st|nd|rd|th)(?:\s+floor)?\b", clean)
        if m:
            return int(m.group(1))

        if clean.isdigit():
            val = int(clean)
            return val if val > 0 else None

        return None

    @staticmethod
    def normalize_count(raw: Optional[str]) -> int:
        """Convert raw count token (word or digit) to integer (default 1)."""
        if not raw:
            return 1
        clean = raw.strip().lower()
        if clean.isdigit():
            return int(clean)
        return WORD_NUMBERS.get(clean, 1)

    @staticmethod
    def normalize_direction(raw: str) -> Optional[str]:
        """Normalize orientation/direction string."""
        clean = raw.strip().lower()
        clean = clean.replace("-", "").replace(" ", "")
        if clean in CARDINAL_DIRECTIONS:
            return clean
        for d in CARDINAL_DIRECTIONS:
            if d in clean:
                return d
        return None

    @staticmethod
    def normalize_area_value(text: str) -> Optional[float]:
        """Extract and convert area from text using standard units converter."""
        return parse_area_sqm(text)

    @staticmethod
    def normalize_dimension_value(text: str) -> Optional[float]:
        """Extract and convert dimension from text using standard units converter."""
        return parse_dimension_m(text)

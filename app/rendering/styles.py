"""Visual styling conventions, color palettes, and line weights for floor plan rendering."""

from __future__ import annotations
from typing import Dict, Any


# Standard semantic category mapping for room types
ROOM_CATEGORY_MAP: Dict[str, str] = {
    "living": "social",
    "living_room": "social",
    "drawing_room": "social",
    "dining": "social",
    "dining_room": "social",
    "family_room": "social",
    "lounge": "social",
    "foyer": "circulation",
    "entry": "circulation",
    "corridor": "circulation",
    "hallway": "circulation",
    "passage": "circulation",
    "staircase": "circulation",
    "bedroom": "private",
    "master_bedroom": "private",
    "guest_bedroom": "private",
    "children_bedroom": "private",
    "study": "private",
    "home_office": "private",
    "kitchen": "service",
    "pantry": "service",
    "utility": "service",
    "laundry": "service",
    "store": "service",
    "storage": "service",
    "bathroom": "service",
    "toilet": "service",
    "wc": "service",
    "powder_room": "service",
    "balcony": "outdoor",
    "verandah": "outdoor",
    "terrace": "outdoor",
    "patio": "outdoor",
    "deck": "outdoor",
    "porch": "outdoor",
    "garage": "service",
}


def get_room_category(room_type: str) -> str:
    """Normalize room type string to functional category."""
    norm = room_type.lower().strip().replace(" ", "_").replace("-", "_")
    return ROOM_CATEGORY_MAP.get(norm, "other")


# Standard color palette (soft, professional architectural pastel tones)
COLOR_PALETTE: Dict[str, Dict[str, Any]] = {
    "social": {
        "fill": "#FFF8E7",      # Soft warm ivory/amber
        "edge": "#8C7355",
        "label": "#4A3B2C",
    },
    "private": {
        "fill": "#F0F4F8",     # Gentle powder blue
        "edge": "#5C768D",
        "label": "#2C3E50",
    },
    "service": {
        "fill": "#EBF5FB",     # Soft light azure/gray-blue
        "edge": "#5499C7",
        "label": "#1B4F72",
    },
    "circulation": {
        "fill": "#F9F9FB", # Pale neutral off-white/gray
        "edge": "#95A5A6",
        "label": "#34495E",
    },
    "outdoor": {
        "fill": "#E8F8F5",     # Pale mint/sage
        "edge": "#48C9B0",
        "label": "#117864",
    },
    "other": {
        "fill": "#FAF9F6",       # Warm neutral white
        "edge": "#7F8C8D",
        "label": "#2C3E50",
    },
}

# Publication-grade monochrome palette (clean black/gray/white for research papers)
PUBLICATION_PALETTE: Dict[str, Dict[str, Any]] = {
    "social": {
        "fill": "#FFFFFF",
        "edge": "#000000",
        "label": "#000000",
    },
    "private": {
        "fill": "#F6F6F6",
        "edge": "#000000",
        "label": "#000000",
    },
    "service": {
        "fill": "#ECECEC",
        "edge": "#000000",
        "label": "#000000",
    },
    "circulation": {
        "fill": "#FAFAFA",
        "edge": "#000000",
        "label": "#000000",
    },
    "outdoor": {
        "fill": "#E0E0E0",
        "edge": "#000000",
        "label": "#000000",
    },
    "other": {
        "fill": "#FFFFFF",
        "edge": "#000000",
        "label": "#000000",
    },
}

# Line style constants
STYLE_PLOT_BOUNDARY = {
    "edgecolor": "#1A1A1A",
    "linewidth": 2.2,
    "linestyle": "-",
    "facecolor": "none",
    "zorder": 1,
}

STYLE_BUILDABLE_BOUNDARY = {
    "edgecolor": "#7F8C8D",
    "linewidth": 1.2,
    "linestyle": "--",
    "facecolor": "none",
    "zorder": 2,
}

STYLE_EXTERIOR_WALL = {
    "color": "#1C2833",
    "linewidth": 3.0,
    "solid_capstyle": "butt",
    "zorder": 10,
}

STYLE_INTERIOR_WALL = {
    "color": "#2C3E50",
    "linewidth": 2.0,
    "solid_capstyle": "butt",
    "zorder": 10,
}

STYLE_DOOR_SWING = {
    "color": "#27AE60",
    "linewidth": 1.4,
    "linestyle": "-",
    "zorder": 12,
}

STYLE_ENTRANCE_DOOR = {
    "color": "#C0392B",
    "linewidth": 2.2,
    "linestyle": "-",
    "zorder": 13,
}

STYLE_WINDOW = {
    "color": "#2980B9",
    "linewidth": 2.6,
    "solid_capstyle": "butt",
    "zorder": 11,
}

STYLE_STAIRCASE_FOOTPRINT = {
    "facecolor": "#EAEDED",
    "edgecolor": "#34495E",
    "linewidth": 1.6,
    "zorder": 5,
}

STYLE_STAIRCASE_TREAD = {
    "color": "#5D6D7E",
    "linewidth": 1.0,
    "linestyle": "-",
    "zorder": 6,
}

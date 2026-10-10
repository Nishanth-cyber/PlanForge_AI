"""Standard CAD layer definitions, styling, and setup for PlanForge DXF export.

Conforms to standard architectural CAD layer conventions:
- Separation of exterior and interior walls
- Distinct layers for openings (doors, door swings, windows)
- Separate circulation, staircase, and room boundaries
- High-visibility annotations (room labels and dimensions)
- Plot and buildable boundary coordination
- Dynamic multi-floor prefixing (e.g. FLOOR_1_*, FLOOR_2_*)
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
import ezdxf


@dataclass(frozen=True)
class LayerDef:
    """CAD Layer specification."""
    name: str
    color: int  # AutoCAD Color Index (ACI: 1=Red, 2=Yellow, 3=Green, 4=Cyan, 5=Blue, 6=Magenta, 7=White/Black, 8=DarkGray, 9=LightGray)
    lineweight: int  # 1/100 mm (e.g. 50 = 0.50mm, 35 = 0.35mm, 25 = 0.25mm, 18 = 0.18mm)
    linetype: str = "Continuous"
    description: str = ""


# Canonical Base Layer Names
LAYER_PLOT_BOUNDARY = "PLOT_BOUNDARY"
LAYER_BUILDABLE_BOUNDARY = "BUILDABLE_BOUNDARY"
LAYER_WALLS_EXTERIOR = "WALLS_EXTERIOR"
LAYER_WALLS_INTERIOR = "WALLS_INTERIOR"
LAYER_ROOM_BOUNDARIES = "ROOM_BOUNDARIES"
LAYER_DOORS = "DOORS"
LAYER_DOOR_SWINGS = "DOOR_SWINGS"
LAYER_WINDOWS = "WINDOWS"
LAYER_STAIRCASES = "STAIRCASES"
LAYER_CORRIDORS = "CORRIDORS"
LAYER_ROOM_LABELS = "ROOM_LABELS"
LAYER_DIMENSIONS = "DIMENSIONS"

# Base Layer Specifications (colors, weights, linetypes)
BASE_LAYERS: Dict[str, LayerDef] = {
    LAYER_PLOT_BOUNDARY: LayerDef(
        name=LAYER_PLOT_BOUNDARY,
        color=4,  # Cyan
        lineweight=35,
        linetype="Continuous",
        description="Site plot perimeter boundary",
    ),
    LAYER_BUILDABLE_BOUNDARY: LayerDef(
        name=LAYER_BUILDABLE_BOUNDARY,
        color=1,  # Red
        lineweight=25,
        linetype="Continuous",
        description="Zoning setback / buildable envelope boundary",
    ),
    LAYER_WALLS_EXTERIOR: LayerDef(
        name=LAYER_WALLS_EXTERIOR,
        color=7,  # White / Black
        lineweight=50,
        linetype="Continuous",
        description="Perimeter and exterior load-bearing walls",
    ),
    LAYER_WALLS_INTERIOR: LayerDef(
        name=LAYER_WALLS_INTERIOR,
        color=8,  # Dark Gray
        lineweight=25,
        linetype="Continuous",
        description="Interior partition walls",
    ),
    LAYER_ROOM_BOUNDARIES: LayerDef(
        name=LAYER_ROOM_BOUNDARIES,
        color=5,  # Blue
        lineweight=18,
        linetype="Continuous",
        description="Usable interior room perimeter polygons",
    ),
    LAYER_DOORS: LayerDef(
        name=LAYER_DOORS,
        color=3,  # Green
        lineweight=25,
        linetype="Continuous",
        description="Door openings and door leaf panels",
    ),
    LAYER_DOOR_SWINGS: LayerDef(
        name=LAYER_DOOR_SWINGS,
        color=2,  # Yellow
        lineweight=18,
        linetype="Continuous",
        description="Door 90-degree swing trajectories",
    ),
    LAYER_WINDOWS: LayerDef(
        name=LAYER_WINDOWS,
        color=4,  # Cyan
        lineweight=25,
        linetype="Continuous",
        description="Window openings, sills, and glazing lines",
    ),
    LAYER_STAIRCASES: LayerDef(
        name=LAYER_STAIRCASES,
        color=6,  # Magenta
        lineweight=25,
        linetype="Continuous",
        description="Staircase footprints, treads, and riser geometry",
    ),
    LAYER_CORRIDORS: LayerDef(
        name=LAYER_CORRIDORS,
        color=9,  # Light Gray
        lineweight=18,
        linetype="Continuous",
        description="Circulation paths and corridor boundaries",
    ),
    LAYER_ROOM_LABELS: LayerDef(
        name=LAYER_ROOM_LABELS,
        color=7,  # White / Black
        lineweight=20,
        linetype="Continuous",
        description="Room names, IDs, floor numbers, and usable areas",
    ),
    LAYER_DIMENSIONS: LayerDef(
        name=LAYER_DIMENSIONS,
        color=1,  # Red
        lineweight=18,
        linetype="Continuous",
        description="Linear dimension entities and bounding measurements",
    ),
}

# Floor-specific entity layers (for multi-floor separation)
FLOOR_ENTITY_LAYERS = [
    LAYER_WALLS_EXTERIOR,
    LAYER_WALLS_INTERIOR,
    LAYER_ROOM_BOUNDARIES,
    LAYER_DOORS,
    LAYER_DOOR_SWINGS,
    LAYER_WINDOWS,
    LAYER_STAIRCASES,
    LAYER_CORRIDORS,
    LAYER_ROOM_LABELS,
    LAYER_DIMENSIONS,
]


def get_layer_name(
    base_layer: str,
    floor_number: Optional[int] = None,
    is_multi_floor: bool = False,
) -> str:
    """Resolve layer name, prefixing with FLOOR_{floor_number}_ for multi-floor designs.

    Global site layers (PLOT_BOUNDARY, BUILDABLE_BOUNDARY) are never prefixed.
    Single-floor projects use base layer names directly.
    """
    if not is_multi_floor or floor_number is None:
        return base_layer

    if base_layer in (LAYER_PLOT_BOUNDARY, LAYER_BUILDABLE_BOUNDARY):
        return base_layer

    return f"FLOOR_{floor_number}_{base_layer}"


def setup_dxf_layers(doc: ezdxf.document.Drawing, floor_numbers: Optional[List[int]] = None) -> None:
    """Register all required architectural layers in the DXF drawing.

    Configures standard ACI colors, lineweights, and linetypes.
    """
    layers = doc.layers

    # Ensure DASHED linetype is available if needed
    if "DASHED" not in doc.linetypes:
        try:
            doc.linetypes.add("DASHED", pattern=[0.5, 0.25, -0.25], description="Dashed __ __ __")
        except Exception:
            pass

    # 1. Register global site layers
    for base_layer in (LAYER_PLOT_BOUNDARY, LAYER_BUILDABLE_BOUNDARY):
        spec = BASE_LAYERS[base_layer]
        if spec.name not in layers:
            layers.add(
                name=spec.name,
                color=spec.color,
                lineweight=spec.lineweight,
                linetype=spec.linetype,
            )

    is_multi_floor = floor_numbers is not None and len(floor_numbers) > 1

    if not is_multi_floor:
        # Register single-floor base layers
        for name, spec in BASE_LAYERS.items():
            if name not in layers:
                layers.add(
                    name=spec.name,
                    color=spec.color,
                    lineweight=spec.lineweight,
                    linetype=spec.linetype,
                )
    else:
        # Register multi-floor specific layers for each floor
        for fn in (floor_numbers or [1]):
            for base_name in FLOOR_ENTITY_LAYERS:
                spec = BASE_LAYERS[base_name]
                fl_name = f"FLOOR_{fn}_{base_name}"
                if fl_name not in layers:
                    layers.add(
                        name=fl_name,
                        color=spec.color,
                        lineweight=spec.lineweight,
                        linetype=spec.linetype,
                    )

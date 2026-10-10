"""CAD DXF Export module for PlanForge AI."""

import mimetypes
from app.export.dxf.layers import (
    BASE_LAYERS,
    LAYER_PLOT_BOUNDARY,
    LAYER_BUILDABLE_BOUNDARY,
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
    get_layer_name,
    setup_dxf_layers,
)
from app.export.dxf.exporter import (
    DXFExporter,
    export_floor_plan_set_to_dxf,
    get_dxf_filename,
    sanitize_project_name,
)

# Register authoritative standard DXF MIME type
mimetypes.add_type("application/dxf", ".dxf")

__all__ = [
    "DXFExporter",
    "export_floor_plan_set_to_dxf",
    "get_dxf_filename",
    "sanitize_project_name",
    "BASE_LAYERS",
    "LAYER_PLOT_BOUNDARY",
    "LAYER_BUILDABLE_BOUNDARY",
    "LAYER_WALLS_EXTERIOR",
    "LAYER_WALLS_INTERIOR",
    "LAYER_ROOM_BOUNDARIES",
    "LAYER_DOORS",
    "LAYER_DOOR_SWINGS",
    "LAYER_WINDOWS",
    "LAYER_STAIRCASES",
    "LAYER_CORRIDORS",
    "LAYER_ROOM_LABELS",
    "LAYER_DIMENSIONS",
    "get_layer_name",
    "setup_dxf_layers",
]

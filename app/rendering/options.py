"""Configuration options and return metadata for floor plan rendering."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


@dataclass
class RenderOptions:
    """Configuration options for floor plan visualization.

    All settings have sensible defaults for clean, readable output suitable
    for research figures and technical documentation.
    """
    dpi: int = 300
    figsize: Tuple[float, float] = (10.0, 10.0)
    publication_mode: bool = False  # If True, renders in clean monochrome/grayscale suitable for print papers
    show_room_ids: bool = False
    show_room_areas: bool = True
    show_dimensions: bool = True
    show_orientation: bool = True  # North arrow (only displayed if actual orientation is provided)
    show_title: bool = True
    show_walls: bool = True
    show_doors: bool = True
    show_windows: bool = True
    show_staircases: bool = True
    show_corridors: bool = True
    show_grid: bool = False
    show_legend: bool = True
    margin_ratio: float = 0.08  # Padding around plot bounds

    def to_dict(self) -> Dict[str, Any]:
        """Serialize options to dictionary."""
        return {
            "dpi": self.dpi,
            "figsize": list(self.figsize),
            "publication_mode": self.publication_mode,
            "show_room_ids": self.show_room_ids,
            "show_room_areas": self.show_room_areas,
            "show_dimensions": self.show_dimensions,
            "show_orientation": self.show_orientation,
            "show_title": self.show_title,
            "show_walls": self.show_walls,
            "show_doors": self.show_doors,
            "show_windows": self.show_windows,
            "show_staircases": self.show_staircases,
            "show_corridors": self.show_corridors,
            "show_grid": self.show_grid,
            "show_legend": self.show_legend,
            "margin_ratio": self.margin_ratio,
        }


@dataclass
class RenderedFloor:
    """Metadata describing a successfully rendered floor-plan image."""
    floor_number: int
    output_path: str
    width_px: int
    height_px: int
    rendered_room_count: int
    rendered_wall_count: int
    rendered_door_count: int
    rendered_window_count: int
    rendered_staircase_count: int
    rendered_corridor_count: int
    orientation: Optional[str] = None
    has_plot_boundary: bool = False
    has_buildable_boundary: bool = False

    @property
    def image_path(self) -> Path:
        """Convenience Path object for output_path."""
        return Path(self.output_path)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            "floor_number": self.floor_number,
            "output_path": self.output_path,
            "width_px": self.width_px,
            "height_px": self.height_px,
            "rendered_room_count": self.rendered_room_count,
            "rendered_wall_count": self.rendered_wall_count,
            "rendered_door_count": self.rendered_door_count,
            "rendered_window_count": self.rendered_window_count,
            "rendered_staircase_count": self.rendered_staircase_count,
            "rendered_corridor_count": self.rendered_corridor_count,
            "orientation": self.orientation,
            "has_plot_boundary": self.has_plot_boundary,
            "has_buildable_boundary": self.has_buildable_boundary,
        }

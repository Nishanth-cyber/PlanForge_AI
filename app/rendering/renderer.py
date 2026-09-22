"""Top-level facade and convenience functions for the rendering subsystem."""

from __future__ import annotations
from pathlib import Path
from typing import Optional, Union, List

from app.models.floor_plan import FloorPlan, FloorPlanSet
from app.rendering.options import RenderOptions, RenderedFloor
from app.rendering.floor_renderer import FloorPlanRenderer, PlanForgeFloorPlanRenderer


def render_floor_plan(
    floor_plan: FloorPlan,
    output_path: Union[str, Path],
    options: Optional[RenderOptions] = None,
    orientation: Optional[str] = None,
    project_name: str = "",
) -> RenderedFloor:
    """Render a single FloorPlan to a PNG image."""
    renderer = FloorPlanRenderer()
    return renderer.render_floor_plan(
        floor_plan=floor_plan,
        output_path=output_path,
        options=options,
        orientation=orientation,
        project_name=project_name,
    )


def render_floor_plan_set(
    floor_plan_set: FloorPlanSet,
    output_dir: Union[str, Path],
    options: Optional[RenderOptions] = None,
    orientation: Optional[str] = None,
    project_name: str = "",
) -> List[RenderedFloor]:
    """Render an entire multi-floor plan set to one PNG per floor."""
    renderer = FloorPlanRenderer()
    return renderer.render_floor_plan_set(
        floor_plan_set=floor_plan_set,
        output_dir=output_dir,
        options=options,
        orientation=orientation,
        project_name=project_name,
    )


__all__ = [
    "FloorPlanRenderer",
    "PlanForgeFloorPlanRenderer",
    "RenderOptions",
    "RenderedFloor",
    "render_floor_plan",
    "render_floor_plan_set",
]

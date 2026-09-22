"""Complete project export bundle and optional ZIP archive packaging."""

from __future__ import annotations
import shutil
import zipfile
from pathlib import Path
from typing import Optional, Union

from app.models.requirements import Requirements
from app.models.planning import PlanningSpec
from app.models.allocation import AllocationSet
from app.models.architectural_design import ArchitecturalDesignSet
from app.models.floor_plan import FloorPlanSet
from app.models.validation import ValidationReport
from app.models.refinement import RefinementResult
from app.models.alternatives import DesignAlternativeSet
from app.explainability.models import DecisionTrace
from app.explainability.renderer import ExplanationRenderer
from app.rendering.options import RenderOptions
from app.rendering.floor_renderer import FloorPlanRenderer
from app.export.errors import BundleExportError
from app.export.json_exporter import export_project_json, export_alternative_json, save_json
from app.export.report_exporter import (
    generate_project_markdown_report,
    generate_alternative_markdown_report,
    save_markdown,
)


class BundleExporter:
    """Orchestrates comprehensive project export bundles."""

    def __init__(self, renderer: Optional[FloorPlanRenderer] = None) -> None:
        self.renderer = renderer or FloorPlanRenderer()

    def export_bundle(
        self,
        output_dir: Union[str, Path],
        project_id: str,
        project_name: str = "",
        requirements: Optional[Requirements] = None,
        planning_spec: Optional[PlanningSpec] = None,
        allocation_set: Optional[AllocationSet] = None,
        architectural_design_set: Optional[ArchitecturalDesignSet] = None,
        floor_plan_set: Optional[FloorPlanSet] = None,
        validation_report: Optional[ValidationReport] = None,
        refinement_result: Optional[RefinementResult] = None,
        alternative_set: Optional[DesignAlternativeSet] = None,
        decision_trace: Optional[DecisionTrace] = None,
        render_images: bool = True,
        create_zip: bool = False,
        render_options: Optional[RenderOptions] = None,
    ) -> Path:
        """Create structured export bundle directory and optional ZIP package.

        Directory structure:
        <output_dir>/<project_id>/
            ├── project.json
            ├── summary.md
            ├── decision_trace.json
            ├── explanations/
            │   ├── project.md
            │   └── alternative_X.md
            └── alternatives/
                └── alternative_X/
                    ├── design.json
                    ├── floor_1.png
                    ├── floor_2.png
                    └── explanation.md
        """
        try:
            bundle_path = Path(output_dir) / project_id
            bundle_path.mkdir(parents=True, exist_ok=True)

            orientation = requirements.orientation if requirements else None
            proj_title = project_name or (requirements.project_name if requirements else project_id)

            # 1. Export project.json
            proj_data = export_project_json(
                project_id=project_id,
                project_name=proj_title,
                requirements=requirements,
                planning_spec=planning_spec,
                allocation_set=allocation_set,
                architectural_design_set=architectural_design_set,
                floor_plan_set=floor_plan_set,
                validation_report=validation_report,
                refinement_result=refinement_result,
                alternative_set=alternative_set,
                decision_trace=decision_trace,
            )
            save_json(proj_data, bundle_path / "project.json")

            # 2. Export summary.md
            summary_md = generate_project_markdown_report(
                project_id=project_id,
                project_name=proj_title,
                requirements=requirements,
                planning_spec=planning_spec,
                allocation_set=allocation_set,
                architectural_design_set=architectural_design_set,
                floor_plan_set=floor_plan_set,
                validation_report=validation_report,
                refinement_result=refinement_result,
                alternative_set=alternative_set,
                decision_trace=decision_trace,
            )
            save_markdown(summary_md, bundle_path / "summary.md")

            # 3. Export explanations/ & decision_trace.json
            exp_dir = bundle_path / "explanations"
            exp_dir.mkdir(parents=True, exist_ok=True)

            if decision_trace:
                save_json(decision_trace.to_dict(), bundle_path / "decision_trace.json")

                if hasattr(ExplanationRenderer, "render_project_summary"):
                    proj_exp = ExplanationRenderer.render_project_summary(decision_trace)
                else:
                    proj_exp = f"# Project Explanations: {proj_title}\n\nDecision trace: `{decision_trace.trace_id}`"
                save_markdown(proj_exp, exp_dir / "project_summary.md")

                for alt_trace in decision_trace.alternatives:
                    if hasattr(ExplanationRenderer, "render_alternative_summary"):
                        alt_exp = ExplanationRenderer.render_alternative_summary(decision_trace, alt_trace.alternative_id)
                    else:
                        alt_exp = f"# Alternative Explanation: {alt_trace.alternative_id}"
                    save_markdown(alt_exp, exp_dir / f"{alt_trace.alternative_id}.md")

                if decision_trace.entity_chains:
                    rooms_dir = exp_dir / "rooms"
                    rooms_dir.mkdir(parents=True, exist_ok=True)
                    for r_id, chain in decision_trace.entity_chains.items():
                        if chain.entity_type == "room" and hasattr(ExplanationRenderer, "render_room_explanation"):
                            r_exp = ExplanationRenderer.render_room_explanation(decision_trace, r_id)
                            save_markdown(r_exp, rooms_dir / f"{r_id}.md")
            else:
                save_markdown(
                    f"# Explanations: {proj_title}\n\n*Detailed decision trace was not recorded for this generation.*",
                    exp_dir / "project_summary.md",
                )

            # 4. Render and export alternatives if available
            alt_dir = bundle_path / "alternatives"
            if alternative_set and alternative_set.alternatives:
                alt_dir.mkdir(parents=True, exist_ok=True)
                for alt in alternative_set.alternatives:
                    single_alt_dir = alt_dir / f"alternative_{alt.index}"
                    single_alt_dir.mkdir(parents=True, exist_ok=True)

                    # Export alternative design.json
                    alt_data = export_alternative_json(alt)
                    save_json(alt_data, single_alt_dir / "design.json")

                    # Export alternative explanation.md
                    alt_md = generate_alternative_markdown_report(alt, decision_trace=decision_trace)
                    save_markdown(alt_md, single_alt_dir / "explanation.md")

                    # Render floor plan PNGs for this alternative
                    if render_images and alt.floor_plan_set:
                        self.renderer.render_floor_plan_set(
                            floor_plan_set=alt.floor_plan_set,
                            output_dir=single_alt_dir,
                            options=render_options,
                            orientation=orientation,
                            project_name=f"{proj_title} (Alt {alt.index})",
                        )

            # 5. Fallback rendering for single floor_plan_set (if alternative_set not provided)
            elif render_images and floor_plan_set:
                floors_dir = bundle_path / "floors"
                floors_dir.mkdir(parents=True, exist_ok=True)
                self.renderer.render_floor_plan_set(
                    floor_plan_set=floor_plan_set,
                    output_dir=floors_dir,
                    options=render_options,
                    orientation=orientation,
                    project_name=proj_title,
                )

            # 6. Optional ZIP Archive packaging
            if create_zip:
                zip_target = Path(output_dir) / f"{project_id}.zip"
                with zipfile.ZipFile(zip_target, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in bundle_path.rglob("*"):
                        if file_path.is_file():
                            arcname = file_path.relative_to(bundle_path.parent)
                            zipf.write(file_path, arcname)

            return bundle_path

        except Exception as e:
            if isinstance(e, BundleExportError):
                raise
            raise BundleExportError(f"Failed to export project bundle for '{project_id}': {e}") from e


def export_project_bundle(
    output_dir: Union[str, Path],
    project_id: str,
    project_name: str = "",
    requirements: Optional[Requirements] = None,
    planning_spec: Optional[PlanningSpec] = None,
    allocation_set: Optional[AllocationSet] = None,
    architectural_design_set: Optional[ArchitecturalDesignSet] = None,
    floor_plan_set: Optional[FloorPlanSet] = None,
    validation_report: Optional[ValidationReport] = None,
    refinement_result: Optional[RefinementResult] = None,
    alternative_set: Optional[DesignAlternativeSet] = None,
    decision_trace: Optional[DecisionTrace] = None,
    render_images: bool = True,
    create_zip: bool = False,
    render_options: Optional[RenderOptions] = None,
) -> Path:
    """Convenience function to export a complete PlanForge project bundle."""
    exporter = BundleExporter()
    return exporter.export_bundle(
        output_dir=output_dir,
        project_id=project_id,
        project_name=project_name,
        requirements=requirements,
        planning_spec=planning_spec,
        allocation_set=allocation_set,
        architectural_design_set=architectural_design_set,
        floor_plan_set=floor_plan_set,
        validation_report=validation_report,
        refinement_result=refinement_result,
        alternative_set=alternative_set,
        decision_trace=decision_trace,
        render_images=render_images,
        create_zip=create_zip,
        render_options=render_options,
    )

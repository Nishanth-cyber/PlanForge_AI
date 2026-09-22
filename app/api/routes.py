"""REST API route handlers for the PlanForge architectural generation service."""

from __future__ import annotations

import json
import mimetypes
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, JSONResponse

from app.api.dependencies import get_orchestrator, get_project_registry
from app.api.errors import resolve_safe_path
from app.api.registry import ProjectRegistry
from app.api.schemas import (
    AlternativeSummarySchema,
    ExportFileItem,
    ExportResponse,
    GenerationRequest,
    GenerationResponse,
    HealthResponse,
    ProjectDetailResponse,
    ValidationSummarySchema,
)
from app.export.json_exporter import export_project_json
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import PlanForgeOrchestrator

router = APIRouter(tags=["PlanForge"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System Health & Diagnostic Status",
)
def get_health() -> HealthResponse:
    """Return system readiness, framework versions, and execution environment."""
    return HealthResponse()


@router.post(
    "/generate",
    response_model=GenerationResponse,
    summary="Generate Residential Floor Plan",
)
def generate_floor_plan(
    req: GenerationRequest,
    orchestrator: PlanForgeOrchestrator = Depends(get_orchestrator),
    registry: ProjectRegistry = Depends(get_project_registry),
) -> GenerationResponse:
    """Execute the complete 10-stage PlanForge generative pipeline.

    Coordinates:
    Requirement -> Planning -> ASAA -> Architectural LLM -> Geometry Engine ->
    Independent Validator -> Refinement Loop -> Multi-Design Diversity ->
    Decision Trace -> Export & Rendering.
    """
    cfg = OrchestrationConfig(
        enable_refinement=req.enable_refinement,
        max_refinement_iterations=req.max_refinement_iterations,
        num_alternatives=req.num_alternatives,
        enable_rendering=req.enable_rendering,
        enable_exports=req.enable_exports,
        create_zip=req.create_zip,
        output_dir=req.output_dir,
    )

    brief_to_use = req.brief or ""
    if req.plot_shape and len(req.plot_shape) >= 3 and "polygon:" not in brief_to_use.lower() and "plot shape:" not in brief_to_use.lower():
        coords_str = ", ".join(f"({float(p[0])}, {float(p[1])})" for p in req.plot_shape)
        brief_to_use = f"Plot polygon: {coords_str}\n" + brief_to_use

    result = orchestrator.generate(
        raw_brief=brief_to_use,
        project_name=req.project_name,
        project_id=req.project_id,
        config=cfg,
    )

    # Cache result in process-local registry
    registry.save_result(result)

    # Format validation summary if available
    val_summary = None
    if result.validation_report:
        val_summary = ValidationSummarySchema(
            overall_valid=result.validation_report.overall_valid,
            overall_score=round(result.validation_report.overall_score, 2),
            total_errors=result.validation_report.total_errors,
            total_warnings=result.validation_report.total_warnings,
        )

    # Format alternatives if available (neutrally presented without rankings)
    alts_list: List[AlternativeSummarySchema] = []
    if result.alternative_set and result.alternative_set.alternatives:
        for alt in result.alternative_set.alternatives:
            alts_list.append(
                AlternativeSummarySchema(
                    alternative_id=alt.alternative_id,
                    index=alt.index,
                    strategy=alt.strategy,
                    is_valid=alt.is_valid,
                    characteristics=list(alt.characteristics),
                    diversity_scores=dict(alt.diversity_scores),
                )
            )

    return GenerationResponse(
        project_id=result.project_id,
        project_name=result.project_name,
        status=result.status,
        is_success=result.is_success,
        is_valid=result.is_valid,
        stage_statuses={k: v.status.value for k, v in result.stage_records.items()},
        validation_summary=val_summary,
        alternatives=alts_list,
        export_bundle_path=result.export_bundle_path,
        decision_trace_available=result.decision_trace is not None,
        missing_fields=result.missing_fields,
        missing_floors=result.missing_floors,
        clarification_questions=result.clarification_questions,
        error_message=result.error_message,
    )


@router.get(
    "/projects",
    response_model=List[ProjectDetailResponse],
    summary="List Generated Projects",
)
def list_projects(
    registry: ProjectRegistry = Depends(get_project_registry),
) -> List[ProjectDetailResponse]:
    """List summary details of all generated projects in registry and on-disk output bundles."""
    projects: List[ProjectDetailResponse] = []
    seen_ids: set[str] = set()

    # 1. In-memory registry projects
    for pid in registry.list_projects():
        res = registry.get_result(pid)
        if not res:
            continue
        seen_ids.add(pid)
        val_summary = None
        if res.validation_report:
            val_summary = ValidationSummarySchema(
                overall_valid=res.validation_report.overall_valid,
                overall_score=round(res.validation_report.overall_score, 2),
                total_errors=res.validation_report.total_errors,
                total_warnings=res.validation_report.total_warnings,
            )
        alts_count = len(res.alternative_set.alternatives) if res.alternative_set else 0
        projects.append(
            ProjectDetailResponse(
                project_id=res.project_id,
                project_name=res.project_name,
                status=res.status,
                is_valid=res.is_valid,
                validation_summary=val_summary,
                alternatives_count=alts_count,
                export_bundle_path=res.export_bundle_path,
                decision_trace_available=res.decision_trace is not None,
            )
        )

    # 2. Check disk outputs/ directory for persisted project.json bundles
    outputs_dir = Path("outputs")
    if outputs_dir.exists() and outputs_dir.is_dir():
        for pdir in outputs_dir.iterdir():
            if pdir.is_dir() and pdir.name not in seen_ids:
                pjson_path = pdir / "project.json"
                if pjson_path.exists():
                    try:
                        with open(pjson_path, "r", encoding="utf-8") as f:
                            pdata = json.load(f)
                        meta = pdata.get("project_metadata", {})
                        val_rep = pdata.get("validation_report", {})
                        val_summary = None
                        if val_rep:
                            val_summary = ValidationSummarySchema(
                                overall_valid=val_rep.get("overall_valid", True),
                                overall_score=round(float(val_rep.get("overall_score", 100.0)), 2),
                                total_errors=int(val_rep.get("total_errors", 0)),
                                total_warnings=int(val_rep.get("total_warnings", 0)),
                            )
                        alts = pdata.get("alternatives", [])
                        projects.append(
                            ProjectDetailResponse(
                                project_id=pdir.name,
                                project_name=meta.get("project_name", pdir.name),
                                status="completed",
                                is_valid=val_summary.overall_valid if val_summary else True,
                                validation_summary=val_summary,
                                alternatives_count=len(alts),
                                export_bundle_path=str(pdir),
                                decision_trace_available="decision_trace" in pdata,
                            )
                        )
                        seen_ids.add(pdir.name)
                    except Exception:
                        pass

    return projects


@router.get(
    "/projects/{project_id}",
    response_model=ProjectDetailResponse,
    summary="Retrieve Generated Project Details",
)
def get_project(
    project_id: str,
    registry: ProjectRegistry = Depends(get_project_registry),
) -> ProjectDetailResponse:
    """Retrieve summary details of a generated project from the process-local registry."""
    res = registry.get_result(project_id)
    if res:
        val_summary = None
        if res.validation_report:
            val_summary = ValidationSummarySchema(
                overall_valid=res.validation_report.overall_valid,
                overall_score=round(res.validation_report.overall_score, 2),
                total_errors=res.validation_report.total_errors,
                total_warnings=res.validation_report.total_warnings,
            )
        alts_count = len(res.alternative_set.alternatives) if res.alternative_set else 0
        return ProjectDetailResponse(
            project_id=res.project_id,
            project_name=res.project_name,
            status=res.status,
            is_valid=res.is_valid,
            validation_summary=val_summary,
            alternatives_count=alts_count,
            export_bundle_path=res.export_bundle_path,
            decision_trace_available=res.decision_trace is not None,
        )

    # Fallback to disk outputs/ bundle if registry cleared
    pjson_path = Path("outputs") / project_id / "project.json"
    if pjson_path.exists():
        try:
            with open(pjson_path, "r", encoding="utf-8") as f:
                pdata = json.load(f)
            meta = pdata.get("project_metadata", {})
            val_rep = pdata.get("validation_report", {})
            val_summary = None
            if val_rep:
                val_summary = ValidationSummarySchema(
                    overall_valid=val_rep.get("overall_valid", True),
                    overall_score=round(float(val_rep.get("overall_score", 100.0)), 2),
                    total_errors=int(val_rep.get("total_errors", 0)),
                    total_warnings=int(val_rep.get("total_warnings", 0)),
                )
            alts = pdata.get("alternatives", [])
            return ProjectDetailResponse(
                project_id=project_id,
                project_name=meta.get("project_name", project_id),
                status="completed",
                is_valid=val_summary.overall_valid if val_summary else True,
                validation_summary=val_summary,
                alternatives_count=len(alts),
                export_bundle_path=str(Path("outputs") / project_id),
                decision_trace_available="decision_trace" in pdata,
            )
        except Exception:
            pass

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Project '{project_id}' was not found in registry or outputs.",
    )


@router.delete(
    "/projects/{project_id}",
    summary="Delete Generated Project",
)
def delete_project(
    project_id: str,
    registry: ProjectRegistry = Depends(get_project_registry),
) -> Dict[str, Any]:
    """Delete a generated project from in-memory registry and disk output bundles."""
    deleted_from_memory = registry.delete_project(project_id)

    # Delete persisted bundle from outputs/ if present
    pdir = Path("outputs") / project_id
    deleted_from_disk = False
    if pdir.exists() and pdir.is_dir():
        try:
            shutil.rmtree(pdir)
            deleted_from_disk = True
        except Exception:
            pass

    if not deleted_from_memory and not deleted_from_disk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' was not found in registry or outputs.",
        )

    return {
        "status": "deleted",
        "project_id": project_id,
        "deleted_from_memory": deleted_from_memory,
        "deleted_from_disk": deleted_from_disk,
    }


@router.get(
    "/projects/{project_id}/data",
    summary="Retrieve Complete Project JSON Data",
)
def get_project_data(
    project_id: str,
    registry: ProjectRegistry = Depends(get_project_registry),
) -> Dict[str, Any]:
    """Retrieve full structured project dictionary (requirements, floor plans, geometry, validation)."""
    res = registry.get_result(project_id)
    if res:
        return export_project_json(
            project_id=res.project_id,
            project_name=res.project_name,
            requirements=res.requirements,
            planning_spec=res.planning_spec,
            allocation_set=res.allocation_set,
            architectural_design_set=res.architectural_design_set,
            floor_plan_set=res.floor_plan_set,
            validation_report=res.validation_report,
            refinement_result=res.refinement_result,
            alternative_set=res.alternative_set,
            decision_trace=res.decision_trace,
        )

    # Fallback to loading project.json from disk bundle
    pjson_path = Path("outputs") / project_id / "project.json"
    if pjson_path.exists():
        with open(pjson_path, "r", encoding="utf-8") as f:
            return json.load(f)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Project data for '{project_id}' was not found.",
    )


@router.get(
    "/projects/{project_id}/trace",
    summary="Retrieve Decision Trace",
)
def get_project_trace(
    project_id: str,
    registry: ProjectRegistry = Depends(get_project_registry),
) -> Dict[str, Any]:
    """Retrieve complete, structured decision trace for a generated project."""
    res = registry.get_result(project_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' was not found.",
        )

    if not res.decision_trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision trace for project '{project_id}' was not recorded or is unavailable.",
        )

    return res.decision_trace.to_dict()


@router.get(
    "/projects/{project_id}/alternatives",
    response_model=List[AlternativeSummarySchema],
    summary="Retrieve Design Alternatives",
)
def get_project_alternatives(
    project_id: str,
    registry: ProjectRegistry = Depends(get_project_registry),
) -> List[AlternativeSummarySchema]:
    """Retrieve all validated architectural design alternatives neutrally without rankings."""
    res = registry.get_result(project_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' was not found.",
        )

    if not res.alternative_set or not res.alternative_set.alternatives:
        return []

    return [
        AlternativeSummarySchema(
            alternative_id=alt.alternative_id,
            index=alt.index,
            strategy=alt.strategy,
            is_valid=alt.is_valid,
            characteristics=list(alt.characteristics),
            diversity_scores=dict(alt.diversity_scores),
        )
        for alt in res.alternative_set.alternatives
    ]


@router.get(
    "/projects/{project_id}/export",
    summary="Access or Download Export Artifacts",
)
def get_project_export(
    project_id: str,
    file: Optional[str] = Query(
        default=None,
        description="Relative file path within bundle (e.g. 'summary.md', 'project.json', 'alternatives/alternative_1/floor_1.png'). If omitted, lists available files.",
    ),
    registry: ProjectRegistry = Depends(get_project_registry),
):
    """Retrieve exported artifacts (reports, JSON, rendered PNGs, ZIP archive).

    Guarantees strict filesystem safety: any attempted directory traversal outside
    the project's export directory is immediately rejected.
    """
    res = registry.get_result(project_id)
    bundle_path_str = res.export_bundle_path if res else None

    # Fallback to standard output path if registry cleared
    if not bundle_path_str:
        candidate_bundle = Path("outputs") / project_id
        if candidate_bundle.exists() and candidate_bundle.is_dir():
            bundle_path_str = str(candidate_bundle)

    if not bundle_path_str or not Path(bundle_path_str).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export bundle for project '{project_id}' does not exist.",
        )

    bundle_root = Path(bundle_path_str).resolve()

    # If specific file is requested, resolve safely and stream
    if file:
        safe_target = resolve_safe_path(bundle_root, file)
        mime_type, _ = mimetypes.guess_type(str(safe_target))
        mime_type = mime_type or "application/octet-stream"
        return FileResponse(
            path=str(safe_target),
            media_type=mime_type,
            filename=safe_target.name,
        )

    # Otherwise, return an inventory of available exported artifacts
    files_list: List[ExportFileItem] = []
    for fp in bundle_root.rglob("*"):
        if fp.is_file():
            rel = fp.relative_to(bundle_root).as_posix()
            mtype, _ = mimetypes.guess_type(str(fp))
            files_list.append(
                ExportFileItem(
                    filename=fp.name,
                    relative_path=rel,
                    size_bytes=fp.stat().st_size,
                    media_type=mtype or "application/octet-stream",
                )
            )

    return ExportResponse(
        project_id=project_id,
        bundle_path=str(bundle_root),
        total_files=len(files_list),
        files=files_list,
    )

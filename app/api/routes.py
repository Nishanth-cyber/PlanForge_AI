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
from app.agents.requirement_agent.conversation import ConversationalRequirementAssistant
from app.api.errors import resolve_safe_path
from app.api.registry import ProjectRegistry
from app.api.schemas import (
    AlternativeSummarySchema,
    CancelRequestSchema,
    ChatActionSchema,
    ChatTurnRequest,
    ChatTurnResponse,
    ClarificationListResponse,
    ClarificationOptionSchema,
    ClarificationRequestSchema,
    ClarificationResponsePayload,
    ClarificationSubmitResponse,
    ExportFileItem,
    ExportResponse,
    GenerationRequest,
    GenerationResponse,
    HealthResponse,
    ProjectDetailResponse,
    QuestionCardSchema,
    QuickReplySchema,
    RequirementProgressItem,
    ResumeRequestSchema,
    ValidationSummarySchema,
    EditDesignRequest,
    EditDesignResponse,
    VersionSummarySchema,
)
from app.export.json_exporter import export_project_json
from app.export.dxf import DXFExporter, get_dxf_filename
from app.orchestration.config import OrchestrationConfig
from app.orchestration.orchestrator import PlanForgeOrchestrator
from app.utils.ids import generate_id

from app.chat.orchestrator import ChatOrchestrator

# Ensure standard CAD DXF MIME type is mapped
mimetypes.add_type("application/dxf", ".dxf")

router = APIRouter(tags=["PlanForge"])
assistant = ConversationalRequirementAssistant()
chat_orchestrator = ChatOrchestrator(assistant=assistant)


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System Health & Diagnostic Status",
)
def get_health() -> HealthResponse:
    """Return system readiness, framework versions, and execution environment."""
    return HealthResponse()


@router.post(
    "/chat",
    response_model=ChatTurnResponse,
    summary="Conversational Requirement Assistant",
)
def chat_turn(
    req: ChatTurnRequest,
    registry: ProjectRegistry = Depends(get_project_registry),
) -> ChatTurnResponse:
    """Execute a conversational interaction turn with the Requirement Agent and configured LLM.

    Analyzes natural language messages or card responses, invokes the LLM when configured,
    updates structured requirements, checks completeness, and returns the next dynamic question card.
    """
    chat_orchestrator.registry = registry
    conv_id = req.conversation_id
    result = chat_orchestrator.handle(
        message=req.message,
        existing_brief=req.existing_brief,
        project_name=req.project_name,
        project_id=req.project_id,
        history=[h.model_dump() for h in req.history] if req.history else None,
        active_floor=req.active_floor,
        alternative_index=req.alternative_index,
        input_source=req.input_source,
        conversation_id=conv_id,
    )
    res = result.turn
    action_dict = None
    if result.action is not None:
        if hasattr(result.action, "to_dict"):
            action_dict = result.action.to_dict()
        elif isinstance(result.action, dict):
            action_dict = result.action

    return ChatTurnResponse(
        message=res.message,
        question_card=QuestionCardSchema(**res.question_card.to_dict()) if res.question_card else None,
        is_ready_for_generation=res.is_ready_for_generation,
        requirements_text=res.requirements_text,
        requirements_summary=res.requirements_summary,
        progress=[RequirementProgressItem(**p.to_dict()) for p in res.progress],
        remaining_count=res.remaining_count,
        project_name=res.project_name,
        status=res.status,
        route=result.route,
        llm_used=result.llm_used,
        llm_provider=result.llm_provider,
        llm_model=result.llm_model,
        llm_latency_ms=result.llm_latency_ms,
        turn_id=result.turn_id,
        plan_modified=result.plan_modified,
        response_type=result.response_type.value if result.response_type else "text",
        intent=result.intent,
        conversation_stage=result.stage or "DISCOVERY",
        quick_replies=[QuickReplySchema(label=q.label, value=q.value) for q in result.quick_replies],
        missing_requirements=result.missing_requirements or [],
        requirements_updated=result.requirements_updated or [],
        action=ChatActionSchema(**action_dict) if action_dict else None,
        conversation_id=result.conversation_id or conv_id,
        project_id=result.project_id or req.project_id,
    )




def _build_generation_response(result: PipelineResult) -> GenerationResponse:
    """Helper to convert PipelineResult into GenerationResponse with pending clarification support."""
    val_summary = None
    if result.validation_report:
        val_summary = ValidationSummarySchema(
            overall_valid=result.validation_report.overall_valid,
            overall_score=round(result.validation_report.overall_score, 2),
            total_errors=result.validation_report.total_errors,
            total_warnings=result.validation_report.total_warnings,
        )

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

    pending_clarification = None
    if result.agentic_state and result.agentic_state.get("pending_clarification"):
        pending_clarification = result.agentic_state.get("pending_clarification")

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
        pending_clarification=pending_clarification,
        error_message=result.error_message,
        agentic_state=result.agentic_state,
        decisions=result.decisions,
    )


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
    """Execute the complete PlanForge generative pipeline or multi-agent coordinator."""
    cfg = OrchestrationConfig(
        enable_refinement=req.enable_refinement,
        max_refinement_iterations=req.max_refinement_iterations,
        num_alternatives=req.num_alternatives,
        enable_rendering=req.enable_rendering,
        enable_exports=req.enable_exports,
        create_zip=req.create_zip,
        output_dir=req.output_dir,
        interactive=req.interactive,
    )

    brief_to_use = req.brief or ""
    if req.plot_shape and len(req.plot_shape) >= 3 and "polygon:" not in brief_to_use.lower() and "plot shape:" not in brief_to_use.lower():
        coords_str = ", ".join(f"({float(p[0])}, {float(p[1])})" for p in req.plot_shape)
        brief_to_use = f"Plot polygon: {coords_str}\n" + brief_to_use

    mode_val = getattr(req, "mode", "standard")
    pid = req.project_id or generate_id("proj")
    pname = req.project_name
    cid = getattr(req, "conversation_id", None)
    if cid:
        from app.chat.state import conversation_store
        conversation_store.begin_generation(cid, pid)

    if mode_val in ("multi_agent", "hierarchical") or (mode_val == "agentic" and req.interactive):
        from app.orchestration.hierarchical import HierarchicalOrchestrator
        hierarchical = HierarchicalOrchestrator(
            registry=orchestrator.tool_registry,
            budget=getattr(cfg, "budget", None),
            interactive=req.interactive,
        )
        project_state = hierarchical.run(
            project_id=pid,
            goal=pname,
            raw_brief=brief_to_use,
            inputs={
                "output_dir": cfg.output_dir,
                "project_name": pname,
                "num_alternatives": cfg.num_alternatives,
            },
        )
        result = orchestrator._create_result_from_agentic_state(
            project_state, pid, pname, cfg, event_log=hierarchical.event_log
        )
        registry.save_result(result, state=project_state, orchestrator=hierarchical, config=cfg)
    elif mode_val == "agentic":
        result = orchestrator.generate_agentic(
            raw_brief=brief_to_use,
            project_name=pname,
            project_id=pid,
            config=cfg,
        )
        registry.save_result(result)
    else:
        result = orchestrator.generate(
            raw_brief=brief_to_use,
            project_name=pname,
            project_id=pid,
            config=cfg,
        )
        registry.save_result(result)

    if cid:
        from app.chat.state import conversation_store
        conversation_store.finish_generation(
            cid,
            ok=result.is_success,
            project_id=result.project_id,
            status=result.status,
            valid=result.is_valid,
            error=result.error_message,
        )

    return _build_generation_response(result)



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
    zip_path = Path("outputs") / f"{project_id}.zip"
    if zip_path.exists() and zip_path.is_file():
        try:
            zip_path.unlink()
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


@router.delete(
    "/projects",
    summary="Clear All Generated Projects",
)
def clear_all_projects(
    registry: ProjectRegistry = Depends(get_project_registry),
) -> Dict[str, Any]:
    """Clear all generated projects from in-memory registry and disk outputs."""
    registry.clear()
    cleared_count = 0
    outputs_dir = Path("outputs")
    preserved = {"dxf", "json", "png"}
    if outputs_dir.exists() and outputs_dir.is_dir():
        for item in outputs_dir.iterdir():
            if item.is_dir() and item.name not in preserved:
                try:
                    shutil.rmtree(item)
                    cleared_count += 1
                except Exception:
                    pass
            elif item.is_file():
                try:
                    item.unlink()
                    cleared_count += 1
                except Exception:
                    pass
    return {
        "status": "cleared",
        "cleared_count": cleared_count,
    }



# ==============================================================================
# Phase 7: Interactive Clarification and Resumable Workflow Endpoints
# ==============================================================================


@router.get(
    "/projects/{project_id}/clarifications",
    response_model=ClarificationListResponse,
    summary="Retrieve Pending and Historical Clarifications",
)
def get_project_clarifications(
    project_id: str,
    registry: ProjectRegistry = Depends(get_project_registry),
) -> ClarificationListResponse:
    """Retrieve active pending clarification request, history, and requirement changes."""
    data = registry.get_clarifications(project_id)
    if data["status"] == "not_found":
        pjson_path = Path("outputs") / project_id / "project.json"
        if not pjson_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found.",
            )

    pending_schema = None
    if data.get("pending_clarification"):
        pending_schema = ClarificationRequestSchema(**data["pending_clarification"])

    return ClarificationListResponse(
        project_id=project_id,
        status=data["status"],
        state_version=data["state_version"],
        pending_clarification=pending_schema,
        clarification_history=data.get("clarification_history", []),
        requirement_changes=data.get("requirement_changes", []),
    )


@router.post(
    "/projects/{project_id}/clarifications/{request_id}/response",
    response_model=ClarificationSubmitResponse,
    summary="Submit User Response to Clarification Request",
)
def submit_clarification_response(
    project_id: str,
    request_id: str,
    payload: ClarificationResponsePayload,
    registry: ProjectRegistry = Depends(get_project_registry),
) -> ClarificationSubmitResponse:
    """Submit a user response (selected option, numeric override, or free text) to an active clarification request."""
    success, msg, resp, state = registry.submit_clarification_response(
        project_id=project_id,
        request_id=request_id,
        selected_option_id=payload.selected_option_id,
        user_response_text=payload.user_response_text,
        numeric_overrides=payload.numeric_overrides,
        expected_state_version=payload.expected_state_version,
    )
    if not success:
        if "not found in active session" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        if "stale response" in msg.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    pending_schema = None
    if state and state.pending_clarification:
        pending_schema = ClarificationRequestSchema(**state.pending_clarification.to_dict())

    return ClarificationSubmitResponse(
        success=True,
        message=msg,
        status=state.status.value if state else "accepted",
        state_version=state.version if state else 0,
        pending_clarification=pending_schema,
    )


@router.post(
    "/projects/{project_id}/resume",
    response_model=GenerationResponse,
    summary="Resume Paused Floor-Plan Generation Workflow",
)
def resume_project_workflow(
    project_id: str,
    payload: ResumeRequestSchema = ResumeRequestSchema(),
    registry: ProjectRegistry = Depends(get_project_registry),
) -> GenerationResponse:
    """Resume execution of a paused or waiting generation workflow from its paused stage."""
    success, msg, result = registry.resume_project(project_id)
    if not success or not result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return _build_generation_response(result)


@router.post(
    "/projects/{project_id}/cancel",
    response_model=GenerationResponse,
    summary="Cancel Ongoing or Paused Generation Session",
)
def cancel_project_workflow(
    project_id: str,
    payload: CancelRequestSchema = CancelRequestSchema(),
    registry: ProjectRegistry = Depends(get_project_registry),
) -> GenerationResponse:
    """Cancel an active, waiting, or paused generation workflow."""
    success, msg, result = registry.cancel_project(project_id, reason=payload.reason or "User cancelled")
    if not success or not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    return _build_generation_response(result)


# ==============================================================================
# Natural-Language Editing & Project Versioning Endpoints
# ==============================================================================


@router.post(
    "/projects/{project_id}/edit",
    response_model=EditDesignResponse,
    summary="Edit Existing Floor Plan via Natural Language",
)
def edit_project_design(
    project_id: str,
    payload: EditDesignRequest,
    registry: ProjectRegistry = Depends(get_project_registry),
) -> EditDesignResponse:
    """Intelligently edit existing architectural design in place using natural language instructions."""
    res = registry.get_result(project_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    edit_res = registry.edit_project(
        project_id=project_id,
        instruction=payload.instruction,
        floor_number=payload.floor_number,
        alternative_index=payload.alternative_index or 1,
    )

    if not edit_res:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize design editing agent.",
        )

    val_summary = None
    if edit_res.validation_summary:
        val_summary = ValidationSummarySchema(**edit_res.validation_summary)

    return EditDesignResponse(
        success=edit_res.success,
        project_id=project_id,
        version_id=edit_res.version_id,
        instruction=edit_res.instruction,
        summary=edit_res.summary,
        is_valid=edit_res.is_valid,
        validation_summary=val_summary,
        affected_rooms=edit_res.affected_rooms,
        affected_elements=edit_res.affected_elements,
        can_undo=edit_res.can_undo,
        clarification_required=edit_res.clarification_required,
        clarification_question=edit_res.clarification_question,
        new_design_requested=edit_res.new_design_requested,
        error_message=edit_res.error_message,
        feasible_alternatives=edit_res.feasible_alternatives,
    )


@router.post(
    "/projects/{project_id}/undo",
    response_model=EditDesignResponse,
    summary="Undo Last Floor Plan Edit",
)
def undo_project_design(
    project_id: str,
    registry: ProjectRegistry = Depends(get_project_registry),
) -> EditDesignResponse:
    """Restore the previous design version safely and revalidate."""
    res = registry.get_result(project_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    undo_res = registry.undo_project(project_id)
    if not undo_res or not undo_res.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=undo_res.summary if undo_res else "Nothing to undo.",
        )

    val_summary = None
    if undo_res.validation_summary:
        val_summary = ValidationSummarySchema(**undo_res.validation_summary)

    return EditDesignResponse(
        success=undo_res.success,
        project_id=project_id,
        version_id=undo_res.version_id,
        instruction=undo_res.instruction,
        summary=undo_res.summary,
        is_valid=undo_res.is_valid,
        validation_summary=val_summary,
        affected_rooms=undo_res.affected_rooms,
        affected_elements=undo_res.affected_elements,
        can_undo=undo_res.can_undo,
        error_message=undo_res.error_message,
    )


@router.get(
    "/projects/{project_id}/versions",
    response_model=List[VersionSummarySchema],
    summary="List Design Version History",
)
def get_project_versions(
    project_id: str,
    registry: ProjectRegistry = Depends(get_project_registry),
) -> List[VersionSummarySchema]:
    """Retrieve full version history snapshots for an edited project."""
    res = registry.get_result(project_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    summaries = registry.get_project_versions(project_id)
    return [VersionSummarySchema(**s) for s in summaries]


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
        data = export_project_json(
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
        data["status"] = res.status
        data["is_valid"] = res.is_valid
        data["is_success"] = res.is_success
        return data

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
        norm_file = file.replace("\\", "/")
        try:
            safe_target = resolve_safe_path(bundle_root, norm_file)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND and "/" not in norm_file:
                alt_target = bundle_root / "alternatives" / "alternative_1" / norm_file
                if alt_target.exists() and alt_target.is_file():
                    safe_target = alt_target
                else:
                    raise exc
            else:
                raise exc
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


@router.get(
    "/projects/{project_id}/export/dxf",
    summary="Download CAD Drawing (DXF)",
    response_class=FileResponse,
)
@router.get(
    "/projects/{project_id}/exports/dxf",
    summary="Download CAD Drawing (DXF) - Alias",
    response_class=FileResponse,
)
def download_project_dxf(
    project_id: str,
    floor: Optional[int] = Query(
        default=None,
        description="Optional specific floor number to export (defaults to all floors)",
    ),
    registry: ProjectRegistry = Depends(get_project_registry),
):
    """Download publication-ready CAD drawing (DXF) generated from validated PlanForge geometry.

    Adheres strictly to the authoritative Geometry Engine:
    - Verifies the floor plan passed validation (Requirement 15)
    - Rejects invalid floor plans with HTTP 400
    - Returns FileResponse with media_type='application/dxf'
    """
    res = registry.get_result(project_id)

    # Fallback path if registry was cleared
    candidate_bundle = Path("outputs") / project_id
    bundle_path_str = res.export_bundle_path if res else (str(candidate_bundle) if candidate_bundle.exists() else None)

    if not res and not bundle_path_str:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    # Validation check (Requirement 15)
    if res:
        if res.floor_plan_set:
            if res.floor_plan_set.validation_report and not res.floor_plan_set.all_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Floor plan failed validation. CAD DXF export is strictly available only for valid, passing floor plans.",
                )
        elif res.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project is not completed or valid. CAD DXF export is unavailable.",
            )

    bundle_root = Path(bundle_path_str or (Path("outputs") / project_id)).resolve()
    bundle_root.mkdir(parents=True, exist_ok=True)

    target_dxf: Optional[Path] = None

    # Check for existing DXF in bundle directory
    existing_dxfs = sorted(list(bundle_root.glob("*.dxf")), key=lambda p: p.stat().st_size, reverse=True)
    if existing_dxfs and floor is None:
        target_dxf = existing_dxfs[0]

    # If floor-specific or not yet on disk, generate on the fly from authoritative geometry
    if target_dxf is None or floor is not None:
        primary_fps = None
        if res and res.floor_plan_set:
            primary_fps = res.floor_plan_set
        elif res and res.alternative_set and res.alternative_set.alternatives:
            primary_fps = res.alternative_set.alternatives[0].floor_plan_set

        if not primary_fps or not primary_fps.floor_plans:
            if existing_dxfs:
                target_dxf = existing_dxfs[0]
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No valid floor plan geometry available to generate DXF for project '{project_id}'.",
                )
        else:
            proj_title = (res.project_name if res else "") or primary_fps.project_name or project_id
            exporter = DXFExporter()

            if floor is not None:
                single_fp = primary_fps.get_floor_plan(floor)
                if not single_fp:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Floor {floor} not found in project '{project_id}'.",
                    )
                target_dxf = bundle_root / f"floor_{floor}.dxf"
                exporter.export_floor_plan(
                    floor_plan=single_fp,
                    output_path=target_dxf,
                    fallback_plot_boundary=primary_fps.plot_boundary,
                    fallback_buildable_boundary=primary_fps.buildable_boundary,
                    project_name=f"{proj_title} (Floor {floor})",
                )
            else:
                is_mf = len(primary_fps.floor_plans) > 1
                dxf_name = get_dxf_filename(proj_title, is_multi_floor=is_mf)
                target_dxf = bundle_root / dxf_name
                exporter.export_floor_plan_set(
                    floor_plan_set=primary_fps,
                    output_path=target_dxf,
                    project_name=proj_title,
                )

    if not target_dxf or not target_dxf.exists() or target_dxf.stat().st_size == 0:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate or locate valid CAD DXF file for project '{project_id}'.",
        )

    return FileResponse(
        path=str(target_dxf),
        media_type="application/dxf",
        filename=target_dxf.name,
        headers={"Content-Disposition": f'attachment; filename="{target_dxf.name}"'},
    )


@router.get(
    "/projects/{project_id}/export/svg",
    summary="Download Vector Floor Plan (SVG)",
    response_class=FileResponse,
)
@router.get(
    "/projects/{project_id}/exports/svg",
    summary="Download Vector Floor Plan (SVG) - Alias",
    response_class=FileResponse,
)
def download_project_svg(
    project_id: str,
    floor: int = Query(default=1, description="Floor number to export as SVG"),
    registry: ProjectRegistry = Depends(get_project_registry),
):
    """Download publication-grade vector drawing (SVG) for a floor."""
    res = registry.get_result(project_id)
    candidate_bundle = Path("outputs") / project_id
    bundle_path_str = res.export_bundle_path if res else (str(candidate_bundle) if candidate_bundle.exists() else None)

    if not bundle_path_str or not Path(bundle_path_str).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found.",
        )

    bundle_root = Path(bundle_path_str).resolve()
    target_svg: Optional[Path] = None

    # Check in alternatives or bundle root
    for candidate in [
        bundle_root / "alternatives" / "alternative_1" / f"floor_{floor}.svg",
        bundle_root / "floors" / f"floor_{floor}.svg",
        bundle_root / f"floor_{floor}.svg",
    ]:
        if candidate.exists() and candidate.stat().st_size > 0:
            target_svg = candidate
            break

    # If not on disk, generate on the fly using FloorPlanRenderer
    if target_svg is None:
        primary_fps = None
        if res and res.floor_plan_set:
            primary_fps = res.floor_plan_set
        elif res and res.alternative_set and res.alternative_set.alternatives:
            primary_fps = res.alternative_set.alternatives[0].floor_plan_set

        if primary_fps and primary_fps.floor_plans:
            single_fp = primary_fps.get_floor_plan(floor)
            if not single_fp:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Floor {floor} not found in project '{project_id}'.",
                )
            from app.rendering.floor_renderer import FloorPlanRenderer
            renderer = FloorPlanRenderer()
            target_svg = bundle_root / f"floor_{floor}.svg"
            renderer.render_floor_plan(
                floor_plan=single_fp,
                output_path=target_svg,
                orientation=res.requirements.orientation if res and res.requirements else None,
                project_name=res.project_name if res else primary_fps.project_name,
                fallback_plot_boundary=primary_fps.plot_boundary,
                fallback_buildable_boundary=primary_fps.buildable_boundary,
            )

    if not target_svg or not target_svg.exists() or target_svg.stat().st_size == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SVG drawing for floor {floor} in project '{project_id}' could not be located or generated.",
        )

    return FileResponse(
        path=str(target_svg),
        media_type="image/svg+xml",
        filename=target_svg.name,
        headers={"Content-Disposition": f'attachment; filename="{target_svg.name}"'},
    )


@router.get(
    "/projects/{project_id}/export/zip",
    summary="Download Complete Project ZIP Archive",
    response_class=FileResponse,
)
@router.get(
    "/projects/{project_id}/exports/zip",
    summary="Download Complete Project ZIP Archive - Alias",
    response_class=FileResponse,
)
def download_project_zip(
    project_id: str,
    registry: ProjectRegistry = Depends(get_project_registry),
):
    """Package and stream complete project export bundle as a ZIP archive."""
    res = registry.get_result(project_id)
    candidate_bundle = Path("outputs") / project_id
    bundle_path_str = res.export_bundle_path if res else (str(candidate_bundle) if candidate_bundle.exists() else None)

    if not bundle_path_str or not Path(bundle_path_str).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_id}' not found or has no export bundle.",
        )

    bundle_root = Path(bundle_path_str).resolve()
    zip_path = bundle_root.parent / f"{project_id}.zip"

    # Package into ZIP archive
    import zipfile
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file_path in bundle_root.rglob("*"):
            if file_path.is_file() and not file_path.name.endswith(".zip"):
                arcname = file_path.relative_to(bundle_root.parent)
                zipf.write(file_path, arcname)

    proj_name = (res.project_name if res else "") or project_id
    from app.export.dxf.exporter import sanitize_project_name
    slug = sanitize_project_name(proj_name) or project_id
    out_filename = f"{slug}_bundle.zip"

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=out_filename,
        headers={"Content-Disposition": f'attachment; filename="{out_filename}"'},
    )


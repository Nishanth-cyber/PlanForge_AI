"""Structured JSON serialization for PlanForge project results."""

from __future__ import annotations
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Union

from app.models.requirements import Requirements
from app.models.planning import PlanningSpec
from app.models.allocation import AllocationSet
from app.models.architectural_design import ArchitecturalDesignSet
from app.models.floor_plan import FloorPlanSet
from app.models.validation import ValidationReport, ValidationResult
from app.models.refinement import RefinementResult
from app.models.alternatives import DesignAlternative, DesignAlternativeSet
from app.explainability.models import DecisionTrace
from app.export.errors import InvalidExportInputError


def to_serializable(obj: Any) -> Any:
    """Recursively convert dataclasses, enums, tuples, and sets to JSON-serializable primitives."""
    if obj is None:
        return None
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (tuple, set)):
        return [to_serializable(item) for item in obj]
    if isinstance(obj, list):
        return [to_serializable(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, ValidationReport):
        rep_dict = asdict(obj)
        rep_dict["overall_valid"] = obj.overall_valid
        rep_dict["overall_score"] = round(obj.overall_score, 2)
        rep_dict["total_errors"] = obj.total_errors
        rep_dict["total_warnings"] = obj.total_warnings
        return to_serializable(rep_dict)
    if isinstance(obj, ValidationResult):
        res_dict = asdict(obj)
        res_dict["has_errors"] = obj.has_errors
        res_dict["has_warnings"] = obj.has_warnings
        res_dict["error_count"] = obj.error_count
        res_dict["warning_count"] = obj.warning_count
        return to_serializable(res_dict)
    if is_dataclass(obj):
        # asdict converts dataclass recursively, but we still need enum/tuple conversion
        return to_serializable(asdict(obj))
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return to_serializable(obj.to_dict())
    if hasattr(obj, "model_dump") and callable(obj.model_dump):
        return to_serializable(obj.model_dump())
    return obj


def export_alternative_json(alternative: DesignAlternative) -> Dict[str, Any]:
    """Serialize a single DesignAlternative into a dictionary preserving IDs and metadata."""
    if not alternative:
        raise InvalidExportInputError("DesignAlternative cannot be None.")

    alt_dict: Dict[str, Any] = {
        "alternative_id": alternative.alternative_id,
        "index": alternative.index,
        "strategy": alternative.strategy,
        "status": alternative.status.value if isinstance(alternative.status, Enum) else str(alternative.status),
        "is_valid": alternative.is_valid,
        "rejection_reason": alternative.rejection_reason,
        "design_rationale": alternative.design_rationale,
        "characteristics": list(alternative.characteristics),
        "diversity_scores": dict(alternative.diversity_scores),
    }

    if alternative.design_signature:
        alt_dict["design_signature"] = alternative.design_signature.to_dict()

    if alternative.architectural_design:
        alt_dict["architectural_design"] = to_serializable(alternative.architectural_design)

    if alternative.floor_plan_set:
        alt_dict["floor_plan_set"] = to_serializable(alternative.floor_plan_set)

    if alternative.validation_report:
        alt_dict["validation_report"] = to_serializable(alternative.validation_report)

    if alternative.refinement_result:
        alt_dict["refinement_result"] = to_serializable(alternative.refinement_result)

    return alt_dict


def export_project_json(
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
) -> Dict[str, Any]:
    """Serialize complete PlanForge project output into structured JSON dictionary.

    Strict Invariant: Preserves all entity IDs (room_id, allocation_id,
    architectural_room_id, geo_room_id, validation_issue_id, change_id, alternative_id).
    """
    data: Dict[str, Any] = {
        "project_id": project_id,
        "project_metadata": {
            "project_id": project_id,
            "project_name": project_name or (requirements.project_name if requirements else ""),
            "exported_at": datetime.now().isoformat(),
            "schema_version": "1.0",
        }
    }

    if requirements:
        data["requirements"] = to_serializable(requirements)

    if planning_spec:
        data["planning_spec"] = to_serializable(planning_spec)

    if allocation_set:
        data["allocation_set"] = to_serializable(allocation_set)

    if architectural_design_set:
        data["architectural_design_set"] = to_serializable(architectural_design_set)

    if floor_plan_set:
        data["floor_plan_set"] = to_serializable(floor_plan_set)

    if validation_report:
        data["validation_report"] = to_serializable(validation_report)

    if refinement_result:
        data["refinement_result"] = to_serializable(refinement_result)

    if alternative_set:
        alts_data = [export_alternative_json(alt) for alt in alternative_set.alternatives]
        data["alternatives"] = alts_data
        data["alternative_set"] = {
            "id": alternative_set.id,
            "project_name": alternative_set.project_name,
            "requested_count": alternative_set.requested_count,
            "candidates_generated": alternative_set.candidates_generated,
            "valid_count": alternative_set.valid_count,
            "strategies_attempted": list(alternative_set.strategies_attempted),
            "status": alternative_set.status,
            "generation_summary": alternative_set.generation_summary,
            "alternatives": alts_data,
            "rejected_candidates": [export_alternative_json(rej) for rej in alternative_set.rejected_candidates],
        }

    if decision_trace:
        data["decision_trace"] = decision_trace.to_dict()

    return data


def save_json(data: Dict[str, Any], output_path: Union[str, Path], indent: int = 2) -> Path:
    """Write dictionary to formatted JSON file."""
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
    return out_p

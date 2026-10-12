"""Candidate management and design quality evaluation for agentic refinement.

Provides authoritative candidate comparison, metric evaluation, best-valid preservation,
and regression rejection to ensure worse designs never overwrite better valid candidates.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.agentic.util import to_jsonable
from app.models.validation import ValidationIssue, ValidationReport
from app.utils.ids import generate_id

logger = logging.getLogger(__name__)


@dataclass
class CandidateEvaluation:
    """Structured quality assessment of a design candidate."""

    candidate_id: str
    is_valid: bool
    overall_score: float
    hard_error_count: int
    warning_count: int
    defect_categories: List[str] = field(default_factory=list)
    metric_breakdown: Dict[str, float] = field(default_factory=dict)
    comparison_with_predecessor: Dict[str, Any] = field(default_factory=dict)
    acceptance_decision: str = "pending"  # "accepted_best" | "accepted_progress" | "rejected_regression" | "rejected_invalid"
    decision_reason: str = ""
    evidence_refs: List[str] = field(default_factory=list)

    @property
    def validation_score(self) -> float:
        return self.overall_score

    def to_dict(self) -> Dict[str, Any]:
        return to_jsonable(self.__dict__)


@dataclass
class CandidateRecord:
    """Immutable snapshot of an evaluated design candidate."""

    id: str
    step: int
    source_action: str
    evaluation: CandidateEvaluation
    fingerprint: str
    floor_plan_set: Any = field(repr=False)
    architectural_design_set: Any = field(repr=False, default=None)
    allocation_set: Any = field(repr=False, default=None)
    planning_spec: Any = field(repr=False, default=None)
    validation_report: Optional[ValidationReport] = field(repr=False, default=None)
    parent_candidate_id: Optional[str] = None
    status: str = "evaluated"  # "accepted_best" | "rejected" | "superseded" | "diagnostic_only"

    @property
    def candidate_id(self) -> str:
        return self.id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "step": self.step,
            "source_action": self.source_action,
            "is_valid": self.evaluation.is_valid,
            "overall_score": self.evaluation.overall_score,
            "hard_error_count": self.evaluation.hard_error_count,
            "warning_count": self.evaluation.warning_count,
            "acceptance_decision": self.evaluation.acceptance_decision,
            "decision_reason": self.evaluation.decision_reason,
            "fingerprint": self.fingerprint,
            "parent_candidate_id": self.parent_candidate_id,
            "status": self.status,
            "defect_categories": self.evaluation.defect_categories,
        }


class DesignQualityEvaluator:
    """Authoritative evaluator comparing candidates against predecessors and best-known designs."""

    @classmethod
    def evaluate(
        cls,
        candidate_id: str,
        validation_report: Optional[ValidationReport],
        floor_plan_set: Any,
        predecessor_eval: Optional[CandidateEvaluation] = None,
        planning_spec: Any = None,
        requirements: Any = None,
    ) -> CandidateEvaluation:
        """Compute structured metrics and evaluate candidate quality."""
        if validation_report is None:
            return CandidateEvaluation(
                candidate_id=candidate_id,
                is_valid=False,
                overall_score=0.0,
                hard_error_count=999,
                warning_count=0,
                defect_categories=["missing_validation"],
                acceptance_decision="rejected_invalid",
                decision_reason="Candidate has no validation report",
            )

        is_valid = bool(validation_report.overall_valid)
        overall_score = float(validation_report.overall_score)
        hard_errors = validation_report.total_errors
        warnings = validation_report.total_warnings

        # Extract defect categories from issues
        defect_cats: List[str] = []
        for issue in validation_report.all_issues():
            cat = issue.category or issue.check or "general"
            if cat not in defect_cats:
                defect_cats.append(cat)

        # Metric breakdown
        metrics: Dict[str, float] = {
            "validation_score": round(overall_score, 1),
            "hard_errors": float(hard_errors),
            "warnings": float(warnings),
        }

        # Check room count adherence if requirements available
        if requirements and hasattr(requirements, "floors") and floor_plan_set and hasattr(floor_plan_set, "floor_plans"):
            expected_rooms = sum(
                len(getattr(f, "room_requirements", [])) for f in requirements.floors
            )
            actual_rooms = 0
            for fp in floor_plan_set.floor_plans:
                fp_rooms = getattr(fp, "rooms", [])
                if not fp_rooms and getattr(fp, "geometry", None):
                    fp_rooms = getattr(fp.geometry, "rooms", [])
                actual_rooms += len(fp_rooms)
            metrics["expected_rooms"] = float(expected_rooms)
            metrics["actual_rooms"] = float(actual_rooms)
            metrics["room_coverage_ratio"] = round(actual_rooms / max(1, expected_rooms), 3)

        # Comparison with predecessor
        comparison: Dict[str, Any] = {}
        if predecessor_eval is not None:
            score_delta = round(overall_score - predecessor_eval.overall_score, 2)
            errors_delta = hard_errors - predecessor_eval.hard_error_count
            warnings_delta = warnings - predecessor_eval.warning_count

            # Determine issues resolved and introduced
            prev_cats = set(predecessor_eval.defect_categories)
            curr_cats = set(defect_cats)
            resolved = list(prev_cats - curr_cats)
            introduced = list(curr_cats - prev_cats)

            comparison = {
                "predecessor_id": predecessor_eval.candidate_id,
                "score_delta": score_delta,
                "errors_delta": errors_delta,
                "warnings_delta": warnings_delta,
                "defects_resolved": resolved,
                "defects_introduced": introduced,
            }

        evidence = [f"score={overall_score:.1f}", f"hard_errors={hard_errors}"]
        if defect_cats:
            evidence.append(f"defects={','.join(defect_cats[:3])}")

        return CandidateEvaluation(
            candidate_id=candidate_id,
            is_valid=is_valid,
            overall_score=overall_score,
            hard_error_count=hard_errors,
            warning_count=warnings,
            defect_categories=defect_cats,
            metric_breakdown=metrics,
            comparison_with_predecessor=comparison,
            evidence_refs=evidence,
        )

    @classmethod
    def should_accept_as_best(
        cls,
        new_eval: CandidateEvaluation,
        current_best: Optional[CandidateEvaluation],
    ) -> Tuple[bool, str]:
        """Determine whether new_eval qualifies to replace current_best.

        Strict Rules:
        1. A valid design ALWAYS beats an invalid design.
        2. An invalid design can NEVER overwrite a valid design.
        3. If both valid: new must not have more hard errors (0) and must have higher/equal score.
        4. If both invalid: new must have fewer hard errors or strictly better diagnostic score.
        5. A design that introduces new hard errors is ALWAYS rejected as a regression.
        """
        if current_best is None:
            reason = "Initial baseline candidate established" if new_eval.is_valid else "Initial diagnostic baseline candidate"
            return True, reason

        # Rule 1 & 2: Validity takes absolute precedence
        if new_eval.is_valid and not current_best.is_valid:
            return True, "Valid candidate achieved; replacing invalid predecessor"

        if not new_eval.is_valid and current_best.is_valid:
            return False, f"Regression rejected: Candidate has {new_eval.hard_error_count} hard error(s); cannot replace valid best"

        # Rule 3: Both valid
        if new_eval.is_valid and current_best.is_valid:
            if new_eval.overall_score > current_best.overall_score:
                return True, f"Score improved from {current_best.overall_score:.1f} to {new_eval.overall_score:.1f}"
            if new_eval.overall_score == current_best.overall_score and new_eval.warning_count < current_best.warning_count:
                return True, f"Soft warnings reduced from {current_best.warning_count} to {new_eval.warning_count}"
            return False, f"No quality improvement over best valid score ({current_best.overall_score:.1f})"

        # Rule 4 & 5: Both invalid (diagnostic comparison)
        if new_eval.hard_error_count < current_best.hard_error_count:
            return True, f"Hard errors reduced from {current_best.hard_error_count} to {new_eval.hard_error_count}"

        if new_eval.hard_error_count > current_best.hard_error_count:
            return False, f"Hard error regression: increased from {current_best.hard_error_count} to {new_eval.hard_error_count}"

        if new_eval.overall_score > current_best.overall_score:
            return True, f"Diagnostic score improved from {current_best.overall_score:.1f} to {new_eval.overall_score:.1f}"

        return False, "No diagnostic improvement over existing candidate"


class CandidateManager:
    """Tracks candidate history, evaluates candidate progressions, and preserves best valid designs."""

    def __init__(self) -> None:
        self.candidates: List[CandidateRecord] = []
        self.best_valid_candidate: Optional[CandidateRecord] = None
        self.best_diagnostic_candidate: Optional[CandidateRecord] = None

    def compute_fingerprint(self, floor_plan_set: Any) -> str:
        """Compute structural hash of floor plan geometry."""
        if not floor_plan_set or not hasattr(floor_plan_set, "floor_plans"):
            return "empty"
        data = []
        for fp in floor_plan_set.floor_plans:
            rooms = getattr(fp, "rooms", [])
            if not rooms and getattr(fp, "geometry", None):
                rooms = getattr(fp.geometry, "rooms", [])
            for r in rooms:
                poly_coords = []
                poly = getattr(r, "polygon", None)
                if poly:
                    if hasattr(poly, "exterior"):
                        poly_coords = [(round(x, 2), round(y, 2)) for x, y in poly.exterior.coords]
                    elif isinstance(poly, (list, tuple)):
                        poly_coords = [(round(p[0], 2), round(p[1], 2)) for p in poly]
                data.append({"floor": getattr(fp, "floor_number", 1), "id": getattr(r, "id", ""), "poly": poly_coords})
        raw = json.dumps(data, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def register_candidate(
        self,
        step: int,
        source_action: str,
        floor_plan_set: Any,
        validation_report: Optional[ValidationReport],
        architectural_design_set: Any = None,
        allocation_set: Any = None,
        planning_spec: Any = None,
        requirements: Any = None,
    ) -> Tuple[CandidateRecord, bool]:
        """Evaluate, record, and check if candidate improves the best valid design.

        Returns:
            Tuple of (candidate_record, is_new_best)
        """
        cid = f"cand_{len(self.candidates) + 1}"
        fp_hash = self.compute_fingerprint(floor_plan_set)

        predecessor_eval = self.candidates[-1].evaluation if self.candidates else None
        current_best_eval = self.best_valid_candidate.evaluation if self.best_valid_candidate else (
            self.best_diagnostic_candidate.evaluation if self.best_diagnostic_candidate else None
        )

        evaluation = DesignQualityEvaluator.evaluate(
            candidate_id=cid,
            validation_report=validation_report,
            floor_plan_set=floor_plan_set,
            predecessor_eval=predecessor_eval,
            planning_spec=planning_spec,
            requirements=requirements,
        )

        is_new_best, decision_reason = DesignQualityEvaluator.should_accept_as_best(
            new_eval=evaluation,
            current_best=current_best_eval,
        )

        evaluation.decision_reason = decision_reason

        record = CandidateRecord(
            id=cid,
            step=step,
            source_action=source_action,
            evaluation=evaluation,
            fingerprint=fp_hash,
            floor_plan_set=floor_plan_set,
            architectural_design_set=architectural_design_set,
            allocation_set=allocation_set,
            planning_spec=planning_spec,
            validation_report=validation_report,
            parent_candidate_id=self.candidates[-1].id if self.candidates else None,
        )

        if evaluation.is_valid:
            if is_new_best:
                evaluation.acceptance_decision = "accepted_best"
                record.status = "accepted_best"
                if self.best_valid_candidate:
                    self.best_valid_candidate.status = "superseded"
                self.best_valid_candidate = record
            else:
                evaluation.acceptance_decision = "rejected_regression"
                record.status = "rejected"
        else:
            if is_new_best:
                evaluation.acceptance_decision = "accepted_progress"
                record.status = "diagnostic_only"
                self.best_diagnostic_candidate = record
            else:
                evaluation.acceptance_decision = "rejected_invalid"
                record.status = "rejected"

        self.candidates.append(record)
        return record, is_new_best

    def get_best_valid(self) -> Optional[CandidateRecord]:
        """Return the highest quality valid candidate, or None if no valid candidate exists."""
        return self.best_valid_candidate

    def get_best_overall(self) -> Optional[CandidateRecord]:
        """Return best valid candidate if available, else best diagnostic candidate."""
        return self.best_valid_candidate or self.best_diagnostic_candidate

    def has_valid_candidate(self) -> bool:
        """Return True if any candidate satisfies all mandatory acceptance criteria."""
        return self.best_valid_candidate is not None

    @property
    def best_record(self) -> Optional[CandidateRecord]:
        """Convenience property returning best overall candidate."""
        return self.get_best_overall()

    def all_summaries(self) -> List[Dict[str, Any]]:
        """Return public list of candidate records for reporting/observability."""
        return [c.to_dict() for c in self.candidates]

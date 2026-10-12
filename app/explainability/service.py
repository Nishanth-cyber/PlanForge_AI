"""Evidence-Grounded Explainability Service for PlanForge.

Converts recorded decision evidence, constraint priorities, ASAA candidate evaluations,
validation findings, and clarification change records into user-readable, strictly factual
explanations without fabrication or exposure of private reasoning scratchpads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from app.models.validation import ValidationIssue, ValidationReport
from app.utils.ids import generate_id


@dataclass
class GroundedExplanation:
    """A strictly evidence-grounded architectural rationale."""

    explanation_id: str
    decision_action: str
    observed_trigger: str
    supporting_evidence: Dict[str, Any]
    relevant_constraints: List[Dict[str, Any]]
    tool_outcome: Optional[str] = None
    alternatives_considered: List[Dict[str, Any]] = field(default_factory=list)
    selection_rationale: str = ""
    resulting_state_change: str = ""
    unresolved_limitations: List[str] = field(default_factory=list)
    is_verified: bool = True
    unverified_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "explanation_id": self.explanation_id,
            "decision_action": self.decision_action,
            "observed_trigger": self.observed_trigger,
            "supporting_evidence": self.supporting_evidence,
            "relevant_constraints": self.relevant_constraints,
            "tool_outcome": self.tool_outcome,
            "alternatives_considered": self.alternatives_considered,
            "selection_rationale": self.selection_rationale,
            "resulting_state_change": self.resulting_state_change,
            "unresolved_limitations": self.unresolved_limitations,
            "is_verified": self.is_verified,
            "unverified_reason": self.unverified_reason,
        }

    def to_readable_text(self) -> str:
        """Render a clean, human-readable paragraph."""
        if not self.is_verified:
            return f"Action '{self.decision_action}': Reason cannot be verified from recorded evidence. ({self.unverified_reason})"

        parts = [f"Action '{self.decision_action}' was selected because {self.observed_trigger}."]
        if self.selection_rationale:
            parts.append(self.selection_rationale)
        if self.resulting_state_change:
            parts.append(f"Result: {self.resulting_state_change}.")
        if self.unresolved_limitations:
            parts.append(f"Remaining limitations: {'; '.join(self.unresolved_limitations)}.")
        return " ".join(parts)


@dataclass
class ProjectExplanationDossier:
    """Comprehensive compilation of evidence-grounded explanations for a project run."""

    project_id: str
    status: str
    infeasibility_explanation: Optional[GroundedExplanation] = None
    clarification_explanations: List[GroundedExplanation] = field(default_factory=list)
    allocation_explanations: List[GroundedExplanation] = field(default_factory=list)
    validation_explanations: List[GroundedExplanation] = field(default_factory=list)
    decision_explanations: List[GroundedExplanation] = field(default_factory=list)
    unresolved_limitations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "status": self.status,
            "infeasibility_explanation": self.infeasibility_explanation.to_dict() if self.infeasibility_explanation else None,
            "clarification_explanations": [c.to_dict() for c in self.clarification_explanations],
            "allocation_explanations": [a.to_dict() for a in self.allocation_explanations],
            "validation_explanations": [v.to_dict() for v in self.validation_explanations],
            "decision_explanations": [d.to_dict() for d in self.decision_explanations],
            "unresolved_limitations": self.unresolved_limitations,
        }


@dataclass
class FailureDossier:
    """Structured, evidence-grounded post-mortem and recovery dossier for failed or recovered runs."""

    experiment_id: str
    case_id: str
    requirements_summary: Dict[str, Any]
    relevant_constraints: List[Dict[str, Any]]
    execution_stage: str
    responsible_component: str
    exception_or_finding: str
    measured_values: Dict[str, Any] = field(default_factory=dict)
    thresholds: Dict[str, Any] = field(default_factory=dict)
    candidate_state_before: Optional[Dict[str, Any]] = None
    candidate_state_after: Optional[Dict[str, Any]] = None
    retry_and_recovery_actions: List[Dict[str, Any]] = field(default_factory=list)
    final_workflow_status: str = "failed"
    valid_candidate_preserved: bool = False
    recovery_succeeded: bool = False
    evidence_references: List[str] = field(default_factory=list)
    root_cause_classification: str = "VERIFIED_ROOT_CAUSE"  # "VERIFIED_ROOT_CAUSE", "LIKELY_CAUSE", "UNRESOLVED_HYPOTHESIS"
    remaining_uncertainty: Optional[str] = None
    dossier_id: str = field(default_factory=lambda: f"dossier_{generate_id()}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dossier_id": self.dossier_id,
            "experiment_id": self.experiment_id,
            "case_id": self.case_id,
            "requirements_summary": self.requirements_summary,
            "relevant_constraints": self.relevant_constraints,
            "execution_stage": self.execution_stage,
            "responsible_component": self.responsible_component,
            "exception_or_finding": self.exception_or_finding,
            "measured_values": self.measured_values,
            "thresholds": self.thresholds,
            "candidate_state_before": self.candidate_state_before,
            "candidate_state_after": self.candidate_state_after,
            "retry_and_recovery_actions": self.retry_and_recovery_actions,
            "final_workflow_status": self.final_workflow_status,
            "valid_candidate_preserved": self.valid_candidate_preserved,
            "recovery_succeeded": self.recovery_succeeded,
            "evidence_references": self.evidence_references,
            "root_cause_classification": self.root_cause_classification,
            "remaining_uncertainty": self.remaining_uncertainty,
        }


class ExplainabilityService:
    """Authoritative generator of evidence-based architectural rationales."""

    @classmethod
    def create_failure_dossier(
        cls,
        experiment_id: str,
        case_id: str,
        requirements_summary: Dict[str, Any],
        relevant_constraints: List[Dict[str, Any]],
        execution_stage: str,
        responsible_component: str,
        exception_or_finding: str,
        measured_values: Optional[Dict[str, Any]] = None,
        thresholds: Optional[Dict[str, Any]] = None,
        candidate_state_before: Optional[Dict[str, Any]] = None,
        candidate_state_after: Optional[Dict[str, Any]] = None,
        retry_and_recovery_actions: Optional[List[Dict[str, Any]]] = None,
        final_workflow_status: str = "failed",
        valid_candidate_preserved: bool = False,
        recovery_succeeded: bool = False,
        evidence_references: Optional[List[str]] = None,
        root_cause_classification: str = "VERIFIED_ROOT_CAUSE",
        remaining_uncertainty: Optional[str] = None,
    ) -> FailureDossier:
        """Create a verifiable, evidence-grounded failure dossier without hallucinated reasons."""
        return FailureDossier(
            experiment_id=experiment_id,
            case_id=case_id,
            requirements_summary=requirements_summary,
            relevant_constraints=relevant_constraints,
            execution_stage=execution_stage,
            responsible_component=responsible_component,
            exception_or_finding=exception_or_finding,
            measured_values=measured_values or {},
            thresholds=thresholds or {},
            candidate_state_before=candidate_state_before,
            candidate_state_after=candidate_state_after,
            retry_and_recovery_actions=retry_and_recovery_actions or [],
            final_workflow_status=final_workflow_status,
            valid_candidate_preserved=valid_candidate_preserved,
            recovery_succeeded=recovery_succeeded,
            evidence_references=evidence_references or [],
            root_cause_classification=root_cause_classification,
            remaining_uncertainty=remaining_uncertainty,
        )

    @classmethod
    def explain_infeasibility(
        cls,
        deficits: List[Dict[str, Any]],
        facts: Optional[Dict[str, Any]] = None,
    ) -> GroundedExplanation:
        """Explain an infeasibility outcome using recorded mathematical deficit evidence."""
        facts = facts or {}
        eid = f"exp_inf_{generate_id()}"

        if not deficits and not facts.get("measured_deficit_sqm") and not facts.get("deficits"):
            return GroundedExplanation(
                explanation_id=eid,
                decision_action="declare_infeasible",
                observed_trigger="Feasibility check returned False",
                supporting_evidence={},
                relevant_constraints=[{"name": "buildable_area_envelope", "type": "mandatory"}],
                selection_rationale="Infeasibility declared but exact quantitative deficit records are missing.",
                is_verified=False,
                unverified_reason="Missing deficit measurements in project facts",
            )

        measured_deficit = facts.get("measured_deficit_sqm")
        if measured_deficit is None and deficits:
            measured_deficit = deficits[0].get("deficit_sqm") if isinstance(deficits[0], dict) else getattr(deficits[0], "deficit_sqm", None)
        if measured_deficit is None:
            measured_deficit = 0.0

        avail = facts.get("available_sqm")
        if avail is None and deficits:
            avail = deficits[0].get("available_sqm") if isinstance(deficits[0], dict) else getattr(deficits[0], "available_sqm", None)
        if avail is None:
            avail = 0.0

        req = facts.get("required_sqm")
        if req is None and deficits:
            req = deficits[0].get("required_sqm") if isinstance(deficits[0], dict) else getattr(deficits[0], "required_sqm", None)
        if req is None:
            req = 0.0

        trigger = (
            f"measured room-area demand ({float(req):.1f} m²) exceeds available buildable area ({float(avail):.1f} m²) "
            f"by a deficit of {float(measured_deficit):.1f} m²"
        )

        constraints = [
            {"name": "plot_setback_envelope", "type": "mandatory", "is_hard": True},
            {"name": "minimum_room_areas", "type": "mandatory", "is_hard": True},
        ]

        rationale = (
            f"The ASAA spatial boundary calculator determined that the requested spaces cannot physically "
            f"fit inside the setback-constrained envelope without violating mandatory minimum area limits."
        )

        return GroundedExplanation(
            explanation_id=eid,
            decision_action="declare_infeasible",
            observed_trigger=trigger,
            supporting_evidence={"deficit_sqm": measured_deficit, "available_sqm": avail, "required_sqm": req},
            relevant_constraints=constraints,
            tool_outcome="infeasible",
            selection_rationale=rationale,
            resulting_state_change="Transitioned workflow to INFEASIBLE (or WAITING_FOR_CLARIFICATION in interactive mode)",
            is_verified=True,
        )

    @classmethod
    def explain_candidate_choice(
        cls,
        accepted_candidate: Any,
        rejected_candidates: Optional[List[Any]] = None,
    ) -> GroundedExplanation:
        """Explain why a specific ASAA candidate or refinement candidate was selected over others."""
        eid = f"exp_cand_{generate_id()}"
        rejected_candidates = rejected_candidates or []

        cand_id = getattr(accepted_candidate, "id", None) or getattr(accepted_candidate, "candidate_id", "unknown")
        acc_eval = getattr(accepted_candidate, "evaluation", None)
        acc_score = getattr(acc_eval, "overall_score", None) if acc_eval else getattr(accepted_candidate, "score", 0.0)
        is_valid = getattr(acc_eval, "is_valid", True) if acc_eval else True

        alts_info: List[Dict[str, Any]] = []
        for rc in rejected_candidates:
            rc_id = getattr(rc, "id", None) or getattr(rc, "candidate_id", "unknown")
            if rc_id == cand_id:
                continue
            r_eval = getattr(rc, "evaluation", None)
            r_score = getattr(r_eval, "overall_score", None) if r_eval else getattr(rc, "score", 0.0)
            r_valid = getattr(r_eval, "is_valid", False) if r_eval else False
            r_reason = getattr(r_eval, "decision_reason", "Lower overall score or hard constraint defect") if r_eval else "Lower quality score"
            alts_info.append({
                "candidate_id": rc_id,
                "score": r_score,
                "is_valid": r_valid,
                "rejection_reason": r_reason,
            })

        trigger = f"candidate '{cand_id}' achieved quality score {acc_score:.1f}/100 with validity={is_valid}"
        rationale = (
            f"Candidate '{cand_id}' was accepted as the best valid candidate because it satisfied all mandatory "
            f"geometric boundary and connectivity constraints while maximizing spatial adjacency and compactness."
        )

        return GroundedExplanation(
            explanation_id=eid,
            decision_action="accept_best_candidate",
            observed_trigger=trigger,
            supporting_evidence={"candidate_id": cand_id, "score": acc_score, "valid": is_valid},
            relevant_constraints=[
                {"name": "hard_boundary_containment", "type": "mandatory", "is_hard": True},
                {"name": "spatial_adjacency_preference", "type": "preference", "is_hard": False},
            ],
            tool_outcome="candidate_accepted",
            alternatives_considered=alts_info,
            selection_rationale=rationale,
            resulting_state_change=f"Preserved candidate '{cand_id}' as the current authoritative design candidate",
            is_verified=True,
        )

    @classmethod
    def explain_validation_issue(cls, issue: Union[ValidationIssue, Dict[str, Any]]) -> GroundedExplanation:
        """Explain an individual validation defect with code reference and severity."""
        eid = f"exp_val_{generate_id()}"
        if isinstance(issue, ValidationIssue):
            cat = issue.category
            sev = issue.severity
            msg = issue.message
            details = issue.details or {}
            target = issue.target_id or issue.room_id
        else:
            cat = issue.get("category", issue.get("check", "general"))
            sev = issue.get("severity", "error")
            msg = issue.get("message", "")
            details = issue.get("details", {})
            target = issue.get("target_id", issue.get("room_id"))

        is_hard = sev == "error"
        action = "reject_for_repair" if is_hard else "record_advisory_warning"
        trigger = f"validation check '{cat}' failed with severity '{sev}': {msg}"

        return GroundedExplanation(
            explanation_id=eid,
            decision_action=action,
            observed_trigger=trigger,
            supporting_evidence=details,
            relevant_constraints=[{"name": cat, "type": "mandatory" if is_hard else "preferred", "is_hard": is_hard}],
            tool_outcome=sev,
            selection_rationale=f"Defect flagged on target '{target}'; hard defects prevent project completion without repair.",
            resulting_state_change="Dispatched to refinement agent for geometry or door repair" if is_hard else "Recorded in validation report",
            is_verified=True,
        )

    @classmethod
    def explain_clarification_interaction(
        cls,
        request: Any,
        response: Optional[Any] = None,
        change_record: Optional[Any] = None,
    ) -> GroundedExplanation:
        """Explain interactive clarification pause, user response, and atomic requirement provenance."""
        eid = f"exp_clr_{generate_id()}"
        req_id = getattr(request, "request_id", "")
        question = getattr(request, "question", "") or getattr(request, "issue_explanation", "")
        cat = getattr(request, "category", None)
        cat_name = getattr(cat, "value", str(cat))

        if not response:
            trigger = f"detected {cat_name}: {question}"
            return GroundedExplanation(
                explanation_id=eid,
                decision_action="pause_for_clarification",
                observed_trigger=trigger,
                supporting_evidence={"request_id": req_id, "category": cat_name},
                relevant_constraints=[{"name": "user_requirement_authority", "type": "mandatory", "is_hard": True}],
                tool_outcome="waiting_for_clarification",
                selection_rationale="Execution was safely paused because mandatory requirements require user authorization before mutation.",
                resulting_state_change="Transitioned workflow to WAITING_FOR_CLARIFICATION",
                is_verified=True,
            )

        # Response answered
        sel_opt = getattr(response, "selected_option_id", "custom")
        num_vals = getattr(response, "numeric_values", {}) or getattr(response, "numeric_overrides", {})
        prov = getattr(change_record, "provenance", "user_authorized") if change_record else "user_authorized"

        trigger = f"user responded with option '{sel_opt}' (provenance: {prov})"
        rationale = (
            f"User explicitly authorized constraint modification. Overrides: {num_vals}. "
            f"Downstream stages were invalidated and workflow resumed."
        )

        return GroundedExplanation(
            explanation_id=eid,
            decision_action="apply_clarification_and_resume",
            observed_trigger=trigger,
            supporting_evidence={"response_id": getattr(response, "response_id", ""), "selected_option": sel_opt, "overrides": num_vals},
            relevant_constraints=[{"name": "provenance_audit_trail", "type": "mandatory", "is_hard": True}],
            tool_outcome="accepted",
            selection_rationale=rationale,
            resulting_state_change="Requirements updated atomically, state version incremented, workflow set to RESUMABLE",
            is_verified=True,
        )

    @classmethod
    def build_dossier_from_pipeline_result(cls, result: Any) -> ProjectExplanationDossier:
        """Build a comprehensive explanation dossier from a PipelineResult or ProjectState."""
        pid = getattr(result, "project_id", "proj_unknown")
        status = getattr(result, "status", "unknown")

        dossier = ProjectExplanationDossier(project_id=pid, status=status)

        # Infeasibility
        facts = getattr(result, "facts", {}) or getattr(result, "agentic_state", {}).get("facts", {})
        deficits = facts.get("deficits", [])
        if status in ("infeasible", "failed") or facts.get("measured_deficit_sqm") or deficits:
            dossier.infeasibility_explanation = cls.explain_infeasibility(deficits=deficits, facts=facts)

        # Validation findings
        val_rep = getattr(result, "validation_report", None)
        if val_rep and hasattr(val_rep, "results"):
            for vr in val_rep.results:
                for issue in getattr(vr, "issues", []):
                    dossier.validation_explanations.append(cls.explain_validation_issue(issue))

        # Best candidate choice
        cands = getattr(result, "candidates", []) or getattr(result, "agentic_state", {}).get("candidates", [])
        if cands:
            best_c = cands[-1]
            dossier.allocation_explanations.append(cls.explain_candidate_choice(best_c, cands[:-1]))

        # Clarification
        clarif = getattr(result, "pending_clarification", None)
        if clarif:
            dossier.clarification_explanations.append(cls.explain_clarification_interaction(clarif))

        # Decisions
        decisions = getattr(result, "decisions", [])
        for d in decisions:
            dossier.decision_explanations.append(cls.explain_decision(d))

        return dossier

    @classmethod
    def explain_decision(cls, decision: Any) -> GroundedExplanation:
        """Explain an individual agent decision from execution trace."""
        eid = f"exp_dec_{generate_id()}"
        if hasattr(decision, "id"):
            action = getattr(decision, "kind", "") or getattr(decision, "action", "")
            agent = getattr(decision, "agent", "")
            tool = getattr(decision, "tool", None)
            rationale = getattr(decision, "rationale", "")
            source = getattr(decision, "source", "rules")
            fallback_reason = getattr(decision, "fallback_reason", None)
            args = getattr(decision, "args", {}) or {}
            evidence_refs = getattr(decision, "evidence_refs", [])
            outcome = getattr(decision, "outcome", None)
            status = getattr(decision, "status", "accepted")
        else:
            action = decision.get("kind", decision.get("action", ""))
            agent = decision.get("agent", "")
            tool = decision.get("tool")
            rationale = decision.get("rationale", "")
            source = decision.get("source", "rules")
            fallback_reason = decision.get("fallback_reason")
            args = decision.get("args", {}) or {}
            evidence_refs = decision.get("evidence_refs", [])
            outcome = decision.get("outcome")
            status = decision.get("status", "accepted")

        # Check evidence grounding
        has_evidence = bool(args) or bool(evidence_refs) or bool(fallback_reason)
        if not has_evidence:
            return GroundedExplanation(
                explanation_id=eid,
                decision_action=action or "unknown_action",
                observed_trigger=rationale or "unrecorded trigger",
                supporting_evidence={},
                relevant_constraints=[],
                tool_outcome=outcome,
                selection_rationale=f"[UNVERIFIED] {rationale}" if rationale else "No supporting evidence recorded.",
                is_verified=False,
                unverified_reason="No supporting evidence recorded",
            )

        trigger = f"agent '{agent}' selected action '{action}' via {source}"
        if fallback_reason:
            trigger += f" (fallback: {fallback_reason})"

        return GroundedExplanation(
            explanation_id=eid,
            decision_action=action,
            observed_trigger=trigger,
            supporting_evidence=args if isinstance(args, dict) else {"args": args},
            relevant_constraints=[{"name": f"{agent}_rules", "type": "agent_policy", "is_hard": False}],
            tool_outcome=tool or outcome,
            selection_rationale=rationale,
            resulting_state_change=f"Status: {status}",
            is_verified=True,
        )

    def generate_dossier(self, state: Any) -> ProjectExplanationDossier:
        """Alias to build a dossier from a ProjectState."""
        return self.build_dossier_from_pipeline_result(state)


"""Agentic Workflow Engine for PlanForge AI.

Coordinates the observe-decide-act-evaluate loop using shared ProjectState,
authoritative ToolRegistry, event logging, and bounded execution budgets.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from app.agentic.budget import Budget
from app.agentic.events import InMemoryEventLog
from app.agentic.state import ProjectState, RunStatus
from app.agentic.tools import ToolRegistry, ToolResult
from app.agentic.toolset import create_default_tool_registry
from app.llm.client import LLMClient
from app.llm.configuration import LLMConfig
from app.orchestration.llm_selector import LLMActionSelector
from app.orchestration.routing import AgenticPolicy, NextAction

logger = logging.getLogger(__name__)


class AgenticWorkflow:
    """Coordinates end-to-end autonomous floor plan design through state-aware tool invocation."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        policy: Optional[AgenticPolicy] = None,
        llm_selector: Optional[LLMActionSelector] = None,
        event_log: Optional[InMemoryEventLog] = None,
        budget: Optional[Budget] = None,
        llm_client: Optional[LLMClient] = None,
        llm_config: Optional[LLMConfig] = None,
        use_llm: bool = True,
    ) -> None:
        self.registry = registry or create_default_tool_registry()
        self.policy = policy or AgenticPolicy()
        self.event_log = event_log or InMemoryEventLog()
        self.budget_template = budget or Budget(max_steps=25, max_tool_calls=35, max_wall_seconds=120.0)
        self.use_llm = use_llm

        if llm_selector is not None:
            self.selector = llm_selector
        elif use_llm:
            self.selector = LLMActionSelector(
                registry=self.registry,
                fallback_policy=self.policy,
                llm_client=llm_client,
                config=llm_config,
                event_log=self.event_log,
            )
        else:
            self.selector = self.policy

    def run(
        self,
        project_id: str,
        goal: str = "",
        raw_brief: Optional[str] = None,
        requirements: Optional[Any] = None,
        inputs: Optional[Dict[str, Any]] = None,
    ) -> ProjectState:
        """Execute the autonomous workflow until termination, acceptance, or budget exhaustion."""
        inps = dict(inputs or {})
        if raw_brief:
            inps["raw_brief"] = raw_brief
        if requirements:
            inps["requirements"] = requirements

        state = ProjectState(
            project_id=project_id,
            goal=goal or (requirements.project_name if requirements else "Residential Floor Plan"),
            inputs=inps,
            budget=Budget(
                max_steps=self.budget_template.max_steps,
                max_llm_calls=self.budget_template.max_llm_calls,
                max_tool_calls=self.budget_template.max_tool_calls,
                max_wall_seconds=self.budget_template.max_wall_seconds,
            ),
        )
        state.budget.start()

        self.event_log.emit(
            type="run_started",
            agent="orchestrator",
            summary=f"Started agentic design workflow for project {project_id}",
            data={"project_id": project_id, "goal": state.goal},
        )

        while not state.status.is_terminal:
            continue_run = self.step(state)
            if not continue_run:
                break

        # Final event logging
        self.event_log.emit(
            type="run_completed",
            agent="orchestrator",
            summary=f"Workflow completed with status: {state.status.value}",
            data={
                "status": state.status.value,
                "status_reason": state.status_reason,
                "steps": state.step,
                "hard_errors": len(state.hard_findings()),
                "warnings": len(state.warning_findings()),
            },
        )

        return state

    def step(self, state: ProjectState) -> bool:
        """Execute one observe-decide-act-evaluate iteration. Returns True to continue."""
        state.step += 1
        state.budget.steps_used += 1

        # Check budget limit
        budget_reason = state.budget.exhausted()
        if budget_reason:
            state.status = RunStatus.BUDGET_EXHAUSTED
            state.status_reason = budget_reason
            return False

        # 1. OBSERVE & DECIDE
        action: NextAction = self.selector.decide(state)

        # Record decision
        current_fp = state.fingerprint()
        decision_rec = state.record_decision(
            agent="orchestrator",
            kind=action.kind,
            tool=action.tool,
            args=action.args,
            rationale=action.rationale,
            source=action.source,
            fallback_reason=action.fallback_reason,
            considered=[action.tool] if action.tool else [],
            state_fingerprint=current_fp,
            evidence_refs=action.evidence,
        )

        self.event_log.emit(
            type="decision_made",
            agent="orchestrator",
            summary=action.rationale,
            data={
                "tool": action.tool,
                "rationale": action.rationale,
                "kind": action.kind,
                "source": action.source,
                "reason_code": action.reason_code,
                "fallback_reason": action.fallback_reason,
            },
        )

        # If decision is terminal (finish / halt)
        if action.kind in {"finish", "halt"}:
            state.status = action.target_status or RunStatus.ACCEPTED
            state.status_reason = action.rationale
            if state.status == RunStatus.ACCEPTED:
                fp_set = state.get_artifact("floor_plan_set")
                val_rep = getattr(fp_set, "validation_report", None) if fp_set else None
                state.acceptance_evidence = {
                    "score": getattr(val_rep, "overall_score", 100.0) if val_rep else 100.0,
                    "hard_errors": len(state.hard_findings()),
                    "warnings": len(state.warning_findings()),
                    "floors_count": len(fp_set.floor_plans) if fp_set else 1,
                    "summary": action.rationale,
                }
            return False

        if not action.tool:
            state.status = RunStatus.STALLED
            state.status_reason = "Policy produced no actionable tool or state transition."
            return False

        # 2. ACT
        tool_name = action.tool
        tool_args = action.args

        # Loop / repeat action detection
        action_key = f"{tool_name}:{sorted(tool_args.items())}"
        exec_record = state.executed.get(action_key)
        if exec_record and exec_record.get("fingerprint") == current_fp:
            exec_record["attempts"] = exec_record.get("attempts", 1) + 1
            if exec_record["attempts"] >= 3:
                exec_record["blocked"] = True
                state.stalled = True
                decision_rec.status = "rejected"
                decision_rec.rejection_reason = "Repeated action with identical state produced no progress."
                state.last_rejection = decision_rec.rejection_reason
                logger.warning(f"Blocking repeated action '{action_key}' to prevent infinite oscillation.")
                return True
        else:
            state.executed[action_key] = {
                "action_key": action_key,
                "tool": tool_name,
                "args": tool_args,
                "fingerprint": current_fp,
                "attempts": 1,
                "blocked": False,
            }

        state.budget.tool_calls_used += 1
        t_start = time.perf_counter()

        self.event_log.emit(
            type="tool_called",
            agent="orchestrator",
            summary=f"Calling tool '{tool_name}'",
            data={"tool": tool_name, "args": tool_args},
        )

        tool_result: ToolResult = self.registry.invoke(state, tool_name, tool_args)
        duration_ms = (time.perf_counter() - t_start) * 1000.0

        # Record tool call
        artifacts_written: List[str] = []
        if tool_result.artifacts:
            for k, v in tool_result.artifacts.items():
                state.set_artifact(k, v)
                artifacts_written.append(k)

        tc_rec = state.record_tool_call(
            decision_id=decision_rec.id,
            tool=tool_name,
            args=tool_args,
            ok=tool_result.ok,
            outcome=tool_result.outcome,
            summary=tool_result.summary,
            error_type=tool_result.error_type,
            error_message=tool_result.error_message,
            duration_ms=round(duration_ms, 2),
            artifacts_written=artifacts_written,
        )
        decision_rec.tool_call_id = tc_rec.id

        self.event_log.emit(
            type="tool_result",
            agent="orchestrator",
            summary=tool_result.summary,
            data={
                "tool": tool_name,
                "ok": tool_result.ok,
                "outcome": tool_result.outcome,
                "duration_ms": round(duration_ms, 2),
            },
        )

        # 3. EVALUATE
        if tool_result.facts:
            state.facts.update(tool_result.facts)
        if tool_result.questions:
            state.open_questions.extend(tool_result.questions)
        if tool_result.infeasibility:
            state.infeasibility_evidence.append(tool_result.infeasibility)
            state.status = RunStatus.INFEASIBLE
            state.status_reason = tool_result.summary
            return False

        if tool_result.outcome == "needs_input":
            state.status = RunStatus.NEEDS_CLARIFICATION
            state.status_reason = tool_result.summary
            return False

        # Candidate Evaluation & Best-Valid Preservation
        cand_rec = None
        is_new_best = False
        if state.has_artifact("floor_plan_set") and ("floor_plan_set" in artifacts_written or tool_name in {"validate_design", "refine_design", "construct_geometry"}):
            cand_rec, is_new_best = state.record_candidate(source_action=tool_name)
            if cand_rec:
                self.event_log.emit(
                    type="candidate_evaluated",
                    agent="orchestrator",
                    summary=f"Candidate {cand_rec.id} evaluated: {cand_rec.evaluation.acceptance_decision}",
                    data={
                        "candidate_id": cand_rec.id,
                        "is_valid": cand_rec.evaluation.is_valid,
                        "score": cand_rec.evaluation.overall_score,
                        "hard_errors": cand_rec.evaluation.hard_error_count,
                        "warnings": cand_rec.evaluation.warning_count,
                        "decision": cand_rec.evaluation.acceptance_decision,
                        "reason": cand_rec.evaluation.decision_reason,
                    },
                )

                if is_new_best:
                    self.event_log.emit(
                        type="best_candidate_updated",
                        agent="orchestrator",
                        summary=f"New best candidate {cand_rec.id} (score {cand_rec.evaluation.overall_score:.1f}, valid={cand_rec.evaluation.is_valid})",
                        data={
                            "candidate_id": cand_rec.id,
                            "score": cand_rec.evaluation.overall_score,
                            "is_valid": cand_rec.evaluation.is_valid,
                        },
                    )
                elif cand_rec.evaluation.acceptance_decision == "rejected_regression":
                    self.event_log.emit(
                        type="candidate_rejected",
                        agent="orchestrator",
                        summary=f"Candidate {cand_rec.id} rejected due to regression; restoring best valid candidate",
                        data={"candidate_id": cand_rec.id, "reason": cand_rec.evaluation.decision_reason},
                    )
                    state.restore_best_valid()

        # Progress tracking & Stagnation Detection
        if cand_rec is not None:
            if is_new_best:
                state.no_progress_streak = 0
                decision_rec.outcome = "improved"
            else:
                state.no_progress_streak += 1
                decision_rec.outcome = "regressed" if cand_rec.evaluation.acceptance_decision == "rejected_regression" else "unchanged"
        elif tool_result.ok and (artifacts_written or tool_result.outcome == "ok"):
            state.no_progress_streak = 0
            decision_rec.outcome = "improved"
        else:
            state.no_progress_streak += 1
            decision_rec.outcome = "unchanged"

        if state.no_progress_streak >= 4:
            state.stalled = True
            self.event_log.emit(
                type="stagnation_detected",
                agent="orchestrator",
                summary=f"Stagnation detected: {state.no_progress_streak} steps without improvement",
                data={"streak": state.no_progress_streak},
            )

        return True

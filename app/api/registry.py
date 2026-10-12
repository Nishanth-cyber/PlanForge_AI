"""Process-local in-memory project registry storing generated project results and interactive states."""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple

from app.agentic.clarification import ClarificationRequest, ClarificationResponse
from app.agentic.state import ProjectState, RunStatus
from app.orchestration.config import OrchestrationConfig
from app.orchestration.pipeline import PipelineResult


class ProjectRegistry:
    """Thread-safe, process-local registry caching generated project results and active sessions.

    Limitation Note:
    Project results are process-local and are not persistent across server restarts.
    Physical export bundles saved in the filesystem (e.g. outputs/<project_id>/)
    remain persistent on disk.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._projects: Dict[str, PipelineResult] = {}
        self._states: Dict[str, ProjectState] = {}
        self._orchestrators: Dict[str, Any] = {}
        self._configs: Dict[str, OrchestrationConfig] = {}

    def save_result(
        self,
        result: PipelineResult,
        state: Optional[ProjectState] = None,
        orchestrator: Optional[Any] = None,
        config: Optional[OrchestrationConfig] = None,
    ) -> None:
        """Store a pipeline result and optional session state by its project_id."""
        with self._lock:
            self._projects[result.project_id] = result
            if state is not None:
                self._states[result.project_id] = state
            if orchestrator is not None:
                self._orchestrators[result.project_id] = orchestrator
            if config is not None:
                self._configs[result.project_id] = config

    def save_session(
        self,
        project_id: str,
        state: ProjectState,
        orchestrator: Any,
        config: Optional[OrchestrationConfig] = None,
        result: Optional[PipelineResult] = None,
    ) -> None:
        """Store active interactive session components."""
        with self._lock:
            self._states[project_id] = state
            self._orchestrators[project_id] = orchestrator
            if config is not None:
                self._configs[project_id] = config
            if result is not None:
                self._projects[project_id] = result

    def get_result(self, project_id: str) -> Optional[PipelineResult]:
        """Retrieve a stored pipeline result by its project_id."""
        with self._lock:
            return self._projects.get(project_id)

    def get_state(self, project_id: str) -> Optional[ProjectState]:
        """Retrieve active ProjectState if present."""
        with self._lock:
            return self._states.get(project_id)

    def get_orchestrator(self, project_id: str) -> Optional[Any]:
        """Retrieve active orchestrator if present."""
        with self._lock:
            return self._orchestrators.get(project_id)

    def get_config(self, project_id: str) -> Optional[OrchestrationConfig]:
        """Retrieve active configuration if present."""
        with self._lock:
            return self._configs.get(project_id)

    def list_projects(self) -> List[str]:
        """Return a list of all stored project IDs."""
        with self._lock:
            return list(self._projects.keys())

    def delete_project(self, project_id: str) -> bool:
        """Remove a stored project result and session by its project_id."""
        with self._lock:
            self._states.pop(project_id, None)
            self._orchestrators.pop(project_id, None)
            self._configs.pop(project_id, None)
            return self._projects.pop(project_id, None) is not None

    def clear(self) -> None:
        """Clear all stored project results (useful for test isolation)."""
        with self._lock:
            self._projects.clear()
            self._states.clear()
            self._orchestrators.clear()
            self._configs.clear()

    def get_pending_clarification(self, project_id: str) -> Optional[ClarificationRequest]:
        """Get currently pending clarification request for project if any."""
        with self._lock:
            state = self._states.get(project_id)
            if state and state.pending_clarification:
                return state.pending_clarification
            res = self._projects.get(project_id)
            if res and res.agentic_state:
                pending_dict = res.agentic_state.get("pending_clarification")
                if pending_dict:
                    return ClarificationRequest.from_dict(pending_dict)
            return None

    def get_clarifications(self, project_id: str) -> Dict[str, Any]:
        """Retrieve complete clarification summary for a project."""
        with self._lock:
            state = self._states.get(project_id)
            if state:
                return {
                    "project_id": project_id,
                    "status": state.status.value,
                    "pending_clarification": state.pending_clarification.to_dict() if state.pending_clarification else None,
                    "clarification_history": [c.to_dict() for c in state.clarification_history],
                    "requirement_changes": [rc.to_dict() for rc in state.requirement_changes],
                    "state_version": state.version,
                }
            res = self._projects.get(project_id)
            if res and res.agentic_state:
                ag = res.agentic_state
                return {
                    "project_id": project_id,
                    "status": ag.get("run_status", res.status),
                    "pending_clarification": ag.get("pending_clarification"),
                    "clarification_history": ag.get("clarification_history", []),
                    "requirement_changes": ag.get("requirement_changes", []),
                    "state_version": ag.get("version", 0),
                }
            return {
                "project_id": project_id,
                "status": "not_found",
                "pending_clarification": None,
                "clarification_history": [],
                "requirement_changes": [],
                "state_version": 0,
            }

    def submit_clarification_response(
        self,
        project_id: str,
        request_id: str,
        selected_option_id: Optional[str] = None,
        user_response_text: Optional[str] = None,
        numeric_overrides: Optional[Dict[str, float]] = None,
        expected_state_version: Optional[int] = None,
    ) -> Tuple[bool, str, Optional[ClarificationResponse], Optional[ProjectState]]:
        """Submit a user response to a pending clarification request."""
        with self._lock:
            state = self._states.get(project_id)
            if not state:
                return False, f"Project '{project_id}' not found in active session registry.", None, None

            orchestrator = self._orchestrators.get(project_id)
            if not orchestrator:
                from app.agentic.tools import create_standard_tool_registry
                from app.orchestration.hierarchical import HierarchicalOrchestrator
                orchestrator = HierarchicalOrchestrator(registry=create_standard_tool_registry(), interactive=True)
                self._orchestrators[project_id] = orchestrator

            success, msg, response = orchestrator.apply_clarification_response(
                state=state,
                request_id=request_id,
                selected_option_id=selected_option_id,
                user_response_text=user_response_text,
                numeric_overrides=numeric_overrides,
                expected_state_version=expected_state_version,
            )

            cfg = self._configs.get(project_id) or OrchestrationConfig()
            from app.orchestration.orchestrator import PlanForgeOrchestrator
            orch_pipeline = PlanForgeOrchestrator()
            res = orch_pipeline._create_result_from_agentic_state(
                project_state=state,
                project_id=project_id,
                project_name=state.goal or project_id,
                cfg=cfg,
                event_log=getattr(orchestrator, "event_log", None),
            )
            self._projects[project_id] = res
            return success, msg, response, state

    def resume_project(self, project_id: str) -> Tuple[bool, str, Optional[PipelineResult]]:
        """Resume execution of a paused/resumable project."""
        with self._lock:
            state = self._states.get(project_id)
            if not state:
                return False, f"Project '{project_id}' has no active resumable session.", None
            orchestrator = self._orchestrators.get(project_id)
            if not orchestrator:
                return False, f"Project '{project_id}' has no active orchestrator.", None
            cfg = self._configs.get(project_id) or OrchestrationConfig()

            success, msg, resumed_state = orchestrator.resume(state)
            from app.orchestration.orchestrator import PlanForgeOrchestrator
            orch_pipeline = PlanForgeOrchestrator()
            res = orch_pipeline._create_result_from_agentic_state(
                project_state=resumed_state,
                project_id=project_id,
                project_name=resumed_state.goal or project_id,
                cfg=cfg,
                event_log=getattr(orchestrator, "event_log", None),
            )
            self._projects[project_id] = res
            return success, msg, res

    def cancel_project(
        self,
        project_id: str,
        reason: str = "User cancelled generation",
    ) -> Tuple[bool, str, Optional[PipelineResult]]:
        """Cancel an active or paused project generation session."""
        with self._lock:
            state = self._states.get(project_id)
            if not state:
                res = self._projects.get(project_id)
                if res:
                    res.status = "cancelled"
                    res.error_message = reason
                    return True, "Project cancelled", res
                return False, f"Project '{project_id}' not found.", None

            orchestrator = self._orchestrators.get(project_id)
            if orchestrator:
                orchestrator.cancel(state, reason=reason)
            else:
                state.status = RunStatus.CANCELLED
                state.status_reason = reason

            cfg = self._configs.get(project_id) or OrchestrationConfig()
            from app.orchestration.orchestrator import PlanForgeOrchestrator
            orch_pipeline = PlanForgeOrchestrator()
            res = orch_pipeline._create_result_from_agentic_state(
                project_state=state,
                project_id=project_id,
                project_name=state.goal or project_id,
                cfg=cfg,
            )
            self._projects[project_id] = res
            return True, "Project generation cancelled.", res

    @property
    def editing_agent(self):
        """Lazy-loaded DesignEditingAgent instance."""
        if not hasattr(self, "_editing_agent") or self._editing_agent is None:
            from app.agents.editing_agent.agent import DesignEditingAgent
            self._editing_agent = DesignEditingAgent()
        return self._editing_agent

    def edit_project(
        self,
        project_id: str,
        instruction: str,
        floor_number: Optional[int] = None,
        alternative_index: int = 1,
    ):
        """Execute a natural language design edit on an existing project."""
        with self._lock:
            res = self.get_result(project_id)
            if not res:
                return None
            return self.editing_agent.edit_design(
                project_result=res,
                instruction=instruction,
                floor_number=floor_number,
                alternative_index=alternative_index,
            )

    def undo_project(self, project_id: str):
        """Undo last accepted design edit and restore previous version."""
        with self._lock:
            res = self.get_result(project_id)
            if not res:
                return None
            return self.editing_agent.undo_design(project_result=res)

    def get_project_versions(self, project_id: str) -> List[Dict[str, Any]]:
        """Retrieve version history summaries for a project."""
        with self._lock:
            return self.editing_agent.get_history(project_id).list_summaries()


# Global default registry instance for API dependency injection
_DEFAULT_REGISTRY = ProjectRegistry()
project_registry = _DEFAULT_REGISTRY


def get_default_registry() -> ProjectRegistry:
    """Return the global default project registry instance."""
    return _DEFAULT_REGISTRY


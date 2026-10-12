"""Tool registry for the agentic workflow.

A *tool* is the only way an agent can affect the project. Every tool declares:

* ``input_schema``  - validated before the handler runs
* ``output_schema`` - documentation of the keys placed in ``ToolResult.data``
* ``reads``/``writes`` - artifact keys it needs / may produce. A tool that returns an artifact it did not
  declare in ``writes`` is rejected, so protected objects (e.g. authoritative geometry) can only be produced
  by the tool that owns them.
* ``side_effects`` - human-readable list, shown to policies and in documentation

Handlers receive the state read-only by convention and return a ``ToolResult``; only the workflow applies
results to the state. Exceptions never escape ``ToolRegistry.invoke``; they become failed results.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.agentic.schema import validate_args
from app.agentic.state import ProjectState
from app.agentic.util import to_jsonable

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class ToolTimeoutError(Exception):
    retryable = False


@dataclass
class ToolResult:
    ok: bool = True
    outcome: str = "ok"  # ok | infeasible | needs_input | no_effect | error
    summary: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    findings: Optional[List[Any]] = None  # None = not a validation; [] = validated and clean
    facts: Dict[str, Any] = field(default_factory=dict)
    strategy: Optional[Dict[str, Any]] = None
    questions: List[str] = field(default_factory=list)
    infeasibility: Optional[Dict[str, Any]] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    retryable: bool = False

    @classmethod
    def failure(
        cls, error_type: str, message: str, *, retryable: bool = False, outcome: str = "error"
    ) -> "ToolResult":
        return cls(
            ok=False,
            outcome=outcome,
            summary=f"{error_type}: {message}"[:300],
            error_type=error_type,
            error_message=str(message)[:500],
            retryable=retryable,
        )


@dataclass
class ToolSpec:
    name: str
    description: str
    handler: Callable[[ProjectState, Dict[str, Any]], ToolResult]
    input_schema: Dict[str, Any] = field(default_factory=lambda: {"type": "object", "additionalProperties": False})
    output_schema: Dict[str, Any] = field(default_factory=dict)
    side_effects: Tuple[str, ...] = ()
    reads: Tuple[str, ...] = ()
    writes: Tuple[str, ...] = ()
    validates: Tuple[str, ...] = ()  # artifact keys whose validity this tool's findings describe
    agent: str = "orchestrator"
    max_calls: Optional[int] = None
    timeout_seconds: Optional[float] = None
    precondition: Optional[Callable[[ProjectState], List[str]]] = None

    def missing_preconditions(self, state: ProjectState) -> List[str]:
        missing = [f"artifact '{k}' is not available" for k in self.reads if not state.has_artifact(k)]
        if self.precondition is not None:
            missing.extend(self.precondition(state))
        if self.max_calls is not None and state.tool_call_count(self.name) >= self.max_calls:
            missing.append(f"call limit reached ({self.max_calls})")
        return missing


def _is_retryable(exc: BaseException) -> bool:
    flag = getattr(exc, "retryable", None)
    if isinstance(flag, bool):
        return flag
    name = type(exc).__name__
    return isinstance(exc, (TimeoutError, ConnectionError)) or "Timeout" in name or "Connection" in name


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolSpec:
        if not _NAME_RE.match(spec.name):
            raise ValueError(f"Invalid tool name '{spec.name}' (use lowercase letters, digits, underscores)")
        if spec.name in self._tools:
            raise ValueError(f"Tool '{spec.name}' is already registered")
        self._tools[spec.name] = spec
        return spec

    def names(self) -> List[str]:
        return sorted(self._tools)

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def legal(self, state: ProjectState) -> List[ToolSpec]:
        return [s for s in self._tools.values() if not s.missing_preconditions(state)]

    def describe(self, state: ProjectState, only_legal: bool = False) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for spec in self._tools.values():
            blockers = spec.missing_preconditions(state)
            if only_legal and blockers:
                continue
            out.append(
                {
                    "name": spec.name,
                    "agent": spec.agent,
                    "description": spec.description,
                    "input_schema": spec.input_schema,
                    "output_keys": sorted(spec.output_schema.get("properties", {})),
                    "side_effects": list(spec.side_effects),
                    "reads": list(spec.reads),
                    "writes": list(spec.writes),
                    "legal": not blockers,
                    "blockers": blockers,
                }
            )
        return out

    def check_call(self, state: ProjectState, name: str, args: Dict[str, Any]) -> Optional[str]:
        """Return a reason the call cannot be made, or ``None`` if it is legal and well-formed."""
        spec = self._tools.get(name)
        if spec is None:
            return f"unknown tool '{name}'"
        errors = validate_args(spec.input_schema, args)
        if errors:
            return "invalid arguments: " + "; ".join(errors)
        blockers = spec.missing_preconditions(state)
        if blockers:
            return "preconditions not met: " + "; ".join(blockers)
        return None

    def invoke(self, state: ProjectState, name: str, args: Dict[str, Any]) -> ToolResult:
        """Run a tool. Never raises; every failure is returned as ``ToolResult(ok=False)``."""
        problem = self.check_call(state, name, args)
        if problem is not None:
            kind = "UnknownTool" if problem.startswith("unknown") else (
                "InvalidArguments" if problem.startswith("invalid") else "PreconditionFailed"
            )
            return ToolResult.failure(kind, problem)
        spec = self._tools[name]
        try:
            result = self._run(spec, state, args)
        except BaseException as exc:  # noqa: BLE001 - tool failures must become observations
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            return ToolResult.failure(type(exc).__name__, str(exc), retryable=_is_retryable(exc))
        if not isinstance(result, ToolResult):
            return ToolResult.failure("InvalidToolResult", f"tool '{name}' returned {type(result).__name__}")
        undeclared = sorted(set(result.artifacts) - set(spec.writes))
        if undeclared:
            return ToolResult.failure(
                "UndeclaredWrite", f"tool '{name}' attempted to write undeclared artifact(s): {undeclared}"
            )
        result.data = to_jsonable(result.data)
        return result

    @staticmethod
    def _run(spec: ToolSpec, state: ProjectState, args: Dict[str, Any]) -> ToolResult:
        if not spec.timeout_seconds:
            return spec.handler(state, args)
        box: Dict[str, Any] = {}

        def target() -> None:
            try:
                box["result"] = spec.handler(state, args)
            except BaseException as exc:  # noqa: BLE001
                box["exc"] = exc

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(spec.timeout_seconds)
        if thread.is_alive():
            raise ToolTimeoutError(f"tool '{spec.name}' exceeded {spec.timeout_seconds}s")
        if "exc" in box:
            raise box["exc"]
        return box["result"]

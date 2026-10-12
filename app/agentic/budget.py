"""Execution budget for an agentic run: steps, LLM calls, tool calls and wall-clock time."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class Budget:
    """Hard limits for one run. ``exhausted()`` returns a human-readable reason or ``None``."""

    max_steps: int = 25
    max_llm_calls: int = 20
    max_tool_calls: int = 40
    max_wall_seconds: float = 120.0
    steps_used: int = 0
    llm_calls_used: int = 0
    tool_calls_used: int = 0
    clock: Callable[[], float] = field(default=time.monotonic, repr=False, compare=False)
    _started: Optional[float] = field(default=None, repr=False, compare=False)

    def start(self) -> None:
        if self._started is None:
            self._started = self.clock()

    def elapsed(self) -> float:
        return 0.0 if self._started is None else max(0.0, self.clock() - self._started)

    def exhausted(self) -> Optional[str]:
        if self.steps_used >= self.max_steps:
            return f"step budget exhausted ({self.steps_used}/{self.max_steps})"
        if self.llm_calls_used >= self.max_llm_calls:
            return f"LLM-call budget exhausted ({self.llm_calls_used}/{self.max_llm_calls})"
        if self.tool_calls_used >= self.max_tool_calls:
            return f"tool-call budget exhausted ({self.tool_calls_used}/{self.max_tool_calls})"
        if self._started is not None and self.elapsed() >= self.max_wall_seconds:
            return f"time budget exhausted ({self.elapsed():.1f}s/{self.max_wall_seconds:.1f}s)"
        return None

    def remaining(self) -> Dict[str, Any]:
        return {
            "steps": max(0, self.max_steps - self.steps_used),
            "llm_calls": max(0, self.max_llm_calls - self.llm_calls_used),
            "tool_calls": max(0, self.max_tool_calls - self.tool_calls_used),
            "seconds": round(max(0.0, self.max_wall_seconds - self.elapsed()), 1),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_steps": self.max_steps,
            "max_llm_calls": self.max_llm_calls,
            "max_tool_calls": self.max_tool_calls,
            "max_wall_seconds": self.max_wall_seconds,
            "steps_used": self.steps_used,
            "llm_calls_used": self.llm_calls_used,
            "tool_calls_used": self.tool_calls_used,
            "elapsed_seconds": round(self.elapsed(), 3),
        }

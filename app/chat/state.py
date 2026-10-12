"""Backend-owned conversation state for the PlanForge chat.

Conversation state (stage, collected requirements, the last question asked, the pending
clarification, last action, generation status, artifacts) lives here -- on the server --
instead of being inferred only from the visible chat transcript.

* ``ConversationStateStore`` is thread-safe, bounded (LRU) and expiring (TTL).
* If a request carries no ``conversation_id`` the state is *transient* (stateless legacy
  behaviour): it is seeded from the request and never stored.
* ``begin_generation`` / ``finish_generation`` give the generation endpoint an atomic,
  server-side lock so repeated clicks cannot start duplicate runs, and give the chat real
  generation status to report.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.chat.schema import ConversationStage

GENERATION_IDLE = "idle"
GENERATION_RUNNING = "running"
GENERATION_COMPLETED = "completed"
GENERATION_FAILED = "failed"

#: A "running" flag older than this is treated as stale (crashed worker) and may be restarted.
GENERATION_STALE_SECONDS = 30 * 60


@dataclass
class ConversationState:
    """Structured, per-conversation project state."""

    conversation_id: str
    project_id: Optional[str] = None
    project_name: str = "PlanForge Residential Project"
    stage: ConversationStage = ConversationStage.DISCOVERY

    # Requirements ---------------------------------------------------------
    canonical_brief: str = ""                       # authoritative structured brief
    confirmed: Dict[str, str] = field(default_factory=dict)   # progress item -> value
    missing: List[str] = field(default_factory=list)          # progress items still needed
    last_summary: Optional[Dict[str, Any]] = None             # last requirements_summary dict

    # Dialogue -------------------------------------------------------------
    last_assistant_question: Optional[str] = None
    pending_field: Optional[str] = None             # field the last question asked for
    last_card_key: Optional[str] = None             # field_key of the last card actually shown
    last_intent: Optional[str] = None
    last_action: Optional[Dict[str, Any]] = None
    turn_count: int = 0

    # Generation / artifacts -----------------------------------------------
    generation_status: str = GENERATION_IDLE
    generation_started_at: Optional[float] = None
    generation_finished_at: Optional[float] = None
    generation_result: Optional[Dict[str, Any]] = None
    export_artifacts: List[str] = field(default_factory=list)
    design_stale: bool = False        # requirements changed after the last generated design

    updated_at: float = field(default_factory=time.time)

    # ------------------------------------------------------------------
    @property
    def has_requirements(self) -> bool:
        return bool(self.canonical_brief and self.canonical_brief.strip())

    @property
    def generation_running(self) -> bool:
        if self.generation_status != GENERATION_RUNNING:
            return False
        started = self.generation_started_at or 0.0
        return (time.time() - started) < GENERATION_STALE_SECONDS

    @property
    def has_generated_design(self) -> bool:
        return self.generation_status == GENERATION_COMPLETED and bool(self.project_id)

    def to_public_dict(self) -> Dict[str, Any]:
        """Serializable snapshot (no secrets) for diagnostics and tests."""
        return {
            "conversation_id": self.conversation_id,
            "project_id": self.project_id,
            "stage": self.stage.value,
            "confirmed": dict(self.confirmed),
            "missing": list(self.missing),
            "last_assistant_question": self.last_assistant_question,
            "pending_field": self.pending_field,
            "last_intent": self.last_intent,
            "last_action": self.last_action,
            "generation_status": self.generation_status,
            "export_artifacts": list(self.export_artifacts),
            "turn_count": self.turn_count,
        }


class ConversationStateStore:
    """Thread-safe, bounded, expiring in-memory store of ``ConversationState``."""

    def __init__(self, max_entries: int = 500, ttl_seconds: float = 6 * 3600) -> None:
        self._lock = threading.RLock()
        self._states: "OrderedDict[str, ConversationState]" = OrderedDict()
        self._max = max(1, max_entries)
        self._ttl = ttl_seconds

    # ------------------------------------------------------------------
    @staticmethod
    def new_id() -> str:
        return "conv_" + uuid.uuid4().hex[:12]

    def _evict(self) -> None:
        now = time.time()
        for cid in [c for c, s in self._states.items() if now - s.updated_at > self._ttl and not s.generation_running]:
            self._states.pop(cid, None)
        while len(self._states) > self._max:
            self._states.popitem(last=False)

    def get(self, conversation_id: Optional[str]) -> Optional[ConversationState]:
        if not conversation_id:
            return None
        with self._lock:
            state = self._states.get(conversation_id)
            if state is not None:
                self._states.move_to_end(conversation_id)
            return state

    def get_or_create(
        self,
        conversation_id: Optional[str],
        *,
        seed_brief: str = "",
        project_name: str = "PlanForge Residential Project",
        project_id: Optional[str] = None,
    ) -> ConversationState:
        """Return the stored state, or create one (transient when no id is supplied)."""
        if not conversation_id:
            return ConversationState(
                conversation_id="transient",
                project_id=project_id,
                project_name=project_name,
                canonical_brief=seed_brief or "",
            )
        with self._lock:
            state = self._states.get(conversation_id)
            if state is None:
                state = ConversationState(
                    conversation_id=conversation_id,
                    project_id=project_id,
                    project_name=project_name,
                    canonical_brief=seed_brief or "",   # restores state after a server restart
                )
                self._states[conversation_id] = state
                self._evict()
            else:
                self._states.move_to_end(conversation_id)
            return state

    def save(self, state: ConversationState) -> None:
        if state.conversation_id == "transient":
            return
        with self._lock:
            state.updated_at = time.time()
            self._states[state.conversation_id] = state
            self._states.move_to_end(state.conversation_id)
            self._evict()

    def delete(self, conversation_id: str) -> bool:
        with self._lock:
            return self._states.pop(conversation_id, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._states.clear()

    # ------------------------------------------------------------------
    # Generation lifecycle (atomic; used by the /generate endpoint)
    # ------------------------------------------------------------------
    def begin_generation(
        self, conversation_id: str, project_id: Optional[str] = None
    ) -> Tuple[bool, ConversationState]:
        """Atomically mark generation as running. Returns ``(False, state)`` if already running."""
        with self._lock:
            state = self._states.get(conversation_id)
            if state is None:
                state = ConversationState(conversation_id=conversation_id)
                self._states[conversation_id] = state
            if state.generation_running:
                return False, state
            state.generation_status = GENERATION_RUNNING
            state.generation_started_at = time.time()
            state.generation_finished_at = None
            state.generation_result = None
            if project_id:
                state.project_id = project_id
            state.stage = ConversationStage.GENERATING
            state.updated_at = time.time()
            return True, state

    def finish_generation(
        self,
        conversation_id: str,
        *,
        ok: bool,
        project_id: Optional[str] = None,
        status: str = "",
        valid: Optional[bool] = None,
        error: Optional[str] = None,
    ) -> Optional[ConversationState]:
        """Record the real outcome reported by the pipeline."""
        with self._lock:
            state = self._states.get(conversation_id)
            if state is None:
                return None
            state.generation_status = GENERATION_COMPLETED if ok else GENERATION_FAILED
            state.generation_finished_at = time.time()
            if project_id:
                state.project_id = project_id
            state.generation_result = {
                "status": status,
                "is_valid": valid,
                "error": error,
                "project_id": state.project_id,
            }
            if ok:
                state.design_stale = False
            state.stage = ConversationStage.REVIEWING_DESIGN if ok else ConversationStage.READY_TO_GENERATE
            state.updated_at = time.time()
            return state


#: Process-wide store shared by the chat route and the generation route.
conversation_store = ConversationStateStore()

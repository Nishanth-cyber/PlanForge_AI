"""Chat orchestrator: routes each chat message to the Requirement Agent or the configured LLM.

    User message
         |
    classify_intent  (deterministic, no LLM)
         |
         +-- REQUIREMENT / REQUIREMENT_REMOVAL --> Requirement Agent (authoritative, no LLM)
         |
         +-- CONVERSATION / PLAN_MODIFICATION  --> project context + bounded history
                                                    --> ConversationalLLMService.generate_reply()
                                                    --> real LLM response (or structured error)

Invariants
----------
* The LLM never changes requirements: for LLM-routed turns the structured requirement
  state is returned exactly as it was (read-only snapshot).
* The LLM never produces geometry. Plan modifications are only *explained*; the reply
  states explicitly that nothing was applied. Geometry stays with the Geometry Engine
  and only changes when the pipeline regenerates the plan.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote

from app.agents.requirement_agent.conversation import (
    ChatTurnResult,
    ConversationalRequirementAssistant,
)
from app.agents.requirement_agent.prompts import REQUIREMENT_EXTRACTION_PROMPT
from app.chat.context import (
    CHAT_SYSTEM_PROMPT,
    DEFAULT_HISTORY_MESSAGES,
    MODIFICATION_NOTE,
    build_chat_prompt,
    build_project_context,
    build_project_context_from_dict,
    trim_history,
)
from app.chat.intent import ChatIntent, IntentDecision, classify_intent, _ROOM_RE, _GREETING_RE
from app.chat.llm_service import ConversationalLLMService
from app.chat.agentic_decision import decide as agent_decide
from app.chat.entities import (
    CAPABILITY_REPLY,
    SUPPORTED_EXPORTS,
    contextualize_message,
    detect_export_formats,
    diff_summaries,
)
from app.chat.router import decide_presentation, decide_stage
from app.chat.schema import (
    REQUIREMENT_INTENTS,
    ChatAction,
    ConversationIntent as CI,
    QuickReply,
    ResponseType,
)
from app.chat.semantic_intent import ConversationIntentClassifier, IntentResult
from app.chat.state import ConversationState, ConversationStateStore, conversation_store
from app.llm.response_parser import LLMResponseParser
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement
from app.utils.ids import generate_id

logger = logging.getLogger("planforge.chat")

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")

_EDIT_COMMANDS = frozenset({"edit requirements", "\u270f edit requirements", "edit", "modify"})

NOT_APPLIED_FOOTER = (
    "*No changes have been applied to your floor plan.* To change your requirements, tell me explicitly "
    "(for example, *'Add a study room on Floor 1'*) and then regenerate the plan."
)


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


@dataclass
class ChatOrchestratorResult:
    """Everything the API layer needs to build a ChatTurnResponse."""

    turn: ChatTurnResult
    route: str
    turn_id: str
    llm_used: bool = False
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_latency_ms: Optional[int] = None
    plan_modified: bool = False
    # --- Structured, backend-decided response contract ---------------------------------
    intent: Optional[str] = None
    intent_source: str = "rules"
    response_type: Optional[ResponseType] = None
    stage: Optional[str] = None
    quick_replies: List[QuickReply] = field(default_factory=list)
    missing_requirements: List[str] = field(default_factory=list)
    requirements_updated: List[str] = field(default_factory=list)
    action: Optional[ChatAction] = None
    pending_field: Optional[str] = None
    conversation_id: Optional[str] = None
    project_id: Optional[str] = None
    requirement_turn: bool = False      # True when this turn read/changed structured requirements


class ChatOrchestrator:
    """Coordinates requirement collection and LLM-backed conversation."""

    def __init__(
        self,
        assistant: Optional[ConversationalRequirementAssistant] = None,
        llm_service: Optional[ConversationalLLMService] = None,
        registry: Any = None,
        outputs_dir: str = "outputs",
        history_messages: Optional[int] = None,
        state_store: Optional[ConversationStateStore] = None,
        intent_classifier: Optional[ConversationIntentClassifier] = None,
    ) -> None:
        """
        Args:
            assistant: Requirement-collection assistant (authoritative for requirements).
            llm_service: Service that calls the configured LLM.
            registry: Object exposing ``get_result(project_id)`` (the ProjectRegistry).
            outputs_dir: Directory holding persisted ``<project_id>/project.json`` bundles.
            history_messages: Max recent messages sent to the LLM (env PLANFORGE_CHAT_HISTORY_MESSAGES).
        """
        self.assistant = assistant or ConversationalRequirementAssistant()
        self.llm_service = llm_service or ConversationalLLMService()
        self.registry = registry
        self.outputs_dir = Path(outputs_dir)
        self.state_store = state_store or conversation_store
        self.intent_classifier = intent_classifier or ConversationIntentClassifier()
        self.history_messages = (
            history_messages
            if history_messages is not None
            else _env_int("PLANFORGE_CHAT_HISTORY_MESSAGES", DEFAULT_HISTORY_MESSAGES)
        )

    # ------------------------------------------------------------------
    def preview_route(self, message: str, input_source: str = "text") -> IntentDecision:
        """Classify a message without executing it (lets the UI know whether an LLM call will happen)."""
        return classify_intent(message, source=input_source)

    # ------------------------------------------------------------------
    # ==================================================================
    # Agentic conversation entry point
    # ==================================================================
    #
    #   message -> state loader -> intent (rules, optional validated LLM) -> decision router
    #           -> {direct answer | requirement agent | clarification | summary |
    #               generation action | validation | status | export}
    #           -> structured response (type, cards, action) -> state update
    #
    # The conversation layer never builds geometry and never starts a competing pipeline: a
    # generation request is returned as a validated ``ChatAction`` that the client executes
    # through the existing ``/generate`` endpoint, which owns the real generation status.
    def handle(
        self,
        *,
        message: str,
        existing_brief: Optional[str] = None,
        project_name: Optional[str] = None,
        project_id: Optional[str] = None,
        history: Optional[Sequence[Dict[str, Any]]] = None,
        active_floor: Optional[int] = None,
        alternative_index: Optional[int] = None,
        input_source: str = "text",
        conversation_id: Optional[str] = None,
    ) -> ChatOrchestratorResult:
        """Process one chat turn with context-aware intent routing and a structured response."""
        turn_id = generate_id("turn")
        pname = project_name or "PlanForge Residential Project"
        state = self.state_store.get_or_create(
            conversation_id,
            seed_brief=existing_brief or "",
            project_name=pname,
            project_id=project_id,
        )
        if project_id:
            state.project_id = project_id
            reg_res = self._get_registry_result(project_id)
            if reg_res is not None and getattr(reg_res, "floor_plan_set", None) is not None:
                state.generation_status = "completed"
        # Backend state is authoritative once it exists; the client brief only seeds a new state.
        brief = state.canonical_brief if state.has_requirements else (existing_brief or "")

        legacy = classify_intent(message, source=input_source)
        ci = self.intent_classifier.classify(
            message,
            state,
            source=input_source,
            legacy=legacy,
            llm_service=self.llm_service,
            turn_id=turn_id,
        )
        before_summary = state.last_summary
        is_start = not (message or "").strip() and not brief.strip()

        try:
            result = self._dispatch(
                ci=ci,
                legacy=legacy,
                state=state,
                turn_id=turn_id,
                message=message or "",
                brief=brief,
                pname=pname,
                history=history,
                active_floor=active_floor,
                alternative_index=alternative_index,
                input_source=input_source,
            )
        except Exception:  # noqa: BLE001 - the chat must degrade to a helpful message, never a 500
            logger.exception("chat turn %s failed (intent=%s)", turn_id, ci.intent.value)
            result = self._text_result(
                "Sorry, something went wrong while handling that message. Your project details are "
                "unchanged. Please try again, or rephrase what you would like to do.",
                brief,
                pname,
                turn_id,
                route="error",
            )
        return self._finalize(
            result, ci, state, before_summary=before_summary, brief=brief, is_start=is_start
        )

    # ------------------------------------------------------------------
    def _dispatch(
        self,
        *,
        ci: IntentResult,
        legacy: IntentDecision,
        state: ConversationState,
        turn_id: str,
        message: str,
        brief: str,
        pname: str,
        history: Optional[Sequence[Dict[str, Any]]],
        active_floor: Optional[int],
        alternative_index: Optional[int],
        input_source: str,
    ) -> ChatOrchestratorResult:
        intent = ci.intent
        clean = message.strip()
        project_id = state.project_id

        # ---- Direct conversational answers (no requirement cards) ---------------------------
        if intent == CI.GREETING:
            if not clean and not brief.strip():
                # Conversation start: welcome + (optional) project-type chooser for a brand-new user.
                turn = self.assistant.handle_turn("", None, project_name=pname)
                return ChatOrchestratorResult(
                    turn=turn, route="requirement", turn_id=turn_id, requirement_turn=True
                )
            text = self._fallback_conversational_reply(
                message=clean,
                decision=IntentDecision(ChatIntent.CONVERSATION, "greeting_or_acknowledgement"),
                context={},
                existing_brief=brief,
                project_name=pname,
            )
            return self._text_result(text, brief, pname, turn_id)

        if intent == CI.CAPABILITY_QUERY:
            return self._text_result(
                self._with_pending_reminder(CAPABILITY_REPLY, state), brief, pname, turn_id
            )

        if intent == CI.AMBIGUOUS_REQUEST:
            if brief.strip():
                text = (
                    "I'm not sure what you'd like me to do with that. You can give me project details "
                    "(plot size, floors, rooms), correct something you told me earlier, ask me to "
                    "summarise your requirements, or ask an architectural question."
                )
            else:
                text = (
                    "I'm not sure I understood. Are you describing a house you'd like designed "
                    "(for example *'a duplex on a 30x40 ft plot'*), or asking me a question?"
                )
            return self._text_result(text, brief, pname, turn_id, response_type=ResponseType.CLARIFICATION)

        if intent == CI.DESIGN_MODIFICATION:
            pid = project_id or state.project_id
            has_existing = bool(pid and (self._get_registry_result(pid) is not None or self._has_saved_bundle(pid)))
            if has_existing:
                return self._handle_design_edit(
                    turn_id=turn_id,
                    message=clean,
                    brief=brief,
                    pname=pname,
                    project_id=pid,
                    active_floor=active_floor,
                    alternative_index=alternative_index,
                    state=state,
                )
            if legacy is not None and legacy.intent == ChatIntent.PLAN_MODIFICATION:
                text = self._fallback_conversational_reply(
                    message=clean,
                    decision=legacy,
                    context={},
                    existing_brief=brief,
                    project_name=pname,
                )
                return self._text_result(text, brief, pname, turn_id, route="plan_modification")
            return self._text_result(
                "You don't have a generated floor plan yet to modify. Complete your requirements and generate a design first, and then you can modify it right here.",
                brief,
                pname,
                turn_id,
            )

        if intent == CI.GENERAL_ARCHITECTURAL_QUERY:
            decision = IntentDecision(ChatIntent.CONVERSATION, ci.reason)
            res = self._handle_llm_turn(
                decision=decision,
                turn_id=turn_id,
                message=clean,
                existing_brief=brief or None,
                project_name=pname,
                project_id=project_id,
                history=history,
                active_floor=active_floor,
                alternative_index=alternative_index,
            )
            res.turn.message = self._with_pending_reminder(res.turn.message, state)
            return res

        # ---- Operations grounded in real backend state ----------------------------------------
        if intent == CI.PROJECT_SUMMARY:
            return self._handle_summary(turn_id=turn_id, brief=brief, pname=pname)
        if intent == CI.GENERATE_FLOOR_PLAN:
            return self._handle_generate_request(turn_id=turn_id, brief=brief, pname=pname, state=state)
        if intent == CI.EXPORT_REQUEST:
            return self._handle_export(turn_id=turn_id, message=clean, brief=brief, pname=pname, state=state)
        if intent == CI.PROJECT_STATUS:
            return self._handle_status(turn_id=turn_id, brief=brief, pname=pname, state=state)
        if intent == CI.VALIDATION_QUERY:
            return self._handle_validation(
                turn_id=turn_id,
                message=clean,
                brief=brief,
                pname=pname,
                state=state,
                history=history,
                active_floor=active_floor,
                alternative_index=alternative_index,
            )

        # ---- Requirement collection family (authoritative Requirement Agent) ----------------
        ctx = contextualize_message(clean, state.pending_field)
        eff_floor = ctx.active_floor or active_floor
        res: ChatOrchestratorResult

        if legacy.intent == ChatIntent.AGENT_DECIDE:
            res = self._handle_agent_decision(
                turn_id=turn_id,
                message=clean,
                existing_brief=brief or None,
                project_name=pname,
                active_floor=eff_floor,
            )
        elif legacy.intent == ChatIntent.REQUIREMENT_REMOVAL:
            turn = self.assistant.handle_removal(
                message=clean, existing_brief=brief or None, project_name=pname
            )
            res = ChatOrchestratorResult(turn=turn, route=legacy.intent.value, turn_id=turn_id)
        elif intent == CI.REQUIREMENT_CORRECTION and clean.lower() not in _EDIT_COMMANDS:
            res = self._handle_correction(
                turn_id=turn_id, text=ctx.text, brief=brief, pname=pname, active_floor=eff_floor
            )
        else:
            res = self._handle_requirement_turn(
                turn_id=turn_id,
                message=ctx.text,
                existing_brief=brief or None,
                project_name=pname,
                project_id=project_id,
                history=history,
                active_floor=eff_floor,
                input_source=input_source,
            )
        res.requirement_turn = True
        return res

    # ------------------------------------------------------------------
    # Presentation + state update
    # ------------------------------------------------------------------
    def _finalize(
        self,
        result: ChatOrchestratorResult,
        ci: IntentResult,
        state: ConversationState,
        *,
        before_summary: Optional[Dict[str, Any]],
        brief: str,
        is_start: bool,
    ) -> ChatOrchestratorResult:
        turn = result.turn
        asked = turn.question_card                      # the question this turn raises (if any)
        question_text = self._question_text(turn, asked) if result.requirement_turn else None

        changed_fields = diff_summaries(before_summary, turn.requirements_summary) if result.requirement_turn else []
        requirement_changed = bool(changed_fields)

        if result.response_type is None:
            pres = decide_presentation(
                ci.intent, turn, state, requirement_changed=requirement_changed, is_conversation_start=is_start
            )
            turn.question_card = pres.card
            if pres.message_prefix:
                turn.message = pres.message_prefix + turn.message
            result.response_type = pres.response_type
            result.quick_replies = pres.quick_replies
        elif turn.question_card is not None:
            card = turn.question_card
            if card.field_key and card.field_key == state.last_card_key and not requirement_changed:
                turn.question_card = None               # identical card is still on screen

        # ---- state update ------------------------------------------------------------------------
        state.turn_count += 1
        state.last_intent = ci.intent.value
        if result.action is not None:
            state.last_action = {"type": result.action.type, "action_id": result.action.action_id, "status": result.action.status}
        if result.requirement_turn:
            state.canonical_brief = turn.requirements_text or state.canonical_brief
            state.last_summary = turn.requirements_summary or state.last_summary
            state.confirmed = {p.name: p.value for p in turn.progress if p.status == "completed" and p.value}
            state.missing = [p.name for p in turn.progress if p.status in ("current", "pending")]
            state.pending_field = asked.field_key if asked else None
            state.last_assistant_question = question_text
            shown = turn.question_card
            if shown is not None:
                state.last_card_key = shown.field_key
            elif asked is None or asked.field_key != state.last_card_key:
                state.last_card_key = None
            if requirement_changed and state.has_generated_design:
                state.design_stale = True
        state.stage = decide_stage(turn, state)

        result.intent = ci.intent.value
        result.intent_source = ci.source
        result.stage = state.stage.value
        result.requirements_updated = changed_fields
        result.missing_requirements = list(state.missing) if state.stage.value == "COLLECTING_REQUIREMENTS" else []
        result.pending_field = state.pending_field
        result.conversation_id = None if state.conversation_id == "transient" else state.conversation_id
        result.project_id = state.project_id
        self.state_store.save(state)
        return result

    # ------------------------------------------------------------------
    # Deterministic handlers
    # ------------------------------------------------------------------
    def _safe_snapshot(self, brief: str, pname: str) -> ChatTurnResult:
        try:
            return self.assistant.snapshot(brief or None, pname)
        except Exception:  # noqa: BLE001
            logger.exception("requirement snapshot failed")
            return ChatTurnResult(message="", project_name=pname, requirements_text=brief or "")

    def _text_turn(self, text: str, brief: str, pname: str) -> ChatTurnResult:
        """A card-less turn that reports the CURRENT requirement state unchanged."""
        base = self._safe_snapshot(brief, pname)
        return ChatTurnResult(
            message=text,
            question_card=None,
            is_ready_for_generation=base.is_ready_for_generation,
            requirements_text=brief or "",
            requirements_summary=base.requirements_summary,
            progress=base.progress,
            remaining_count=base.remaining_count,
            project_name=pname,
            status=base.status,
        )

    def _text_result(
        self,
        text: str,
        brief: str,
        pname: str,
        turn_id: str,
        *,
        route: str = "conversation",
        response_type: Optional[ResponseType] = None,
        action: Optional[ChatAction] = None,
    ) -> ChatOrchestratorResult:
        return ChatOrchestratorResult(
            turn=self._text_turn(text, brief, pname),
            route=route,
            turn_id=turn_id,
            response_type=response_type if response_type is not None else ResponseType.TEXT,
            action=action,
        )

    @staticmethod
    def _with_pending_reminder(text: str, state: ConversationState) -> str:
        """After answering a side question, gently restate the open requirement question (text only)."""
        if state.has_requirements and state.pending_field and state.last_assistant_question:
            return f"{text}\n\nWhenever you're ready, we can pick up where we left off: {state.last_assistant_question}"
        return text

    @staticmethod
    def _question_text(turn: ChatTurnResult, asked: Any) -> Optional[str]:
        if asked is None:
            return None
        if asked.input_type == "confirmation":
            return "Shall I generate the floor plan?"
        lines = [ln.strip() for ln in (turn.message or "").splitlines() if ln.strip()]
        last = re.sub(r"[*#`]", "", lines[-1]) if lines else ""
        return (last or asked.question)[:200]

    def _get_registry_result(self, project_id: Optional[str]) -> Any:
        if not project_id or self.registry is None:
            return None
        try:
            return self.registry.get_result(project_id)
        except Exception:  # noqa: BLE001
            return None

    def _has_saved_bundle(self, project_id: Optional[str]) -> bool:
        return bool(project_id and _SAFE_ID_RE.match(project_id) and (self.outputs_dir / project_id).is_dir())

    # ---- design modifications ----------------------------------------------------------------
    def _handle_design_edit(
        self,
        *,
        turn_id: str,
        message: str,
        brief: str,
        pname: str,
        project_id: str,
        active_floor: Optional[int],
        alternative_index: Optional[int],
        state: ConversationState,
    ) -> ChatOrchestratorResult:
        """Apply a natural-language modification to an existing generated design."""
        registry = self.registry
        if not registry:
            from app.api.registry import get_default_registry
            registry = get_default_registry()

        edit_res = registry.edit_project(
            project_id=project_id,
            instruction=message,
            floor_number=active_floor,
            alternative_index=alternative_index or 1,
        )

        if not edit_res:
            text = "Could not initialize design editing for this project. Please try again."
            return self._text_result(text, brief, pname, turn_id)

        if edit_res.clarification_required:
            return self._text_result(
                edit_res.clarification_question or "Could you clarify which room or element you would like to edit?",
                brief,
                pname,
                turn_id,
                response_type=ResponseType.CLARIFICATION,
            )

        if edit_res.new_design_requested:
            return self._text_result(
                "You requested a new design. You can start a new project using the New Project button.",
                brief,
                pname,
                turn_id,
            )

        if not edit_res.success:
            err_msg = edit_res.error_message or edit_res.summary
            alt_tip = f" {edit_res.feasible_alternatives[0]}" if edit_res.feasible_alternatives else ""
            reply_text = f"I couldn't apply that modification: {err_msg}. Your current floor plan has been preserved.{alt_tip}"
            return self._text_result(reply_text, brief, pname, turn_id)

        reply_text = f"I've updated your design: {edit_res.summary}"
        payload = self._design_payload(project_id)
        payload["version_id"] = edit_res.version_id
        payload["can_undo"] = edit_res.can_undo
        payload["summary"] = edit_res.summary
        payload["affected_rooms"] = edit_res.affected_rooms

        action = ChatAction(
            type="inspect",
            label="Updated Design",
            status="completed",
            payload=payload,
        )

        base = self._safe_snapshot(brief, pname)
        base.message = reply_text
        base.question_card = None

        return ChatOrchestratorResult(
            turn=base,
            route="edit_design",
            turn_id=turn_id,
            plan_modified=True,
            response_type=ResponseType.GENERATION_RESULT,
            action=action,
            project_id=project_id,
        )

    # ---- requirements summary ---------------------------------------------------------------
    def _handle_summary(self, *, turn_id: str, brief: str, pname: str) -> ChatOrchestratorResult:
        if not brief.strip():
            return self._text_result(
                "I don't have any requirements for this project yet. Tell me your plot size, number "
                "of floors or the rooms you want, and I'll keep track of them as we go.",
                brief,
                pname,
                turn_id,
            )
        base = self._safe_snapshot(brief, pname)
        lines: List[str] = []
        for p in base.progress:
            if p.status == "completed" and p.value and p.name != "Project type":
                lines.append(f"- **{p.name}**: {p.value}")
        try:
            reqs = self.assistant.requirement_agent.process(brief, project_name=pname).requirements
            for fl in reqs.floors:
                if fl.room_requirements:
                    rooms = ", ".join(
                        (f"{r.min_count} " if (r.min_count or 1) > 1 else "") + r.room_type.replace("_", " ").title()
                        for r in fl.room_requirements
                    )
                    lines.append(f"- **Floor {fl.floor_number} rooms**: {rooms}")
        except Exception:  # noqa: BLE001
            logger.exception("could not expand room list for summary")
        missing = [p.name for p in base.progress if p.status in ("current", "pending")]
        if base.is_ready_for_generation:
            tail = "Everything needed is in place — I can generate the floor plan whenever you're ready."
        elif missing:
            tail = "Still needed: " + ", ".join(missing) + "."
        else:
            tail = ""
        body = "\n".join(lines) if lines else "- Nothing concrete recorded yet."
        base.message = f"### Current Requirements\n\n{body}\n\n{tail}".strip()
        if not base.is_ready_for_generation:
            base.question_card = None                      # only offer Generate when it is actually possible
        return ChatOrchestratorResult(
            turn=base,
            route="conversation",
            turn_id=turn_id,
            response_type=ResponseType.REQUIREMENT_SUMMARY,
            requirement_turn=True,
        )

    # ---- generation request -------------------------------------------------------------------
    def _handle_generate_request(
        self, *, turn_id: str, brief: str, pname: str, state: ConversationState
    ) -> ChatOrchestratorResult:
        if state.generation_running:
            return self._text_result(
                "A floor-plan generation is already running for this project, so I haven't started a "
                "second one. Ask me for the status any time, and I'll show the result when it finishes.",
                brief,
                pname,
                turn_id,
                response_type=ResponseType.GENERATION_PROGRESS,
            )
        if not brief.strip():
            return self._text_result(
                "There's nothing to generate yet. Tell me about your plot and the rooms you want, and "
                "I'll collect the requirements first.",
                brief,
                pname,
                turn_id,
            )
        base = self._safe_snapshot(brief, pname)
        if not base.is_ready_for_generation:
            # Requirement completeness gate: never bypassed. Ask only what is genuinely missing.
            base.message = "I can't generate the floor plan quite yet. " + (base.message or "")
            return ChatOrchestratorResult(
                turn=base, route="requirement", turn_id=turn_id, requirement_turn=True
            )
        action = ChatAction(
            type="generate_floor_plan",
            label="Generate Floor Plan",
            status="ready",
            auto_execute=True,
            payload={
                "brief": brief,
                "project_name": pname,
                "conversation_id": None if state.conversation_id == "transient" else state.conversation_id,
            },
        )
        base.message = (
            "Your requirements are complete, so I'm sending them to the PlanForge generation pipeline. "
            "I'll report the real result, including validation, when it finishes."
        )
        base.question_card = None
        return ChatOrchestratorResult(
            turn=base,
            route="generate",
            turn_id=turn_id,
            response_type=ResponseType.GENERATION_PROGRESS,
            action=action,
            requirement_turn=True,
        )

    # ---- exports ----------------------------------------------------------------------------------
    @staticmethod
    def _export_url(project_id: str, fmt: str, bundle_png: Optional[str] = None) -> Optional[str]:
        pid = quote(project_id, safe="")
        if fmt == "dxf":
            return f"/projects/{pid}/export/dxf"
        if fmt == "svg":
            return f"/projects/{pid}/export/svg?floor=1"
        if fmt == "zip":
            return f"/projects/{pid}/export/zip"
        if fmt == "json":
            return f"/projects/{pid}/data"
        if fmt == "png" and bundle_png:
            return f"/projects/{pid}/export?file={quote(bundle_png, safe='')}"
        return None

    def _handle_export(
        self, *, turn_id: str, message: str, brief: str, pname: str, state: ConversationState
    ) -> ChatOrchestratorResult:
        formats, unsupported = detect_export_formats(message)
        supported_txt = ", ".join(k.upper() for k in SUPPORTED_EXPORTS)
        pid = state.project_id
        result = self._get_registry_result(pid)
        has_design = bool(pid and (result is not None or self._has_saved_bundle(pid)))
        lead = (
            f"I can't export {', '.join(u.upper() for u in unsupported)}. " if unsupported else ""
        )
        wanted = formats or list(SUPPORTED_EXPORTS)

        if not has_design:
            named = ", ".join(f.upper() for f in formats) if formats else supported_txt
            if state.has_requirements and self._safe_snapshot(brief, pname).is_ready_for_generation:
                nxt = "Your requirements are complete — say *'generate the floor plan'* to create one."
            elif state.has_requirements:
                nxt = "Once the remaining requirements are in, I can generate a plan to export."
            else:
                nxt = "Tell me about your project and I'll generate a plan you can export."
            text = (
                f"{lead}PlanForge supports {supported_txt} exports. {named} files are produced from a "
                f"generated floor plan, and you don't have one yet. {nxt}"
            )
            action = ChatAction(
                type="export",
                label="Export",
                status="unavailable",
                payload={"formats": wanted, "reason": "no_generated_design", "items": []},
            )
            return self._text_result(text, brief, pname, turn_id, response_type=ResponseType.ACTION_RESULT, action=action)

        # A design exists: offer only real, verifiable downloads.
        bundle_png: Optional[str] = None
        bundle_dir: Optional[Path] = None
        if result is not None and getattr(result, "export_bundle_path", None):
            bundle_dir = Path(result.export_bundle_path)
        elif self._has_saved_bundle(pid):
            bundle_dir = self.outputs_dir / pid
        if bundle_dir is not None and bundle_dir.is_dir():
            pngs = sorted(bundle_dir.rglob("*.png"))
            if pngs:
                bundle_png = pngs[0].relative_to(bundle_dir).as_posix()

        fps = getattr(result, "floor_plan_set", None) if result is not None else None
        plan_invalid = bool(fps is not None and getattr(fps, "validation_report", None) and not fps.all_valid)

        items: List[Dict[str, Any]] = []
        for fmt in wanted:
            available, note = True, ""
            url = self._export_url(pid, fmt, bundle_png)
            if fmt == "dxf" and plan_invalid:
                available, note = False, "The floor plan failed validation; DXF export is only allowed for valid plans."
            if fmt == "png" and not bundle_png:
                available, note = False, "No rendered PNG exists in this project's export bundle."
            items.append(
                {"format": fmt, "label": SUPPORTED_EXPORTS[fmt], "url": url if available else None, "available": available, "note": note}
            )
        ready = [i for i in items if i["available"]]
        blocked = [i for i in items if not i["available"]]
        parts = [lead.strip()] if lead else []
        if ready:
            parts.append("Ready to download: " + ", ".join(i["format"].upper() for i in ready) + ".")
        for b in blocked:
            parts.append(f"{b['format'].upper()} is not available — {b['note']}")
        action = ChatAction(
            type="export",
            label="Download",
            status="ready" if ready else "unavailable",
            payload={"project_id": pid, "formats": wanted, "items": items},
        )
        for i in ready:
            tag = f"{pid}:{i['format']}"
            if tag not in state.export_artifacts:
                state.export_artifacts.append(tag)
        return self._text_result(" ".join(parts), brief, pname, turn_id, response_type=ResponseType.ACTION_RESULT, action=action)

    # ---- status ----------------------------------------------------------------------------------
    def _handle_status(
        self, *, turn_id: str, brief: str, pname: str, state: ConversationState
    ) -> ChatOrchestratorResult:
        pid = state.project_id
        if state.generation_running:
            elapsed = int(time.time() - (state.generation_started_at or time.time()))
            return self._text_result(
                f"Your floor plan is being generated by the PlanForge pipeline (running for about {elapsed}s). "
                "Per-stage progress isn't streamed to the chat, so I can only confirm it is still running; "
                "I'll show the result as soon as it finishes.",
                brief,
                pname,
                turn_id,
                response_type=ResponseType.GENERATION_PROGRESS,
            )
        if state.generation_status == "failed":
            err = (state.generation_result or {}).get("error")
            return self._text_result(
                "The last generation attempt did not complete" + (f" ({err})" if err else "") + ". "
                "Your requirements are still saved — you can ask me to generate again.",
                brief,
                pname,
                turn_id,
            )
        if state.has_generated_design:
            payload = self._design_payload(pid)
            note = " Your requirements changed since then, so the design is out of date." if state.design_stale else ""
            return self._text_result(
                f"A floor plan has been generated for this project.{note}",
                brief,
                pname,
                turn_id,
                response_type=ResponseType.GENERATION_RESULT,
                action=ChatAction(type="inspect", label="Design", status="completed", payload=payload),
            )
        if brief.strip():
            base = self._safe_snapshot(brief, pname)
            missing = [p.name for p in base.progress if p.status in ("current", "pending")]
            text = "No floor plan has been generated yet. "
            text += (
                "Your requirements are complete and ready to generate."
                if base.is_ready_for_generation
                else "Still needed before generation: " + ", ".join(missing) + "."
            )
            return self._text_result(text, brief, pname, turn_id)
        return self._text_result(
            "We haven't started a project yet. Tell me about your plot and rooms whenever you're ready.",
            brief,
            pname,
            turn_id,
        )

    def _design_payload(self, project_id: Optional[str]) -> Dict[str, Any]:
        """Real validation / alternative facts for a generated project (never invented)."""
        payload: Dict[str, Any] = {"project_id": project_id}
        res = self._get_registry_result(project_id)
        if res is None:
            return payload
        payload["status"] = getattr(res, "status", None)
        payload["is_valid"] = getattr(res, "is_valid", None)
        report = getattr(res, "validation_report", None)
        if report is not None:
            payload["validation"] = {
                "overall_valid": bool(getattr(report, "overall_valid", False)),
                "overall_score": round(float(getattr(report, "overall_score", 0.0)), 2),
                "total_errors": getattr(report, "total_errors", 0),
                "total_warnings": getattr(report, "total_warnings", 0),
            }
        alt_set = getattr(res, "alternative_set", None)
        payload["alternatives_count"] = len(getattr(alt_set, "alternatives", []) or []) if alt_set else 0
        return payload

    # ---- validation --------------------------------------------------------------------------------
    def _handle_validation(
        self,
        *,
        turn_id: str,
        message: str,
        brief: str,
        pname: str,
        state: ConversationState,
        history: Optional[Sequence[Dict[str, Any]]],
        active_floor: Optional[int],
        alternative_index: Optional[int],
    ) -> ChatOrchestratorResult:
        pid = state.project_id
        res = self._get_registry_result(pid)
        report = getattr(res, "validation_report", None) if res is not None else None
        if report is None:
            # No validated geometry exists: answer as a (grounded) conversational question.
            return self._handle_llm_turn(
                decision=IntentDecision(ChatIntent.CONVERSATION, "validation_without_design"),
                turn_id=turn_id,
                message=message,
                existing_brief=brief or None,
                project_name=pname,
                project_id=pid,
                history=history,
                active_floor=active_floor,
                alternative_index=alternative_index,
            )
        valid = bool(getattr(report, "overall_valid", False))
        score = float(getattr(report, "overall_score", 0.0))
        lines = [
            f"The independent validator reports this design as **{'VALID' if valid else 'NOT VALID'}** "
            f"with a score of {score:.1f}/100, {getattr(report, 'total_errors', 0)} error(s) and "
            f"{getattr(report, 'total_warnings', 0)} warning(s)."
        ]
        try:
            issues = list(report.all_issues())
            issues.sort(key=lambda i: 0 if getattr(i, "severity", "") == "error" else 1)
            for issue in issues[:5]:
                msg = " ".join(str(getattr(issue, "message", "")).split())[:160]
                lines.append(
                    f"- [{getattr(issue, 'severity', '?')}] Floor {getattr(issue, 'floor_number', '?')}: {msg}"
                )
            if len(issues) > 5:
                lines.append(f"- …and {len(issues) - 5} more issue(s).")
        except Exception:  # noqa: BLE001
            logger.exception("could not list validation issues")
        payload = self._design_payload(pid)
        return self._text_result(
            "\n".join(lines),
            brief,
            pname,
            turn_id,
            response_type=ResponseType.ACTION_RESULT,
            action=ChatAction(type="validation", label="Validation", status="completed", payload=payload),
        )

    # ---- requirement corrections ----------------------------------------------------------------
    def _handle_correction(
        self, *, turn_id: str, text: str, brief: str, pname: str, active_floor: Optional[int]
    ) -> ChatOrchestratorResult:
        """Update previously supplied details, preserving everything the user did not mention."""
        agent = self.assistant.requirement_agent
        base = (
            agent.process(brief, project_name=pname).requirements
            if brief.strip()
            else Requirements(project_name=pname)
        )
        res = agent.update(base, text, active_floor=active_floor)
        self._apply_count_corrections(res.requirements, text, active_floor)
        turn = self.assistant.build_turn_result_from_reqs(res.requirements, text, pname)
        return ChatOrchestratorResult(turn=turn, route="requirement", turn_id=turn_id)

    def _apply_count_corrections(
        self, reqs: Requirements, text: str, active_floor: Optional[int]
    ) -> None:
        """A correction such as '2 bedrooms' must be able to LOWER a count (the merge only raises)."""
        try:
            parsed = self.assistant.requirement_agent.parser.parse(
                text, project_name=reqs.project_name, active_floor=active_floor
            )
        except Exception:  # noqa: BLE001
            return
        for nf in parsed.floors:
            if not nf.room_requirements:
                continue
            fn = (
                active_floor
                if (active_floor and active_floor > 1 and len(parsed.floors) == 1 and nf.floor_number == 1)
                else nf.floor_number
            )
            target = reqs.get_floor(fn)
            if target is None:
                continue
            for nr in nf.room_requirements:
                for er in target.room_requirements:
                    if er.room_type == nr.room_type:
                        er.min_count = nr.min_count
                        er.max_count = nr.max_count if nr.max_count is not None else nr.min_count

    # ==================================================================
    # Legacy (stateless) entry point, kept for backward compatibility
    # ==================================================================
    def handle_legacy(
        self,
        *,
        message: str,
        existing_brief: Optional[str] = None,
        project_name: Optional[str] = None,
        project_id: Optional[str] = None,
        history: Optional[Sequence[Dict[str, Any]]] = None,
        active_floor: Optional[int] = None,
        alternative_index: Optional[int] = None,
        input_source: str = "text",
    ) -> ChatOrchestratorResult:
        """Process one chat turn."""
        turn_id = generate_id("turn")
        pname = project_name or "PlanForge Residential Project"
        decision = classify_intent(message, source=input_source)

        if decision.intent == ChatIntent.REQUIREMENT:
            return self._handle_requirement_turn(
                turn_id=turn_id,
                message=message,
                existing_brief=existing_brief,
                project_name=pname,
                project_id=project_id,
                history=history,
                active_floor=active_floor,
                input_source=input_source,
            )

        if decision.intent == ChatIntent.REQUIREMENT_REMOVAL:
            turn = self.assistant.handle_removal(
                message=message, existing_brief=existing_brief, project_name=pname
            )
            return ChatOrchestratorResult(turn=turn, route=decision.intent.value, turn_id=turn_id, llm_used=False)

        if decision.intent == ChatIntent.AGENT_DECIDE:
            return self._handle_agent_decision(
                turn_id=turn_id,
                message=message,
                existing_brief=existing_brief,
                project_name=pname,
                active_floor=active_floor,
            )

        return self._handle_llm_turn(
            decision=decision,
            turn_id=turn_id,
            message=message,
            existing_brief=existing_brief,
            project_name=pname,
            project_id=project_id,
            history=history,
            active_floor=active_floor,
            alternative_index=alternative_index,
        )

    # ------------------------------------------------------------------
    def _handle_agent_decision(
        self,
        *,
        turn_id: str,
        message: str,
        existing_brief: Optional[str],
        project_name: str,
        active_floor: Optional[int],
    ) -> ChatOrchestratorResult:
        """Agentic handler: autonomously fills all missing requirements and
        returns an explanatory turn so the user understands every choice made."""
        # Parse whatever requirements we already have
        if existing_brief and existing_brief.strip():
            base_res = self.assistant.requirement_agent.process(existing_brief, project_name=project_name)
            reqs = base_res.requirements
        else:
            reqs = Requirements(project_name=project_name)

        # Let the Agentic Decision Engine fill every gap
        ad = agent_decide(reqs)

        # Rebuild structured turn from the now-complete requirements
        turn = self.assistant.build_turn_result_from_reqs(
            ad.requirements, message, project_name
        )
        # Override the reply with the agent's transparent explanation
        turn.message = ad.explanation_markdown

        return ChatOrchestratorResult(
            turn=turn,
            route="agent_decide",
            turn_id=turn_id,
            llm_used=False,
        )

    # ------------------------------------------------------------------
    def _handle_llm_turn(
        self,
        *,
        decision: IntentDecision,
        turn_id: str,
        message: str,
        existing_brief: Optional[str],
        project_name: str,
        project_id: Optional[str],
        history: Optional[Sequence[Dict[str, Any]]],
        active_floor: Optional[int],
        alternative_index: Optional[int],
    ) -> ChatOrchestratorResult:
        # Read-only view of the structured requirement state (never mutated by a question).
        try:
            snapshot: Optional[ChatTurnResult] = self.assistant.snapshot(existing_brief, project_name)
        except Exception:  # noqa: BLE001 - context enrichment must never break the chat
            logger.exception("requirement snapshot failed for turn %s", turn_id)
            snapshot = None

        requirement_state = None
        if snapshot is not None:
            requirement_state = {
                "remaining_count": snapshot.remaining_count,
                "progress": [p.to_dict() for p in snapshot.progress],
            }

        context = self._build_context(
            project_name=project_name,
            project_id=project_id,
            existing_brief=existing_brief,
            active_floor=active_floor,
            alternative_index=alternative_index,
            requirement_state=requirement_state,
        )

        prompt = build_chat_prompt(
            user_message=message,
            project_context=context,
            history=trim_history(history, self.history_messages),
            request_note=MODIFICATION_NOTE if decision.intent == ChatIntent.PLAN_MODIFICATION else None,
        )

        llm = self.llm_service.generate_reply(
            prompt=prompt,
            system_prompt=CHAT_SYSTEM_PROMPT,
            turn_id=turn_id,
            project_id=project_id,
            intent=decision.intent.value,
        )

        if llm.ok:
            reply_text = llm.text
            if decision.intent == ChatIntent.PLAN_MODIFICATION:
                reply_text = f"{reply_text}\n\n{NOT_APPLIED_FOOTER}"
        else:
            reply_text = self._fallback_conversational_reply(
                message=message,
                decision=decision,
                context=context,
                existing_brief=existing_brief,
                project_name=project_name,
            )
            # Be transparent when the configured model failed (not when it is simply not configured).
            if llm.status in ("LLM_TIMEOUT", "LLM_UNAVAILABLE", "LLM_EMPTY_RESPONSE") and llm.user_message:
                reply_text = f"{reply_text}\n\n*Note: {llm.user_message}*"
        turn = ChatTurnResult(
            message=reply_text,
            question_card=None,  # a question/explanation never re-displays requirement cards
            is_ready_for_generation=snapshot.is_ready_for_generation if snapshot else False,
            requirements_text=existing_brief or "",  # unchanged: a question never edits requirements
            requirements_summary=snapshot.requirements_summary if snapshot else None,
            progress=snapshot.progress if snapshot else [],
            remaining_count=snapshot.remaining_count if snapshot else 0,
            project_name=project_name,
            status=(snapshot.status if snapshot else "INITIAL") if not llm.ok else llm.status,
        )
        return ChatOrchestratorResult(
            turn=turn,
            route=decision.intent.value,
            turn_id=turn_id,
            llm_used=llm.ok,
            llm_provider=llm.provider,
            llm_model=llm.model,
            llm_latency_ms=llm.latency_ms,
            plan_modified=False,
        )

    def _fallback_conversational_reply(
        self,
        *,
        message: str,
        decision: IntentDecision,
        context: Dict[str, Any],
        existing_brief: Optional[str],
        project_name: str,
    ) -> str:
        """Deterministic architectural assistant fallback when LLM is unavailable or in mock mode."""
        norm = re.sub(r"\s+", " ", (message or "").strip().lower())

        # 1. Greetings & Pleasantries
        if _GREETING_RE.match(norm) or decision.reason == "greeting_or_acknowledgement":
            # Acknowledgements & thanks
            if re.search(r"\b(thanks|thank\s+you|thx|cool|great|awesome|ok|okay|got\s+it)\b", norm):
                return (
                    "You're welcome! Let me know if you would like to add or adjust any rooms, "
                    "or continue with floor plan generation."
                )
            if re.search(r"\b(bye|goodbye)\b", norm):
                return "Goodbye! Your project requirements are saved whenever you return."

            # Standard greetings (hi, hello, hey, etc.)
            if not existing_brief or not existing_brief.strip():
                return (
                    f"Hello! I am **PlanForge AI**, your conversational architectural design assistant.\n\n"
                    f"Tell me about your residential project requirements in plain language (for example: *'30x40 feet plot with 2 floors'*), "
                    f"or just ask me what I can design."
                )
            return (
                f"Hello! I am here to help you design and refine your floor plan for **{project_name}**.\n\n"
                f"You can tell me about additional rooms, ask questions about your layout, "
                f"or request adjustments."
            )

        # 2. Plan Modification Requests
        if decision.intent == ChatIntent.PLAN_MODIFICATION:
            return (
                "To adjust your floor plan layout or room dimensions, specify your updates directly in the chat "
                "(for example: *'Make master bedroom 14x16 ft'* or *'Add a balcony on Floor 1'* or *'Remove the study room'*). "
                "Once your requirements are updated, click **Generate Floor Plan** to apply the changes.\n\n"
                f"{NOT_APPLIED_FOOTER}"
            )

        # 3. Layout / Design Explanation Requests
        if any(w in norm for w in ("explain", "why", "layout", "walkthrough", "circulation", "how is", "where is", "placement")):
            if existing_brief and existing_brief.strip():
                brief_lines = [line.strip() for line in existing_brief.strip().split("\n") if line.strip()][:6]
                summary_snippet = "\n".join(f"- {line}" for line in brief_lines)
                return (
                    f"Here is an overview of the current design requirements for **{project_name}**:\n\n"
                    f"{summary_snippet}\n\n"
                    "PlanForge allocates spaces using the Adaptive Space Allocation Algorithm (ASAA), "
                    "clustering public zones near the entrance, placing wet areas for plumbing efficiency, "
                    "and positioning private bedrooms along outer edges for daylight and ventilation."
                )
            return (
                "PlanForge AI generates intelligent residential floor plans using an Adaptive Space Allocation Algorithm (ASAA). "
                "Once you define your plot dimensions and room needs, the system automatically partitions space, "
                "places doors and windows, and verifies municipal building codes.\n\n"
                "To begin, please share your plot size (e.g., *'30x40 feet'*) or ask me anything about the design process."
            )

        # 4. Dimension / Sizing Guidance
        if any(w in norm for w in ("size", "dimension", "standard", "how big", "area", "sq ft", "sqft", "sqm", "bhk")):
            return (
                "Here are standard residential dimension guidelines:\n\n"
                "• **Living Room**: 14ft x 16ft to 16ft x 20ft (spacious seating and circulation)\n"
                "• **Master Bedroom**: 12ft x 14ft to 14ft x 16ft (accommodates king bed and attached bath)\n"
                "• **Secondary Bedroom**: 10ft x 12ft to 12ft x 12ft\n"
                "• **Kitchen**: 8ft x 10ft to 10ft x 12ft (efficient counter work triangle)\n"
                "• **Bathrooms**: 5ft x 8ft to 6ft x 8ft\n\n"
                "You can specify your preferred dimensions directly (e.g., *'Living room 16x18 ft'*)."
            )

        # 5. General / Information Seeking Catch-All
        if not existing_brief or not existing_brief.strip():
            return (
                "I am your PlanForge architectural assistant. You can tell me about your plot dimensions, "
                "the number of floors, or the rooms you would like to include. "
                "What would you like to design today?"
            )
        return (
            f"I have your current requirements recorded for **{project_name}**. "
            "You can specify additional rooms, ask about dimensions or layouts, "
            "or proceed with generating your floor plan."
        )

    # ------------------------------------------------------------------
    def _handle_requirement_turn(
        self,
        *,
        turn_id: str,
        message: str,
        existing_brief: Optional[str],
        project_name: str,
        project_id: Optional[str],
        history: Optional[Sequence[Dict[str, Any]]],
        active_floor: Optional[int],
        input_source: str,
    ) -> ChatOrchestratorResult:
        clean_msg = message.strip()

        # 1. Fast path: initial empty greeting or explicit action commands
        if not clean_msg and not existing_brief:
            turn = self.assistant.handle_turn("", None, project_name=project_name)
            return ChatOrchestratorResult(turn=turn, route="requirement", turn_id=turn_id, llm_used=False)

        action_commands = {
            "edit requirements",
            "✏ edit requirements",
            "edit",
            "modify",
            "generate floor plan",
            "generate",
            "✓ generate floor plan",
        }
        if clean_msg.lower() in action_commands:
            turn = self.assistant.handle_turn(
                clean_msg,
                existing_brief=existing_brief,
                project_name=project_name,
                active_floor=active_floor,
            )
            return ChatOrchestratorResult(turn=turn, route="requirement", turn_id=turn_id, llm_used=False)

        # 2. Attempt real LLM invocation when configured
        extraction_prompt = REQUIREMENT_EXTRACTION_PROMPT.format(user_input=clean_msg)
        if existing_brief:
            extraction_prompt = (
                f"EXISTING REQUIREMENTS:\n{existing_brief}\n\n"
                f"ADDITIONAL USER INPUT:\n{clean_msg}\n\n"
                "Extract ONLY explicitly mentioned requirements into the JSON schema. Never invent unstated fields."
            )

        llm = self.llm_service.generate_reply(
            prompt=extraction_prompt,
            system_prompt=(
                "You are an expert architectural requirements analyst for PlanForge AI. "
                "Extract ONLY explicitly mentioned requirements. Never invent rooms, floors, or plot dimensions. "
                "Output pure JSON adhering to the schema."
            ),
            turn_id=turn_id,
            project_id=project_id,
            intent="requirement",
        )

        if llm.ok:
            # LLM successfully executed
            try:
                data = LLMResponseParser.parse_json(llm.text)
                if existing_brief:
                    base_res = self.assistant.requirement_agent.process(existing_brief, project_name=project_name)
                    reqs = base_res.requirements
                else:
                    reqs = Requirements(project_name=project_name, raw_input=clean_msg)

                self._apply_llm_data_to_requirements(reqs, data, clean_msg, active_floor=active_floor)
                # Combine with authoritative update to ensure no user requirements are lost
                res = self.assistant.requirement_agent.update(reqs, clean_msg, active_floor=active_floor)
                turn = self.assistant.build_turn_result_from_reqs(res.requirements, clean_msg, project_name)

                return ChatOrchestratorResult(
                    turn=turn,
                    route="requirement",
                    turn_id=turn_id,
                    llm_used=True,
                    llm_provider=llm.provider,
                    llm_model=llm.model,
                    llm_latency_ms=llm.latency_ms,
                )
            except Exception:
                turn = self.assistant.handle_turn(
                    clean_msg,
                    existing_brief=existing_brief,
                    project_name=project_name,
                    active_floor=active_floor,
                )
                return ChatOrchestratorResult(
                    turn=turn,
                    route="requirement",
                    turn_id=turn_id,
                    llm_used=True,
                    llm_provider=llm.provider,
                    llm_model=llm.model,
                    llm_latency_ms=llm.latency_ms,
                )

        # 3. Deterministic fallback when LLM is unavailable or disabled
        turn = self.assistant.handle_turn(
            clean_msg,
            existing_brief=existing_brief,
            project_name=project_name,
            active_floor=active_floor,
        )
        return ChatOrchestratorResult(
            turn=turn,
            route="requirement",
            turn_id=turn_id,
            llm_used=False,
            llm_provider=llm.provider,
            llm_model=llm.model,
            llm_latency_ms=llm.latency_ms,
        )

    @staticmethod
    def _apply_llm_data_to_requirements(
        reqs: Requirements,
        data: Dict[str, Any],
        user_message: str,
        active_floor: Optional[int] = None,
    ) -> None:
        """Apply parsed LLM JSON fields to Requirements without hallucinating rooms."""
        if not isinstance(data, dict):
            return

        # Plot dimensions
        pw = data.get("plot_width_m")
        pd = data.get("plot_depth_m")
        if pw is not None and pd is not None:
            try:
                w_f, d_f = float(pw), float(pd)
                if w_f > 0 and d_f > 0:
                    reqs.plot_dimensions = (w_f, d_f)
                    reqs.plot_area_sqm = round(w_f * d_f, 4)
            except (ValueError, TypeError):
                pass
        elif data.get("plot_area_sqm"):
            try:
                pa = float(data["plot_area_sqm"])
                if pa > 0 and not reqs.plot_area_sqm:
                    reqs.plot_area_sqm = pa
            except (ValueError, TypeError):
                pass

        # Target floors
        if data.get("target_floors"):
            try:
                tf = int(data["target_floors"])
                if tf > 0:
                    reqs.target_floors = tf
            except (ValueError, TypeError):
                pass

        # Orientation & Entrance
        if data.get("orientation"):
            reqs.orientation = str(data["orientation"]).lower()
        if data.get("entrance_facing"):
            reqs.entrance_facing = str(data["entrance_facing"]).lower()

        # Setbacks
        sb = data.get("setbacks")
        if isinstance(sb, dict):
            for k, v in sb.items():
                if v is not None:
                    try:
                        reqs.setbacks[k] = float(v)
                    except (ValueError, TypeError):
                        pass

        # Task 5 check: Only extract rooms from LLM if user actually mentioned rooms or BHK
        has_rooms_in_user_msg = bool(_ROOM_RE.search(user_message) or re.search(r"\b\d+\s*[-\s]?BHK\b", user_message, re.I))
        if has_rooms_in_user_msg and isinstance(data.get("floors"), list):
            for fl_data in data["floors"]:
                if not isinstance(fl_data, dict):
                    continue
                fn = fl_data.get("floor_number") or (active_floor if (active_floor and active_floor > 1) else 1)
                target_fl = reqs.get_floor(fn)
                if not target_fl:
                    target_fl = FloorRequirement(
                        floor_number=fn,
                        floor_name=f"Floor {fn}" if fn > 1 else "Ground Floor",
                        source="user",
                    )
                    reqs.floors.append(target_fl)

                raw_rooms = fl_data.get("rooms", [])
                for r in raw_rooms:
                    if not isinstance(r, dict):
                        continue
                    rtype = str(r.get("room_type", "")).strip().lower().replace(" ", "_")
                    if not rtype:
                        continue
                    cnt = int(r.get("count", 1) or 1)
                    pref_a = float(r["preferred_area_sqm"]) if r.get("preferred_area_sqm") else None
                    min_a = float(r["min_area_sqm"]) if r.get("min_area_sqm") else None
                    max_a = float(r["max_area_sqm"]) if r.get("max_area_sqm") else None
                    adj = [str(a).lower().replace(" ", "_") for a in r.get("adjacent_to", []) if a]
                    sep = [str(s).lower().replace(" ", "_") for s in r.get("separate_from", []) if s]
                    att = str(r["attached_to"]).lower().replace(" ", "_") if r.get("attached_to") else None

                    existing_r = next((er for er in target_fl.room_requirements if er.room_type == rtype), None)
                    if existing_r:
                        existing_r.min_count = max(existing_r.min_count, cnt)
                        if pref_a:
                            existing_r.preferred_area_sqm = pref_a
                        if min_a:
                            existing_r.min_area_sqm = min_a
                        if max_a:
                            existing_r.max_area_sqm = max_a
                        for a in adj:
                            if a not in existing_r.adjacency:
                                existing_r.adjacency.append(a)
                        for s in sep:
                            if s not in existing_r.separation:
                                existing_r.separation.append(s)
                        if att:
                            existing_r.attached_to = att
                    else:
                        target_fl.room_requirements.append(
                            RoomRequirement(
                                room_type=rtype,
                                min_count=cnt,
                                max_count=cnt,
                                preferred_area_sqm=pref_a,
                                min_area_sqm=min_a,
                                max_area_sqm=max_a,
                                adjacency=adj,
                                separation=sep,
                                attached_to=att,
                                source="user",
                            )
                        )

    # ------------------------------------------------------------------
    def _build_context(
        self,
        *,
        project_name: str,
        project_id: Optional[str],
        existing_brief: Optional[str],
        active_floor: Optional[int],
        alternative_index: Optional[int],
        requirement_state: Optional[Dict[str, Any]],
    ) -> str:
        result, data = self._load_project(project_id)
        try:
            if data is not None:
                return build_project_context_from_dict(
                    project_name=project_name,
                    project_id=project_id,
                    data=data,
                    active_floor=active_floor,
                    existing_brief=existing_brief,
                    requirement_state=requirement_state,
                )
            return build_project_context(
                project_name=project_name,
                project_id=project_id,
                existing_brief=existing_brief,
                result=result,
                active_floor=active_floor,
                alternative_index=alternative_index,
                requirement_state=requirement_state,
            )
        except Exception:  # noqa: BLE001 - degrade to a minimal context instead of failing the chat
            logger.exception("project context build failed; using minimal context")
            return f"Project: {project_name}\n(Detailed project context could not be built.)"

    def _load_project(self, project_id: Optional[str]):
        """Return (PipelineResult, None) from the registry, or (None, dict) from a saved bundle."""
        if not project_id:
            return None, None
        if self.registry is not None:
            try:
                result = self.registry.get_result(project_id)
            except Exception:  # noqa: BLE001
                result = None
            if result is not None:
                return result, None
        if _SAFE_ID_RE.match(project_id):
            path = self.outputs_dir / project_id / "project.json"
            if path.is_file():
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        return None, json.load(fh)
                except Exception:  # noqa: BLE001
                    logger.warning("could not read saved project bundle for %s", project_id)
        return None, None

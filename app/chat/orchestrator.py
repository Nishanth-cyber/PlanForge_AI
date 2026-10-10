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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

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
from app.llm.response_parser import LLMResponseParser
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement
from app.utils.ids import generate_id

logger = logging.getLogger("planforge.chat")

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")

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


class ChatOrchestrator:
    """Coordinates requirement collection and LLM-backed conversation."""

    def __init__(
        self,
        assistant: Optional[ConversationalRequirementAssistant] = None,
        llm_service: Optional[ConversationalLLMService] = None,
        registry: Any = None,
        outputs_dir: str = "outputs",
        history_messages: Optional[int] = None,
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

        base = snapshot or ChatTurnResult(message="", project_name=project_name)
        turn = ChatTurnResult(
            message=reply_text,
            question_card=base.question_card,  # retain active card so user can easily respond
            is_ready_for_generation=base.is_ready_for_generation,
            requirements_text=existing_brief or "",  # unchanged: a question never edits requirements
            requirements_summary=base.requirements_summary,
            progress=base.progress,
            remaining_count=base.remaining_count,
            project_name=project_name,
            status=base.status if not llm.ok else llm.status,
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
                    f"or choose one of the project types below to get started!"
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
                "To begin, please share your plot size (e.g., *'30x40 feet'*) or select a project type below!"
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

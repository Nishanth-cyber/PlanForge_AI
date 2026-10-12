"""Context-aware semantic intent understanding for the PlanForge chat.

Layering (cheapest and most reliable first):

1. **Deterministic rules** that use the conversation state (pending question, stage, whether a
   design already exists) -- instant, free, unit-testable.
2. **Optional LLM classification**, used only when the rules cannot decide (``AMBIGUOUS_REQUEST``)
   *and* a real provider is configured. The model must return JSON; the result is validated
   against the ``ConversationIntent`` enum and a confidence threshold before it is trusted.
   If the LLM is unavailable (mock/offline, timeout, bad JSON) the deterministic result stands.

The classifier never mutates requirements or triggers actions: it only labels the message.
Actions are validated separately by the orchestrator.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.chat.intent import (
    ChatIntent,
    IntentDecision,
    _COUNTED_ROOM_RE,
    _DIMS_RE,
    _GREETING_RE,
    _PLOT_FLOOR_RE,
    _QUESTION_START_RE,
    _ROOM_RE,
    _normalize,
)
from app.chat.schema import ConversationIntent as CI
from app.chat.state import ConversationState
from app.llm.response_parser import LLMResponseParser

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_GENERATE_COMMANDS = frozenset({"generate floor plan", "generate", "\u2713 generate floor plan", "generate the floor plan"})
_EDIT_COMMANDS = frozenset({"edit requirements", "\u270f edit requirements", "edit", "modify"})

_AFFIRM_RE = re.compile(
    r"^(?:yes|yeah|yep|yup|sure|ok|okay|go\s+ahead|proceed|do\s+it|please\s+do|sounds\s+good|"
    r"looks\s+good|confirm(?:ed)?|let'?s\s+(?:go|do\s+it))(?:\s+(?:please|generate|go\s+ahead|proceed))?\s*[!.]*$"
)

_EXPORT_RE = re.compile(
    r"\b(?:export|exports|download|save\s+(?:as|to)|dxf|svg|png|autocad|cad\s+(?:file|drawing)|zip|json)\b"
)
_VALIDATION_RE = re.compile(
    r"\b(?:valid(?:ate|ation|ity)?|complian(?:t|ce)|building\s+codes?|violations?|errors?|warnings?|"
    r"feasib(?:le|ility)|(?:does|will|would)\s+(?:it|this)\s+(?:pass|work|fit)|"
    r"is\s+(?:it|this)\s+(?:ok|okay|correct|fine|safe))\b"
)
_STATUS_RE = re.compile(
    r"\b(?:progress|status|how\s+long|how\s+far|still\s+(?:running|generating|working)|"
    r"is\s+(?:it|the\s+(?:plan|generation))\s+(?:done|ready|finished|complete)|"
    r"are\s+you\s+(?:done|finished)|what(?:'s|\s+is)\s+happening|eta)\b"
)
_SUMMARY_RE = re.compile(
    r"\b(?:summary|summari[sz]e|recap|current\s+requirements|what\s+(?:do\s+you|have\s+you)\s+(?:have|got|recorded|saved)|"
    r"what\s+have\s+i\s+(?:told|given|said|entered)|show\s+(?:me\s+)?(?:my\s+|the\s+)?requirements|"
    r"what(?:'s|\s+is)\s+(?:my|the)\s+(?:project|plan|requirements?)\s+so\s+far|so\s+far)\b"
)
_GENERATE_VERB_RE = re.compile(
    r"\b(?:generate|create|build|make|produce|draw|start\s+generat\w*|run\s+(?:the\s+)?(?:generation|pipeline))\b"
)
_PLAN_NOUN_RE = re.compile(r"\b(?:floor\s*plans?|plans?|layouts?|designs?)\b")
_POLITE_GENERATE_RE = re.compile(r"^(?:please\s+)?(?:can|could|would|will)\s+you\s+(?:please\s+)?generate\b")

_CAPABILITY_RE = re.compile(
    r"\bwhat\s+(?:can|could|do)\s+you\s+(?:do|build|design|make|create|help|offer|support)\b|"
    r"\bwhat\s+(?:are\s+)?(?:the\s+)?(?:things|types|kinds|sorts)\b.*\b(?:build|design|make|create|do|support)\b|"
    r"\bthings\s+you\s+can\b|"
    r"\bwhat\s+(?:is|are)\s+(?:planforge|you)\b|\bwho\s+are\s+you\b|\babout\s+planforge\b|"
    r"\b(?:your|planforge'?s?)\s+(?:capabilit(?:y|ies)|features)\b|"
    r"\bhow\s+does\s+(?:this|planforge|it)\s+work\b|"
    r"\bwhat\s+can\s+i\s+(?:ask|do|build|design)\b|^help\b"
)
_POLITE_CAPABILITY_RE = re.compile(
    r"^(?:please\s+)?(?:can|could|would|do)\s+you\s+(?:help|design|build|make|create|support|do)\b"
)

_CORRECTION_RE = re.compile(
    r"\b(?:actually|instead|rather|change|update|correct(?:ion)?|make\s+it|should\s+be|"
    r"no\s*,?\s+it'?s|sorry\s*,?|i\s+meant|replace|switch\s+to)\b"
)
_TYPE_RE = re.compile(
    r"\b(?:bungalow|duplex|town\s*house|custom\s+(?:residen\w*|home|house|layout|dimensions?)|"
    r"single[- ]floor|two[- ]floor|three[- ]floor|single[- ]stor(?:e)?y)\b"
)
_DOMAIN_RE = re.compile(
    r"\b(?:house|home|residen\w*|villa|apartment|flat|building|project|plot|site|land|floors?|storeys?|"
    r"rooms?|bedrooms?|bathrooms?|kitchen|living|bhk|construct\w*|design(?:ing)?|build(?:ing)?|plan)\b"
)
_ARCH_TOPIC_RE = re.compile(
    r"\b(?:vastu|ventilation|natural\s+light|daylight|setbacks?|fsi|far|circulation|staircase|stairs?|"
    r"orientation|facing|bedroom|kitchen|bathroom|living|dining|room\s+size|minimum|standard|"
    r"building\s+codes?|zoning|structure|load[- ]bearing|column|beam|plumbing|wet\s+areas?)\b"
)


@dataclass(frozen=True)
class IntentResult:
    """Outcome of intent classification."""

    intent: CI
    confidence: float
    reason: str
    source: str = "rules"           # "rules" | "llm"


def _signals(norm: str) -> Dict[str, bool]:
    return {
        "dims": bool(_DIMS_RE.search(norm)),
        "plot_floor": bool(_PLOT_FLOOR_RE.search(norm)),
        "counted_room": bool(_COUNTED_ROOM_RE.search(norm)),
        "room": bool(_ROOM_RE.search(norm)),
    }


def classify_conversation_intent(
    message: str,
    state: Optional[ConversationState] = None,
    *,
    source: str = "text",
    legacy: Optional[IntentDecision] = None,
) -> IntentResult:
    """Deterministic, state-aware intent classification."""
    raw = message or ""
    norm = _normalize(raw)
    pending = state.pending_field if state else None
    has_brief = bool(state and state.has_requirements)
    has_design = bool(state and state.has_generated_design)

    # 1. Card answers are always structured turns -------------------------------------------
    if source == "card":
        if "generate floor plan" in norm:
            return IntentResult(CI.GENERATE_FLOOR_PLAN, 0.99, "card_generate")
        if "edit requirements" in norm:
            return IntentResult(CI.REQUIREMENT_CORRECTION, 0.95, "card_edit")
        if _TYPE_RE.search(norm) and pending in (None, "project_type"):
            return IntentResult(CI.PROJECT_TYPE_SELECTION, 0.95, "card_project_type")
        if pending:
            return IntentResult(CI.REQUIREMENT_CLARIFICATION, 0.95, "card_answer")
        return IntentResult(CI.REQUIREMENT_INPUT, 0.9, "card_answer_no_pending")

    # 2. Empty message = conversation start -------------------------------------------------
    if not norm:
        return IntentResult(CI.GREETING, 0.99, "empty_initial_greeting")

    # 3. Explicit commands / confirmations ------------------------------------------------------
    if norm in _GENERATE_COMMANDS:
        return IntentResult(CI.GENERATE_FLOOR_PLAN, 0.99, "generate_command")
    if norm in _EDIT_COMMANDS:
        return IntentResult(CI.REQUIREMENT_CORRECTION, 0.95, "edit_command")
    if pending == "confirmation" and _AFFIRM_RE.match(norm):
        return IntentResult(CI.GENERATE_FLOOR_PLAN, 0.95, "confirmation_affirmed")
    if legacy is not None and legacy.reason == "plot_polygon_payload":
        return IntentResult(
            CI.REQUIREMENT_CLARIFICATION if pending == "plot_dimensions" else CI.REQUIREMENT_INPUT,
            0.95,
            "plot_polygon_payload",
        )

    sig = _signals(norm)
    structured = sig["dims"] or sig["plot_floor"] or sig["counted_room"]
    is_question = norm.endswith("?") or bool(_QUESTION_START_RE.match(norm))

    # 4. Operations on an existing project --------------------------------------------------------
    if _EXPORT_RE.search(norm) and not (structured and not is_question):
        return IntentResult(CI.EXPORT_REQUEST, 0.9, "export_keywords")
    if _VALIDATION_RE.search(norm) and not (sig["dims"] and not is_question):
        return IntentResult(CI.VALIDATION_QUERY, 0.85, "validation_keywords")
    if _STATUS_RE.search(norm):
        return IntentResult(CI.PROJECT_STATUS, 0.85, "status_keywords")
    if _SUMMARY_RE.search(norm):
        return IntentResult(CI.PROJECT_SUMMARY, 0.85, "summary_keywords")
    if _GENERATE_VERB_RE.search(norm) and _PLAN_NOUN_RE.search(norm) and not structured:
        if is_question and _POLITE_GENERATE_RE.match(norm) and not has_brief:
            return IntentResult(CI.CAPABILITY_QUERY, 0.7, "polite_generate_without_project")
        return IntentResult(CI.GENERATE_FLOOR_PLAN, 0.85, "generate_verb_plan_noun")

    # 4b. Editing / modifying an existing floor plan ------------------------------------------
    if has_design and not is_question:
        if (
            (legacy is not None and legacy.intent == ChatIntent.PLAN_MODIFICATION)
            or _MODIFY_RE.search(norm)
            or ("window" in norm and ("add" in norm or "remove" in norm or "put" in norm or "delete" in norm or "change" in norm))
            or ("door" in norm and ("add" in norm or "remove" in norm or "put" in norm or "delete" in norm or "change" in norm))
            or ("entrance" in norm and ("move" in norm or "shift" in norm or "relocate" in norm or "side" in norm or "east" in norm or "west" in norm or "north" in norm or "south" in norm))
            or ("circulation" in norm or "corridor" in norm)
            or ("l-shape" in norm or "l shaped" in norm)
            or ("spacious" in norm)
        ):
            return IntentResult(CI.DESIGN_MODIFICATION, 0.95, "edit_existing_design")

    # 5. Casual conversation / capabilities ----------------------------------------------------------
    if _GREETING_RE.match(norm):
        return IntentResult(CI.GREETING, 0.95, "greeting_or_acknowledgement")
    if not structured and (_CAPABILITY_RE.search(norm) or (is_question and _POLITE_CAPABILITY_RE.match(norm))):
        return IntentResult(CI.CAPABILITY_QUERY, 0.9, "capability_phrasing")

    # 6. Delegation / removal / modification (reuse the proven legacy rules) ------------------
    if legacy is not None:
        if legacy.intent == ChatIntent.AGENT_DECIDE:
            return IntentResult(CI.REQUIREMENT_INPUT, 0.9, "agent_delegation")
        if legacy.intent == ChatIntent.REQUIREMENT_REMOVAL:
            return IntentResult(CI.REQUIREMENT_CORRECTION, 0.9, legacy.reason)
        if legacy.intent == ChatIntent.PLAN_MODIFICATION:
            return IntentResult(CI.DESIGN_MODIFICATION, 0.85, legacy.reason)

    # 7. Questions are answered, not turned into requirement turns ---------------------------------
    if is_question:
        if legacy is not None and legacy.reason == "polite_add_request":
            return IntentResult(CI.REQUIREMENT_INPUT, 0.8, "polite_add_request")
        if _ARCH_TOPIC_RE.search(norm) or legacy is None or legacy.intent == ChatIntent.CONVERSATION:
            return IntentResult(CI.GENERAL_ARCHITECTURAL_QUERY, 0.8, "question")

    # 8. Requirement corrections / project type / answers to the pending question -----------
    has_signal = structured or sig["room"]
    if has_brief and has_signal and _CORRECTION_RE.search(norm):
        return IntentResult(CI.REQUIREMENT_CORRECTION, 0.85, "correction_cue")
    if _TYPE_RE.search(norm) and not sig["dims"] and not sig["counted_room"]:
        if pending in ("target_floors", "project_type") or pending is None:
            return IntentResult(
                CI.REQUIREMENT_CLARIFICATION if pending == "target_floors" else CI.PROJECT_TYPE_SELECTION,
                0.85,
                "project_type_phrase",
            )
    if pending and not is_question:
        return IntentResult(CI.REQUIREMENT_CLARIFICATION, 0.8, f"answers_pending:{pending}")

    # 9. New requirement statements ------------------------------------------------------------------------
    if has_signal or (legacy is not None and legacy.reason in ("requirement_statement", "polite_add_request")):
        return IntentResult(CI.REQUIREMENT_INPUT, 0.85, "requirement_signals")
    if _DOMAIN_RE.search(norm):
        return IntentResult(CI.REQUIREMENT_INPUT, 0.6, "domain_words_only")

    return IntentResult(CI.AMBIGUOUS_REQUEST, 0.3, "no_recognisable_signal")


# ---------------------------------------------------------------------------
# Optional LLM-backed semantic classification (validated)
# ---------------------------------------------------------------------------

_LLM_SYSTEM_PROMPT = (
    "You classify one message sent to PlanForge AI, a residential floor-plan design assistant. "
    "Reply with ONLY a JSON object: {\"intent\": <one of the allowed intents>, \"confidence\": <0..1>}. "
    "Do not answer the message. Do not invent requirements."
)


def _build_llm_prompt(message: str, state: Optional[ConversationState]) -> str:
    allowed = ", ".join(i.value for i in CI)
    ctx = {
        "stage": state.stage.value if state else "DISCOVERY",
        "pending_question_field": state.pending_field if state else None,
        "has_requirements": bool(state and state.has_requirements),
        "has_generated_design": bool(state and state.has_generated_design),
        "last_assistant_question": (state.last_assistant_question if state else None),
    }
    return (
        f"Allowed intents: {allowed}\n"
        f"Conversation context: {json.dumps(ctx)}\n"
        f"User message: {message.strip()[:1000]}\n"
        "Return the JSON object now."
    )


def validate_llm_intent(data: Any, state: Optional[ConversationState]) -> Optional[IntentResult]:
    """Validate an LLM classification payload; return ``None`` if it must not be trusted."""
    if not isinstance(data, dict):
        return None
    try:
        intent = CI(str(data.get("intent", "")).strip().upper())
        confidence = float(data.get("confidence", 0.0))
    except (ValueError, TypeError):
        return None
    if not 0.0 <= confidence <= 1.0 or confidence < 0.6:
        return None
    if intent == CI.AMBIGUOUS_REQUEST:
        return None
    # Never let the model route to generation when there is nothing to generate.
    if intent == CI.GENERATE_FLOOR_PLAN and not (state and state.has_requirements):
        return None
    return IntentResult(intent, confidence, "llm_classification", source="llm")


class ConversationIntentClassifier:
    """Rules first; falls back to a validated LLM classification only when rules are unsure."""

    def classify(
        self,
        message: str,
        state: Optional[ConversationState] = None,
        *,
        source: str = "text",
        legacy: Optional[IntentDecision] = None,
        llm_service: Any = None,
        turn_id: str = "",
    ) -> IntentResult:
        result = classify_conversation_intent(message, state, source=source, legacy=legacy)
        if result.intent != CI.AMBIGUOUS_REQUEST or llm_service is None:
            return result
        try:
            llm = llm_service.generate_reply(
                prompt=_build_llm_prompt(message, state),
                system_prompt=_LLM_SYSTEM_PROMPT,
                turn_id=turn_id,
                project_id=state.project_id if state else None,
                intent="intent_classification",
            )
            if not llm.ok:
                return result
            checked = validate_llm_intent(LLMResponseParser.parse_json(llm.text), state)
            return checked or result
        except Exception:  # noqa: BLE001 - classification must never break the chat
            return result

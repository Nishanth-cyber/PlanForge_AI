"""Deterministic intent routing for the PlanForge chat endpoint.

Design rule: the structured Requirement Agent flow is the DEFAULT. A message is
diverted away from it only when it is clearly conversational (a question, an
explanation request, a greeting) or clearly a request to change the *existing
plan* that the Requirement Agent cannot express.

Why this matters: the Requirement Parser extracts any room word it sees, so
feeding it "Why is the kitchen placed here?" or "Can you modify the bedroom?"
would silently add a kitchen/bedroom to the requirements, and "Remove the
dining room" would ADD a dining room. Those messages must never reach it.

Routing is intentionally rule-based (no LLM call) so it is instant, free,
deterministic and unit-testable. The LLM never decides whether requirements
change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class ChatIntent(str, Enum):
    """Where a chat message is handled."""

    #: Structured requirement collection/update -> Requirement Agent (no LLM).
    REQUIREMENT = "requirement"
    #: Remove rooms from the structured requirements -> deterministic handler (no LLM).
    REQUIREMENT_REMOVAL = "requirement_removal"
    #: General question / explanation -> configured LLM with project context.
    CONVERSATION = "conversation"
    #: Request to change the existing plan -> LLM explains; NOTHING is applied.
    PLAN_MODIFICATION = "plan_modification"
    #: User delegates a decision to the AI agent ("decide by you", "your choice", etc.).
    AGENT_DECIDE = "agent_decide"


@dataclass(frozen=True)
class IntentDecision:
    """Outcome of intent classification."""

    intent: ChatIntent
    reason: str

    @property
    def uses_llm(self) -> bool:
        """True when the message is answered by the configured LLM."""
        return self.intent in (ChatIntent.CONVERSATION, ChatIntent.PLAN_MODIFICATION)

    @property
    def is_agent_decision(self) -> bool:
        """True when the user wants the AI to decide autonomously."""
        return self.intent == ChatIntent.AGENT_DECIDE


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_ROOM_WORD = (
    r"(?:living|lounge|dining|kitchen|bed\s?rooms?|master|bath\s?rooms?|baths?|washrooms?|"
    r"toilets?|study|studies|office|library|pooja|prayer|storage|store\s?rooms?|utility|"
    r"pantry|laundry|servant|maid|porch|veranda|verandah|garage|parking|balcon(?:y|ies)|"
    r"terrace|foyer|hallway|corridor|lobby|stair(?:case)?s?|rooms?)"
)
_ROOM_RE = re.compile(rf"\b{_ROOM_WORD}\b")
_LAYOUT_RE = re.compile(
    r"\b(layout|plan|arrangement|design|placement|position|entrance|flow|orientation)\b"
)

# Messages the structured flow always owns.
_STRUCTURED_COMMANDS = frozenset(
    {
        "edit requirements",
        "\u270f edit requirements",
        "edit",
        "modify",
        "generate floor plan",
        "generate",
        "\u2713 generate floor plan",
    }
)

# Three or more "(x, y)" coordinate pairs => custom plot polygon payload.
_COORD_PAIR_RE = re.compile(r"\(\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\)")

# Agentic delegation: user asks the AI to decide / choose autonomously.
_AGENT_DECIDE_RE = re.compile(
    r"\b(?:"
    r"decide(?:\s+(?:by|for)\s+(?:you|me|us|yourself|it|the\s+ai))?|"
    r"your\s+(?:choice|call|pick|decision|recommendation|preference|suggestion)|"
    r"you\s+(?:decide|choose|pick|select|recommend|suggest)|"
    r"agent\s+(?:decide|choose|select)|"
    r"auto(?:matically)?\s+(?:decide|choose|select|fill|complete|pick)|"
    r"surprise\s+me|"
    r"whatever\s+(?:you\s+think|works|is\s+best|is\s+appropriate|is\s+standard)|"
    r"just\s+(?:decide|choose|pick|use\s+default|use\s+standard|fill\s+it(?:\s+in)?|go\s+ahead|proceed)|"
    r"use\s+(?:your\s+)?(?:best\s+)?(?:judgment|discretion|defaults?|standard)|"
    r"make\s+(?:the\s+)?(?:decision|choice|selection|recommendation)|"
    r"i(?:'?m|\s+am)?\s+(?:not\s+sure|unsure|flexible|open)|"
    r"(?:any|all)(?:\s+rooms?)?\s+(?:is|are)\s+fine|"
    r"standard\s+(?:layout|rooms?|configuration|setup|design)|"
    r"typical\s+(?:layout|rooms?|configuration|setup|design)|"
    r"default\s+(?:layout|rooms?|configuration|setup|design)"
    r")\b",
    re.I,
)

_GREETING_RE = re.compile(
    r"^(?:hi|hello|hey|hiya|hola|namaste|yo|good\s+(?:morning|afternoon|evening)|"
    r"thanks|thank\s+you|thx|ok|okay|cool|great|nice|awesome|got\s+it|bye|goodbye)"
    r"(?:\s+(?:there|planforge|planforge\s+ai))?\s*[!.?,]*$"
)

_QUESTION_START_RE = re.compile(
    r"^(?:what|whats|what's|why|how|when|where|which|who|whom|whose|is|are|was|were|"
    r"does|do|did|can|could|would|should|will|shall|may|might|explain|describe|"
    r"tell\s+me|summari[sz]e|walk\s+me\s+through|help\s+me\s+understand|compare|"
    r"clarify|elaborate|define)\b"
)

# "Can you ...", "Could we ...", "Is it possible to ..." => polite request, not a pure question.
_POLITE_REQUEST_RE = re.compile(
    r"^(?:please\s+)?(?:(?:can|could|would|will|may|shall)\s+(?:you|we|i)\b|"
    r"is\s+it\s+possible\s+to\b|are\s+you\s+able\s+to\b|would\s+it\s+be\s+possible\s+to\b)"
)

_EXPLAIN_WORD_RE = re.compile(r"\b(explain|why|how|what|which|describe|tell\s+me|clarify|define)\b")

_INFO_SEEKING_RE = re.compile(
    r"\b(?:i\s+)?(?:want|need|would\s+like|'d\s+like)\s+to\s+"
    r"(?:understand|know|see|check|learn|find\s+out|ask|hear|discuss|talk)\b|"
    r"\bhelp\s+me\b|\blet'?s\s+(?:talk|discuss)\b|\bi\s+(?:wonder|am\s+curious)\b"
)

_ADD_RE = re.compile(
    r"\b(?:add|adding|include|insert|append|i\s+want|we\s+want|i\s+need|we\s+need|"
    r"i'd\s+like|id\s+like|i\s+would\s+like|we\s+would\s+like|we'd\s+like|"
    r"should\s+have|must\s+have|needs?\s+to\s+have|has\s+to\s+have|put\s+in)\b"
)

_REMOVE_VERB_RE = re.compile(
    r"\b(?:remove|delete|drop|eliminate|scrap|cancel|get\s+rid\s+of|take\s+out|exclude|omit)\b"
)
_NEGATION_ROOM_RE = re.compile(
    rf"\b(?:no|without|don'?t\s+(?:want|need|have)|do\s+not\s+(?:want|need|have)|"
    rf"not\s+(?:want|need))\b[^,;.\n]*?\b{_ROOM_WORD}\b"
)

_MODIFY_RE = re.compile(
    r"\b(?:move|swap|switch|relocate|shift|resize|enlarge|expand|shrink|reduce|widen|narrow|"
    r"rotate|reposition|rearrange|reorient|flip|mirror|modify|redesign|rework|revise|change|"
    r"alter|adjust|improve|optimi[sz]e|bring|push|place)\b"
)

# Requirement-shaped content (dimensions, plot/floor words, counted rooms).
_DIMS_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:(?:ft|feet|foot|meters?|metres?|m|sq\.?\s*ft|sq\.?\s*m|sqft|sqm)\b|'|\u2019)"
    r"|\d+(?:\.\d+)?\s*(?:x|\u00d7|by)\s*\d+"
    r"|\d+(?:\.\d+)?\s*(?:m2|m\u00b2|ft2|ft\u00b2)"
)
_PLOT_FLOOR_RE = re.compile(
    r"\b(?:plot|site|setbacks?|floors?(?!\s+plan)|stor(?:ey|eys|y|ies)|levels?|bhk|facing|"
    r"ground\s+floor|duplex|bungalow|townhouse|polygon)\b|\bg\s*\+\s*\d"
)
_COUNTED_ROOM_RE = re.compile(
    r"\b(?:\d+|one|two|three|four|five|six)\s+(?:\w+\s+)?"
    r"(?:bed\s?rooms?|bath\s?rooms?|washrooms?|toilets?|kitchens?|living\s+rooms?|"
    r"dining\s+rooms?|study\s+rooms?|studies|offices|balcon(?:y|ies)|garages?|pooja\s+rooms?)\b"
)

# Preference / design-quality language: advisory, not an encodable requirement.
_PREFERENCE_RE = re.compile(
    r"\b(?:more|less|better|bigger|larger|smaller|wider|narrower|private|privacy|quieter|"
    r"brighter|spacious|open[- ]plan|arrangement|layout|flow|feel|cozy|airy)\b"
)


def _normalize(message: str) -> str:
    return re.sub(r"\s+", " ", (message or "").strip().lower())


def classify_intent(message: str, *, source: str = "text") -> IntentDecision:
    """Classify a chat message into the component that must handle it.

    Args:
        message: Raw user message.
        source: ``"card"`` when the text came from clicking a question-card
            option (always structured), otherwise ``"text"``.

    Returns:
        IntentDecision with the chosen intent and a human-readable reason
        (useful for logs and tests).
    """
    raw = message or ""
    norm = _normalize(raw)

    # --- Structured flow owns these unconditionally -------------------------
    if source == "card":
        return IntentDecision(ChatIntent.REQUIREMENT, "card_answer")
    if not norm:
        return IntentDecision(ChatIntent.REQUIREMENT, "empty_message_initial_greeting")
    if norm in _STRUCTURED_COMMANDS:
        return IntentDecision(ChatIntent.REQUIREMENT, "structured_command")
    if len(_COORD_PAIR_RE.findall(raw)) >= 3 or norm.startswith("plot polygon"):
        return IntentDecision(ChatIntent.REQUIREMENT, "plot_polygon_payload")

    # --- Agentic delegation: user wants the AI to decide -------------------
    if _AGENT_DECIDE_RE.search(norm):
        return IntentDecision(ChatIntent.AGENT_DECIDE, "agent_delegation")

    # --- Plain conversation --------------------------------------------------
    if _GREETING_RE.match(norm):
        return IntentDecision(ChatIntent.CONVERSATION, "greeting_or_acknowledgement")
    if _INFO_SEEKING_RE.search(norm):
        return IntentDecision(ChatIntent.CONVERSATION, "information_seeking")

    has_room = bool(_ROOM_RE.search(norm))
    has_layout = bool(_LAYOUT_RE.search(norm))
    is_question = norm.endswith("?") or bool(_QUESTION_START_RE.match(norm))

    # --- Questions -----------------------------------------------------------
    if is_question:
        if _POLITE_REQUEST_RE.match(norm) and not _EXPLAIN_WORD_RE.search(norm):
            if _ADD_RE.search(norm):
                return IntentDecision(ChatIntent.REQUIREMENT, "polite_add_request")
            if _REMOVE_VERB_RE.search(norm) and has_room:
                return IntentDecision(ChatIntent.REQUIREMENT_REMOVAL, "polite_remove_request")
            if _MODIFY_RE.search(norm) and (has_room or has_layout):
                return IntentDecision(ChatIntent.PLAN_MODIFICATION, "polite_modify_request")
        return IntentDecision(ChatIntent.CONVERSATION, "question")

    # --- Statements / imperatives -------------------------------------------
    if (_REMOVE_VERB_RE.search(norm) and has_room) or _NEGATION_ROOM_RE.search(norm):
        return IntentDecision(ChatIntent.REQUIREMENT_REMOVAL, "remove_or_exclude_room")

    has_dims = bool(_DIMS_RE.search(norm))
    has_plot_floor = bool(_PLOT_FLOOR_RE.search(norm))
    has_counted = bool(_COUNTED_ROOM_RE.search(norm))
    structured_signal = has_dims or has_plot_floor or has_counted

    if _ADD_RE.search(norm) or structured_signal:
        if _PREFERENCE_RE.search(norm) and not structured_signal:
            return IntentDecision(ChatIntent.PLAN_MODIFICATION, "design_preference")
        return IntentDecision(ChatIntent.REQUIREMENT, "requirement_statement")

    if _MODIFY_RE.search(norm) and (has_room or has_layout):
        return IntentDecision(ChatIntent.PLAN_MODIFICATION, "modify_existing_plan")

    # Default: keep the existing deterministic requirement flow.
    return IntentDecision(ChatIntent.REQUIREMENT, "default_structured_flow")

"""Presentation decisions: which response type, and which interactive options, a turn deserves.

The backend owns this decision so the frontend never renders cards "because a message was
sent". Rules (see the task's section 2):

* Non-requirement turns (greetings, capability / architectural questions, status, validation,
  exports, summaries without a ready project, ambiguity) NEVER carry requirement cards.
* A requirement question card is attached only when it helps: it is a *new* question (its
  ``field_key`` differs from the card still on screen) or the user's reply changed the
  requirements. A repeated identical card is suppressed and the question is asked in words.
* The project-type chooser is shown only for a brand-new, empty conversation start.
* A confirmation card (generate / edit) is shown only when requirements are complete.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.agents.requirement_agent.conversation import ChatTurnResult, QuestionCardData
from app.chat.schema import (
    REQUIREMENT_INTENTS,
    ConversationIntent as CI,
    ConversationStage,
    QuickReply,
    ResponseType,
)
from app.chat.state import ConversationState

#: Intents whose answer must never be accompanied by a requirement card.
CARDLESS_INTENTS = frozenset(
    {
        CI.GREETING,
        CI.CAPABILITY_QUERY,
        CI.GENERAL_ARCHITECTURAL_QUERY,
        CI.DESIGN_MODIFICATION,
        CI.VALIDATION_QUERY,
        CI.EXPORT_REQUEST,
        CI.PROJECT_STATUS,
        CI.AMBIGUOUS_REQUEST,
    }
)

REPEAT_PREFIX = "I wasn't able to pick that up from your last message. "


@dataclass
class Presentation:
    """How a turn is presented."""

    response_type: ResponseType
    card: Optional[QuestionCardData]
    quick_replies: List[QuickReply] = field(default_factory=list)
    message_prefix: str = ""


def _quick_replies_from_card(card: QuestionCardData) -> List[QuickReply]:
    if card.input_type not in ("single_choice", "direction"):
        return []
    return [QuickReply(label=o, value=o) for o in card.options[:6]]


def decide_presentation(
    intent: CI,
    turn: ChatTurnResult,
    state: ConversationState,
    *,
    requirement_changed: bool,
    is_conversation_start: bool = False,
) -> Presentation:
    """Choose the response type and the (possibly suppressed) card for a turn."""
    card = turn.question_card

    if intent in CARDLESS_INTENTS and not is_conversation_start:
        return Presentation(ResponseType.TEXT, None)

    if card is None:
        return Presentation(ResponseType.TEXT, None)

    # A repeated, unanswered, identical card adds nothing: ask in words instead.
    repeated = card.field_key is not None and card.field_key == state.last_card_key and not requirement_changed
    if repeated and not is_conversation_start:
        prefix = REPEAT_PREFIX if intent in REQUIREMENT_INTENTS and card.input_type != "confirmation" else ""
        rtype = (
            ResponseType.REQUIREMENT_SUMMARY if card.input_type == "confirmation" else ResponseType.CLARIFICATION
        )
        return Presentation(rtype, None, message_prefix=prefix)

    if card.field_key == "project_type":
        return Presentation(ResponseType.QUICK_REPLIES, card, _quick_replies_from_card(card))
    if card.input_type == "confirmation":
        return Presentation(ResponseType.REQUIREMENT_SUMMARY, card)
    return Presentation(ResponseType.CLARIFICATION, card, _quick_replies_from_card(card))


def decide_stage(turn: ChatTurnResult, state: ConversationState) -> ConversationStage:
    """Derive the workflow stage from real state."""
    if state.generation_running:
        return ConversationStage.GENERATING
    if state.has_generated_design and not state.design_stale:
        return ConversationStage.REVIEWING_DESIGN
    if turn.is_ready_for_generation:
        return ConversationStage.READY_TO_GENERATE
    if state.has_requirements or any(p.status == "completed" and p.name != "Project type" for p in turn.progress):
        return ConversationStage.COLLECTING_REQUIREMENTS
    return ConversationStage.DISCOVERY

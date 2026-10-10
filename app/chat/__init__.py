"""Conversational chat layer for PlanForge AI.

Routes each chat message either to the authoritative Requirement Agent
(structured requirement collection/update) or to the configured LLM
(general conversation grounded in the current project).

The chat layer never builds geometry: physical geometry remains the sole
responsibility of the deterministic Geometry Engine.
"""

from app.chat.intent import ChatIntent, IntentDecision, classify_intent

__all__ = ["ChatIntent", "IntentDecision", "classify_intent"]

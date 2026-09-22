"""LLM prompt templates for the Requirement Agent.

This module contains the text prompts used when LLM-backed requirement
extraction is enabled.  No LLM call is made here — this is a pure-data
module.  The actual LLM invocation is handled by ``app.llm.client`` (not yet
implemented in Phase 2).

To use in a future LLM-enabled flow::

    from app.agents.requirement_agent.prompts import REQUIREMENT_EXTRACTION_PROMPT
    from app.llm.client import LLMClient          # Phase 5

    client   = LLMClient()
    response = client.generate(
        prompt=REQUIREMENT_EXTRACTION_PROMPT.format(user_input=raw_text),
        schema=REQUIREMENT_JSON_SCHEMA,
    )
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

REQUIREMENT_EXTRACTION_PROMPT: str = """\
You are an expert architectural requirements analyst for PlanForge, an AI-assisted
floor-plan generation system.

Your task: extract ONLY the building requirements explicitly stated in the user's
input.  Do NOT invent rooms, floors, or preferences that were not mentioned.

USER INPUT:
\"\"\"
{user_input}
\"\"\"

Return a JSON object matching the schema below.  Use null for any field the user
did not explicitly mention.

SCHEMA:
{{
  "project_name":       <string | null>,
  "target_floors":      <integer | null>,
  "plot_width_m":       <float | null>,
  "plot_depth_m":       <float | null>,
  "plot_area_sqm":      <float | null>,
  "orientation":        <"north" | "south" | "east" | "west" | null>,
  "entrance_facing":    <"north" | "south" | "east" | "west" | null>,
  "setbacks": {{
    "front":  <float | null>,
    "rear":   <float | null>,
    "left":   <float | null>,
    "right":  <float | null>
  }},
  "floors": [
    {{
      "floor_number":      <integer>,
      "rooms": [
        {{
          "room_type":         <string>,
          "count":             <integer>,
          "preferred_area_sqm": <float | null>,
          "min_area_sqm":      <float | null>,
          "max_area_sqm":      <float | null>,
          "adjacent_to":       <list[string]>,
          "separate_from":     <list[string]>
        }}
      ]
    }}
  ]
}}

STRICT RULES:
- Set a field to null if the user did not mention it.
- Do NOT infer or assume room counts from context.
- Do NOT add rooms the user did not mention.
- Do NOT create additional floors beyond what the user stated.
- Canonical room types: bedroom, bathroom, kitchen, living, dining, study,
  storage, laundry, servant_room, porch, garage, balcony, circulation.
"""

# ---------------------------------------------------------------------------
# Validation / clarification prompt
# ---------------------------------------------------------------------------

REQUIREMENT_CLARIFICATION_PROMPT: str = """\
You are helping a user clarify their architectural brief for PlanForge.

The following required information is still missing:
{missing_fields}

Ask the user for only the missing details in a concise, friendly tone.
Do not ask for information that has already been provided.

Already provided:
{already_provided_summary}
"""

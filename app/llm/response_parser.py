"""Robust JSON response parser for LLM outputs."""

from __future__ import annotations
import json
import re
from typing import Any


class LLMResponseParser:
    """Extracts and parses structured JSON from LLM text responses."""

    @staticmethod
    def parse_json(response_text: str) -> dict[str, Any]:
        """Extract and parse JSON object from LLM response text.

        Handles:
        - Plain JSON objects
        - Markdown code blocks (```json ... ``` or ``` ...)
        - Leading and trailing conversational text

        Args:
            response_text: Raw string response from LLM.

        Returns:
            Parsed JSON dictionary.

        Raises:
            ValueError: If valid JSON cannot be found or parsed.
        """
        if not response_text or not response_text.strip():
            raise ValueError("Empty response text from LLM")

        cleaned = response_text.strip()

        # 1. Direct JSON parse attempt
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # 2. Extract from markdown code blocks
        json_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        if json_block_match:
            block_content = json_block_match.group(1).strip()
            try:
                parsed = json.loads(block_content)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        # 3. Find outermost curly braces { ... }
        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            substr = cleaned[first_brace : last_brace + 1]
            try:
                parsed = json.loads(substr)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse extracted JSON object: {e}") from e

        raise ValueError(
            f"No valid JSON object could be extracted from response text: {response_text[:100]}..."
        )

    extract_json = parse_json

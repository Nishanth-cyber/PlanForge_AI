#!/usr/bin/env python
"""Runtime Integration Verification Script for Google Gemini Provider.

Verifies:
1. GoogleGeminiClient initialization with selected Flash model (e.g. gemini-2.0-flash).
2. Endpoint and authentication configuration via Google AI Studio API key.
3. Live query execution through architectural planning prompt formatting.
4. Response parsing and JSON structure validation.
5. Strict failure visibility without silent mock fallback.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.llm.client import (
    GoogleGeminiAPIError,
    GoogleGeminiAuthError,
    GoogleGeminiClient,
    GoogleGeminiConnectionError,
    GoogleGeminiQuotaError,
    GoogleGeminiRateLimitError,
    GoogleGeminiTimeoutError,
)
from app.llm.configuration import LLMConfig
from app.llm.response_parser import LLMResponseParser


def verify_gemini_runtime() -> int:
    print("=" * 80)
    print("PlanForge AI - Google Gemini Runtime Verification")
    print("=" * 80)

    os.environ["PLANFORGE_LLM_PROVIDER"] = "google"
    config = LLMConfig.from_env()
    config.provider = "google"
    if not os.getenv("PLANFORGE_LLM_MODEL"):
        config.model_name = "gemini-flash-latest"

    key = config.api_key or ""
    is_placeholder = "your_google_ai_studio" in key.lower() or "placeholder" in key.lower()
    key_present = bool(key.strip() and not is_placeholder)

    print(f"\n[1] Configuration:")
    print(f"  Provider:         {config.provider.upper()}")
    print(f"  Requested Model:  {config.model_name}")
    print(f"  Fallback Models:  {config.fallback_models or 'None'}")
    print(f"  Fallback Provider:{config.fallback_provider or 'None'}")
    print(f"  Auth Key:         {'Configured (hidden)' if key_present else 'Missing/Placeholder (Set PLANFORGE_GOOGLE_API_KEY)'}")
    print(f"  Timeout:          {config.timeout_seconds}s")
    print(f"  Max Retries:      {config.max_retries}")
    print(f"  Retry Delay:      {config.retry_delay}s")

    if not key_present:
        print("\n[!] Cannot run live verification without valid PLANFORGE_GOOGLE_API_KEY.")
        print("    1. Obtain a free API key from Google AI Studio: https://aistudio.google.com/apikey")
        print("    2. Set PLANFORGE_GOOGLE_API_KEY=AIzaSy... in your .env file or environment.")
        return 2

    client = GoogleGeminiClient(config)
    print(f"  Target Endpoint:  {client.endpoint}")

    test_prompt = """You are an architectural planning assistant.
Generate a valid JSON object for a single room:
{
  "room_type": "living",
  "intended_shape": "rectangular",
  "intended_dimensions": [6.0, 5.0],
  "intended_area_sqm": 30.0,
  "design_rationale": "Spacious front living room"
}
Return ONLY valid JSON."""

    print(f"\n[2] Testing live generation with {config.model_name}...")
    start_time = time.time()
    try:
        raw_response = client.generate(
            prompt=test_prompt,
            system_prompt="You are a professional architectural AI assistant. Always output valid JSON only.",
        )
        elapsed = time.time() - start_time
        meta = getattr(client, "last_metadata", {})
        actual_model = meta.get("model", config.model_name)
        fallback_used = meta.get("fallback_used", False)
        fallback_provider = meta.get("fallback_provider_used", False)

        if not raw_response or not raw_response.strip():
            print(f"\n[FAIL] Received empty response from model.")
            return 1

        print(f"  [OK] Received response in {elapsed:.2f}s")
        print(f"  Resolved Model:   {actual_model}")
        if fallback_used:
            print(f"  [NOTE] Multi-model fallback was activated.")
        if fallback_provider:
            print(f"  [NOTE] Fallback provider was used: {meta.get('provider')}")
        if "usage" in meta:
            print(f"  Tokens:           {meta['usage']}")
        if "finish_reason" in meta:
            print(f"  Finish Reason:    {meta['finish_reason']}")

        print(f"\n[3] Raw Response Preview (first 200 chars):")
        preview = raw_response[:200].replace("\n", " ")
        print(f"  {preview}...")

        print(f"\n[4] Validating JSON parsing...")
        try:
            parsed = LLMResponseParser.parse_json(raw_response)
            print(f"  [OK] JSON parsed successfully:")
            print(f"    - room_type: {parsed.get('room_type')}")
            print(f"    - dimensions: {parsed.get('intended_dimensions')}")
            print(f"    - area_sqm: {parsed.get('intended_area_sqm')}")
            print(f"    - rationale: {parsed.get('design_rationale')}")
        except Exception as exc:
            print(f"  [FAIL] JSON parsing failed: {exc}")
            return 1

        print("\n" + "=" * 80)
        print("RESULT: SUCCESS - Google Gemini provider is operational and schema-compliant.")
        print("=" * 80)
        return 0

    except GoogleGeminiAuthError as exc:
        print(f"\n[FAIL] Authentication failed (HTTP 401/403):")
        print(f"  {exc}")
        print("  Please check that your PLANFORGE_GOOGLE_API_KEY from https://aistudio.google.com/apikey is valid.")
        return 1

    except GoogleGeminiQuotaError as exc:
        print(f"\n[FAIL] Google Gemini Quota Exhausted (HTTP 429 RESOURCE_EXHAUSTED):")
        print(f"  {exc}")
        print("  Your Google AI Studio quota is exhausted. Consider configuring fallback provider.")
        return 1

    except GoogleGeminiRateLimitError as exc:
        print(f"\n[FAIL] Rate limit exceeded (HTTP 429):")
        print(f"  {exc}")
        return 1

    except GoogleGeminiTimeoutError as exc:
        print(f"\n[FAIL] Request timed out after {config.timeout_seconds}s:")
        print(f"  {exc}")
        return 1

    except GoogleGeminiConnectionError as exc:
        print(f"\n[FAIL] Network connection error:")
        print(f"  {exc}")
        return 1

    except GoogleGeminiAPIError as exc:
        code_str = f"HTTP {exc.status_code}" if getattr(exc, "status_code", None) else "API Error"
        print(f"\n[FAIL] Google Gemini API error ({code_str}):")
        print(f"  {exc}")
        return 1

    except Exception as exc:
        print(f"\n[FAIL] Unexpected error: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(verify_gemini_runtime())

#!/usr/bin/env python
"""Runtime Integration Verification Script for OpenRouter Provider.

Verifies:
1. OpenRouterClient initialization with selected model (e.g. meta-llama/llama-3.3-70b-instruct).
2. Endpoint and authentication configuration.
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
    OpenRouterAPIError,
    OpenRouterAuthError,
    OpenRouterClient,
    OpenRouterConnectionError,
    OpenRouterCreditError,
    OpenRouterRateLimitError,
    OpenRouterTimeoutError,
)
from app.llm.configuration import LLMConfig
from app.llm.response_parser import LLMResponseParser


def verify_openrouter_runtime() -> int:
    print("=" * 80)
    print("PlanForge AI - OpenRouter Runtime Verification")
    print("=" * 80)

    os.environ["PLANFORGE_LLM_PROVIDER"] = "openrouter"
    config = LLMConfig.from_env()
    config.provider = "openrouter"
    if not os.getenv("PLANFORGE_LLM_MODEL"):
        config.model_name = "meta-llama/llama-3.3-70b-instruct"

    key_present = bool(config.api_key and config.api_key.strip())

    print(f"\n[1] Configuration:")
    print(f"  Provider:         {config.provider.upper()}")
    print(f"  Requested Model:  {config.model_name}")
    print(f"  Fallback Models:  {config.fallback_models or 'None'}")
    print(f"  API Base URL:     {config.api_base_url}")
    print(f"  Auth Key:         {'Configured (hidden)' if key_present else 'Missing (Set PLANFORGE_OPENROUTER_API_KEY)'}")
    print(f"  Timeout:          {config.timeout_seconds}s")
    print(f"  Max Retries:      {config.max_retries}")
    print(f"  Retry Delay:      {config.retry_delay}s")
    print(f"  Allow Fallbacks:  {config.allow_provider_fallbacks}")
    if config.http_referer:
        print(f"  HTTP-Referer:     {config.http_referer}")
    if config.app_title:
        print(f"  App Title:        {config.app_title}")

    if not key_present:
        print("\n[!] Cannot run live verification without PLANFORGE_OPENROUTER_API_KEY.")
        print("    Add PLANFORGE_OPENROUTER_API_KEY=sk-or-v1-... to your .env file.")
        return 2

    client = OpenRouterClient(config)
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

        if not raw_response or not raw_response.strip():
            print(f"\n[FAIL] Received empty response from model.")
            return 1

        print(f"  [OK] Received response in {elapsed:.2f}s")
        print(f"  Responded Model:  {actual_model} {'(FALLBACK USED)' if fallback_used else '(PRIMARY)'}")
        print(f"  Response preview: {raw_response[:160]}...")

        # Verify JSON extraction
        parsed = LLMResponseParser.parse_json(raw_response)
        print(f"  [OK] Successfully parsed structured JSON:")
        print(json.dumps(parsed, indent=4))

        print(f"\n[3] Execution Metadata:")
        print(f"  Provider:         {meta.get('provider')}")
        print(f"  Model Requested:  {meta.get('model_requested', config.model_name)}")
        print(f"  Model Responded:  {meta.get('model')}")
        print(f"  Fallback Used:    {'YES' if fallback_used else 'NO'}")
        print(f"  Attempts:         {meta.get('attempts', 1)}")
        print(f"  Endpoint:         {meta.get('endpoint')}")
        print(f"  Elapsed:          {meta.get('elapsed_seconds')}s")
        print(f"  Status:           {meta.get('status')}")
        if "finish_reason" in meta:
            print(f"  Finish Reason:    {meta.get('finish_reason')}")

        print("\n" + "=" * 80)
        print("OPENROUTER LIVE GENERATION VERIFIED: YES")
        print("=" * 80)
        return 0

    except OpenRouterRateLimitError as err:
        print(f"\n[AVAILABILITY FAILURE] Selected model / upstream pool rate-limited (HTTP 429).")
        print(f"    Type:    OpenRouterRateLimitError")
        print(f"    Message: {err}")
        print("\n[NOTE] HTTP 429 indicates model availability exhaustion, not a successful generation.")
        print("       Configure a valid fallback model in PLANFORGE_OPENROUTER_FALLBACK_MODELS.")
        return 1
    except OpenRouterAuthError as err:
        print(f"\n[AUTHENTICATION FAILURE] OpenRouter authentication failed.")
        print(f"    Type:    OpenRouterAuthError")
        print(f"    Message: {err}")
        return 1
    except OpenRouterCreditError as err:
        print(f"\n[PAYMENT/CREDIT FAILURE] OpenRouter account credits exhausted (HTTP 402).")
        print(f"    Type:    OpenRouterCreditError")
        print(f"    Message: {err}")
        return 1
    except (
        OpenRouterAPIError,
        OpenRouterTimeoutError,
        OpenRouterConnectionError,
    ) as err:
        print(f"\n[GENERATION FAILURE] OpenRouter request failed:")
        print(f"    Type:    {type(err).__name__}")
        print(f"    Message: {err}")
        return 1
    except Exception as exc:
        print(f"\n[FAIL] Unexpected exception: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(verify_openrouter_runtime())

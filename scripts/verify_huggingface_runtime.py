#!/usr/bin/env python
"""Runtime Integration Verification Script for Hugging Face DeepSeek Model.

Verifies:
1. HuggingFaceClient initialization with DeepSeek model (e.g. deepseek-ai/DeepSeek-R1-Distill-Qwen-7B).
2. Endpoint and authentication configuration.
3. Live query execution through the Architectural Design Agent prompt formatting.
4. Response parsing and <think> reasoning token handling.
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
    HuggingFaceAPIError,
    HuggingFaceClient,
    HuggingFaceConnectionError,
    HuggingFaceTimeoutError,
)
from app.llm.configuration import LLMConfig
from app.llm.response_parser import LLMResponseParser


def verify_huggingface_runtime() -> int:
    print("=" * 80)
    print("PlanForge AI - Hugging Face DeepSeek Runtime Verification")
    print("=" * 80)

    config = LLMConfig.from_env()
    config.provider = "huggingface"
    if not os.getenv("PLANFORGE_LLM_MODEL"):
        config.model_name = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"

    print(f"\n[1] Configuration:")
    print(f"  Provider:       {config.provider.upper()}")
    print(f"  Model:          {config.model_name}")
    print(f"  API Base URL:   {config.api_base_url}")
    print(f"  Auth Key:       {'Configured (hidden)' if config.api_key else 'Not configured (Public free tier)'}")
    print(f"  Timeout:        {config.timeout_seconds}s")

    client = HuggingFaceClient(config)
    print(f"  Target Endpoint: {client.endpoint}")

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
        print(f"  [OK] Received response in {elapsed:.2f}s")
        print(f"  Response preview: {raw_response[:160]}...")

        # Verify JSON extraction and reasoning stripping
        parsed = LLMResponseParser.parse_json(raw_response)
        print(f"  [OK] Successfully parsed structured JSON:")
        print(json.dumps(parsed, indent=4))

        meta = getattr(client, "last_metadata", {})
        print(f"\n[3] Execution Metadata:")
        print(f"  Provider:         {meta.get('provider')}")
        print(f"  Model:            {meta.get('model')}")
        print(f"  Endpoint:         {meta.get('endpoint')}")
        print(f"  Elapsed:          {meta.get('elapsed_seconds')}s")
        print(f"  Status:           {meta.get('status')}")

        print("\n" + "=" * 80)
        print("HUGGING FACE DEEPSEEK RUNTIME VERIFIED: YES")
        print("=" * 80)
        return 0

    except (HuggingFaceConnectionError, HuggingFaceTimeoutError, HuggingFaceAPIError) as err:
        print(f"\n[!] Hugging Face execution encountered error as expected when offline or unauthenticated:")
        print(f"    Type:    {type(err).__name__}")
        print(f"    Message: {err}")
        print("\n[NOTE] Provider correctly raised explicit error without silent mock fallback.")
        return 1
    except Exception as exc:
        print(f"\n[FAIL] Unexpected exception: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(verify_huggingface_runtime())

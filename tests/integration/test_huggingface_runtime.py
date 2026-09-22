"""Integration test verifying the Hugging Face DeepSeek execution path.

This test optionally queries the Hugging Face Serverless Inference API with a DeepSeek model.
If offline or network resolution fails, the test skips gracefully without breaking CI suites.
"""

from __future__ import annotations

import os
import pytest

from app.llm.client import (
    HuggingFaceAPIError,
    HuggingFaceClient,
    HuggingFaceConnectionError,
    HuggingFaceTimeoutError,
)
from app.llm.configuration import LLMConfig


def test_huggingface_deepseek_connection_or_skip():
    """Verify Hugging Face DeepSeek client can be initialized and fails explicitly if offline."""
    cfg = LLMConfig.from_env()
    cfg.provider = "huggingface"
    if not os.getenv("PLANFORGE_LLM_MODEL"):
        cfg.model_name = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"

    client = HuggingFaceClient(cfg)
    assert client.config.provider == "huggingface"
    assert "deepseek" in client.config.model_name.lower()

    # Attempt a lightweight call; if offline/unreachable, expect clean structured exception or skip
    try:
        resp = client.generate("Reply with {\"status\": \"ok\"}")
        assert isinstance(resp, str)
        assert len(resp) > 0
    except (HuggingFaceConnectionError, HuggingFaceTimeoutError, HuggingFaceAPIError) as e:
        pytest.skip(f"Hugging Face DeepSeek endpoint currently not reachable in this test environment: {e}")

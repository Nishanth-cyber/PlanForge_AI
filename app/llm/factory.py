"""Factory for creating LLM clients."""

from __future__ import annotations
from typing import Optional
from app.llm.client import HuggingFaceClient, LLMClient, MockLLMClient
from app.llm.configuration import LLMConfig


def create_llm_client(config: Optional[LLMConfig] = None) -> LLMClient:
    """Create an LLM client based on configuration or environment.

    Args:
        config: LLMConfig object. If None, loaded from environment via LLMConfig.from_env().

    Returns:
        LLMClient instance (HuggingFaceClient or MockLLMClient).
    """
    cfg = config or LLMConfig.from_env()

    if cfg.provider in ("huggingface", "hf"):
        return HuggingFaceClient(cfg)

    # Default to MockLLMClient for testing and offline safety
    return MockLLMClient()

"""Factory for creating LLM clients."""

from __future__ import annotations
from typing import Optional
from app.llm.client import (
    GoogleGeminiClient,
    HuggingFaceClient,
    LLMClient,
    MockLLMClient,
    OpenRouterClient,
)
from app.llm.configuration import LLMConfig


def create_llm_client(config: Optional[LLMConfig] = None) -> LLMClient:
    """Create an LLM client based on configuration or environment.

    Args:
        config: LLMConfig object. If None, loaded from environment via LLMConfig.from_env().

    Returns:
        LLMClient instance (GoogleGeminiClient, OpenRouterClient, HuggingFaceClient, or MockLLMClient).

    Raises:
        ValueError: If the configured provider name is unsupported.
    """
    cfg = config or LLMConfig.from_env()

    if cfg.provider in ("google", "gemini"):
        fallback_client: Optional[LLMClient] = None
        if cfg.fallback_provider in ("openrouter", "or"):
            fallback_client = OpenRouterClient(cfg)
        elif cfg.fallback_provider in ("huggingface", "hf"):
            fallback_client = HuggingFaceClient(cfg)
        return GoogleGeminiClient(cfg, fallback_client=fallback_client)

    if cfg.provider in ("openrouter", "or"):
        return OpenRouterClient(cfg)

    if cfg.provider in ("huggingface", "hf"):
        return HuggingFaceClient(cfg)

    if cfg.provider == "mock":
        return MockLLMClient()

    raise ValueError(
        f"Unsupported LLM provider: '{cfg.provider}'. "
        "Supported providers are: 'google', 'openrouter', 'huggingface', 'mock'."
    )

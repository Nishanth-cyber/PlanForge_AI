"""LLM configuration model for PlanForge AI."""

from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def load_dotenv_file(filepath: Optional[str] = None) -> None:
    """Read a .env file and populate os.environ if keys are not already set."""
    if filepath is None:
        candidates = [
            Path.cwd() / ".env",
            Path(__file__).resolve().parent.parent.parent / ".env",
        ]
        for c in candidates:
            if c.is_file():
                filepath = str(c)
                break
    if not filepath or not os.path.isfile(filepath):
        return

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


@dataclass
class LLMConfig:
    """Configuration for LLM providers."""
    provider: str = "mock"  # "mock", "huggingface"
    model_name: str = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout_seconds: float = 120.0
    api_base_url: Optional[str] = "https://api-inference.huggingface.co/models"
    api_key: Optional[str] = None

    @classmethod
    def from_env(cls) -> LLMConfig:
        """Create an LLMConfig instance populated from environment variables.

        Environment variables:
            PLANFORGE_LLM_PROVIDER: Provider name ('mock', 'huggingface')
            PLANFORGE_LLM_MODEL: Model name (default: 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B')
            PLANFORGE_HF_BASE_URL: Base URL for Hugging Face Inference API
            PLANFORGE_HF_API_KEY / HF_TOKEN: Hugging Face API key
            PLANFORGE_LLM_TEMPERATURE: Sampling temperature
            PLANFORGE_LLM_TIMEOUT: Request timeout in seconds
            PLANFORGE_LLM_MAX_TOKENS: Max tokens to generate
        """
        load_dotenv_file()
        provider = os.getenv("PLANFORGE_LLM_PROVIDER", "mock").strip().lower()

        # Determine model and base_url default based on provider
        if provider in ("huggingface", "hf"):
            default_model = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
            default_base_url = os.getenv("PLANFORGE_HF_BASE_URL", "https://api-inference.huggingface.co/models").strip()
            default_timeout = 120.0
        else:
            default_model = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
            default_base_url = "https://api-inference.huggingface.co/models"
            default_timeout = 60.0

        model_name = os.getenv("PLANFORGE_LLM_MODEL", default_model).strip()
        base_url = default_base_url

        try:
            temp = float(os.getenv("PLANFORGE_LLM_TEMPERATURE", "0.2"))
        except ValueError:
            temp = 0.2

        try:
            timeout = float(os.getenv("PLANFORGE_LLM_TIMEOUT", str(default_timeout)))
        except ValueError:
            timeout = default_timeout

        try:
            max_tokens = int(os.getenv("PLANFORGE_LLM_MAX_TOKENS", "4096"))
        except ValueError:
            max_tokens = 4096

        api_key = (
            os.getenv("PLANFORGE_HF_API_KEY")
            or os.getenv("HF_TOKEN")
            or os.getenv("PLANFORGE_LLM_API_KEY")
        )

        return cls(
            provider=provider,
            model_name=model_name,
            temperature=temp,
            max_tokens=max_tokens,
            timeout_seconds=timeout,
            api_base_url=base_url,
            api_key=api_key,
        )

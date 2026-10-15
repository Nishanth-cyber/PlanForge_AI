"""LLM configuration model for PlanForge AI."""

from __future__ import annotations
import os
from dataclasses import dataclass, field
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
    provider: str = "mock"  # "google", "openrouter", "huggingface", "mock"
    model_name: str = "gemini-2.0-flash"
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout_seconds: float = 120.0
    api_base_url: Optional[str] = "https://generativelanguage.googleapis.com"
    api_key: Optional[str] = None
    http_referer: Optional[str] = None
    app_title: Optional[str] = "PlanForge AI"
    fallback_models: list[str] = field(default_factory=list)
    fallback_provider: Optional[str] = None
    max_retries: int = 3
    retry_delay: float = 1.0
    allow_provider_fallbacks: bool = True

    @classmethod
    def from_env(cls) -> LLMConfig:
        """Create an LLMConfig instance populated from environment variables.

        Environment variables:
            PLANFORGE_LLM_PROVIDER: Provider name ('google', 'openrouter', 'huggingface', 'mock')
            PLANFORGE_GOOGLE_API_KEY / GEMINI_API_KEY: Google Gemini API key
            PLANFORGE_LLM_MODEL: Model name (e.g. 'gemini-2.0-flash', 'gemini-1.5-flash')
            PLANFORGE_FALLBACK_PROVIDER: Optional secondary provider on quota exhaustion ('openrouter')
            PLANFORGE_OPENROUTER_API_KEY / OPENROUTER_API_KEY: OpenRouter API key
            PLANFORGE_OPENROUTER_BASE_URL: OpenRouter endpoint (default: 'https://openrouter.ai/api/v1/chat/completions')
            PLANFORGE_OPENROUTER_HTTP_REFERER: Optional attribution URL header
            PLANFORGE_OPENROUTER_TITLE: Optional attribution application name header
            PLANFORGE_OPENROUTER_FALLBACK_MODELS: Comma-separated list of fallback models
            PLANFORGE_OPENROUTER_MAX_RETRIES: Maximum retry attempts for transient errors (default: 3)
            PLANFORGE_OPENROUTER_RETRY_DELAY: Base retry delay in seconds for exponential backoff (default: 1.0)
            PLANFORGE_OPENROUTER_ALLOW_FALLBACKS: Whether OpenRouter provider fallbacks are allowed (default: True)
            PLANFORGE_HF_BASE_URL: Base URL for Hugging Face Inference API
            PLANFORGE_HF_API_KEY / HF_TOKEN: Hugging Face API key
            PLANFORGE_LLM_TEMPERATURE: Sampling temperature
            PLANFORGE_LLM_TIMEOUT: Request timeout in seconds
            PLANFORGE_LLM_MAX_TOKENS: Max tokens to generate
        """
        load_dotenv_file()
        provider = os.getenv("PLANFORGE_LLM_PROVIDER", "google").strip().lower()

        # Determine model, base_url, timeout, and api_key based on provider
        if provider in ("google", "gemini"):
            default_model = "gemini-flash-latest"
            default_base_url = "https://generativelanguage.googleapis.com"
            default_timeout = 120.0
            api_key = (
                os.getenv("PLANFORGE_GOOGLE_API_KEY")
                or os.getenv("GEMINI_API_KEY")
                or os.getenv("GOOGLE_API_KEY")
                or os.getenv("PLANFORGE_LLM_API_KEY")
            )
        elif provider in ("openrouter", "or"):
            default_model = "meta-llama/llama-3.3-70b-instruct"
            default_base_url = os.getenv(
                "PLANFORGE_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions"
            ).strip()
            default_timeout = 120.0
            api_key = (
                os.getenv("PLANFORGE_OPENROUTER_API_KEY")
                or os.getenv("OPENROUTER_API_KEY")
                or os.getenv("PLANFORGE_LLM_API_KEY")
            )
        elif provider in ("huggingface", "hf"):
            default_model = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
            default_base_url = os.getenv("PLANFORGE_HF_BASE_URL", "https://api-inference.huggingface.co/models").strip()
            default_timeout = 120.0
            api_key = (
                os.getenv("PLANFORGE_HF_API_KEY")
                or os.getenv("HF_TOKEN")
                or os.getenv("PLANFORGE_LLM_API_KEY")
            )
        else:
            default_model = "gemini-flash-latest"
            default_base_url = "https://generativelanguage.googleapis.com"
            default_timeout = 60.0
            api_key = os.getenv("PLANFORGE_LLM_API_KEY")

        model_name = (
            os.getenv("PLANFORGE_LLM_MODEL")
            or (os.getenv("GOOGLE_MODEL") if provider in ("google", "gemini") else None)
            or (os.getenv("GEMINI_MODEL") if provider in ("google", "gemini") else None)
            or default_model
        ).strip()

        if provider in ("google", "gemini"):
            for prefix in ("google-gla:", "google-vertex:", "google:"):
                if model_name.startswith(prefix):
                    model_name = model_name[len(prefix):]
                    break
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

        http_referer = os.getenv("PLANFORGE_OPENROUTER_HTTP_REFERER") or os.getenv("HTTP_REFERER")
        app_title = os.getenv("PLANFORGE_OPENROUTER_TITLE") or "PlanForge AI"

        # Fallback models configuration
        if provider in ("google", "gemini"):
            fb_env = os.getenv("PLANFORGE_FALLBACK_MODELS") or os.getenv("PLANFORGE_GOOGLE_FALLBACK_MODELS")
            if fb_env is not None:
                fallback_models = [m.strip() for m in fb_env.split(",") if m.strip()]
            else:
                fallback_models = [
                    "gemini-3.8-flash",
                    "gemini-3.5-flash",
                    "gemini-2.5-flash-lite",
                ]
        elif provider in ("openrouter", "or"):
            fb_env = os.getenv("PLANFORGE_FALLBACK_MODELS") or os.getenv("PLANFORGE_OPENROUTER_FALLBACK_MODELS")
            if fb_env is not None:
                fallback_models = [m.strip() for m in fb_env.split(",") if m.strip()]
            else:
                fallback_models = [
                    "nvidia/nemotron-3.5-lightning:free",
                    "liquid/lfm-2.5-2.6b:free",
                ]
        else:
            fb_env = os.getenv("PLANFORGE_FALLBACK_MODELS")
            if fb_env is not None:
                fallback_models = [m.strip() for m in fb_env.split(",") if m.strip()]
            else:
                fallback_models = []

        fb_provider_env = os.getenv("PLANFORGE_FALLBACK_PROVIDER")
        fallback_provider = fb_provider_env.strip().lower() if fb_provider_env else None

        try:
            max_retries = int(os.getenv("PLANFORGE_LLM_MAX_RETRIES") or os.getenv("PLANFORGE_OPENROUTER_MAX_RETRIES", "3"))
        except ValueError:
            max_retries = 3

        try:
            retry_delay = float(os.getenv("PLANFORGE_LLM_RETRY_DELAY") or os.getenv("PLANFORGE_OPENROUTER_RETRY_DELAY", "1.0"))
        except ValueError:
            retry_delay = 1.0

        allow_fb_env = os.getenv("PLANFORGE_ALLOW_FALLBACKS") or os.getenv("PLANFORGE_OPENROUTER_ALLOW_FALLBACKS", "true")
        allow_provider_fallbacks = allow_fb_env.strip().lower() in ("true", "1", "yes")

        return cls(
            provider=provider,
            model_name=model_name,
            temperature=temp,
            max_tokens=max_tokens,
            timeout_seconds=timeout,
            api_base_url=base_url,
            api_key=api_key,
            http_referer=http_referer,
            app_title=app_title,
            fallback_models=fallback_models,
            fallback_provider=fallback_provider,
            max_retries=max_retries,
            retry_delay=retry_delay,
            allow_provider_fallbacks=allow_provider_fallbacks,
        )


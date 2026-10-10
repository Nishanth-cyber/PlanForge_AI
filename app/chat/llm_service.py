"""Conversational LLM service: the single place where chat messages reach the LLM.

Guarantees
----------
* Reuses the existing LLM abstraction (``app.llm``): ``create_llm_client`` /
  ``LLMConfig.from_env`` / ``LLMClient.generate`` -- no second LLM system.
* NEVER silently substitutes ``MockLLMClient``. If the configured provider is not
  a real provider, or the real provider fails, a structured error is returned
  with ``ok=False`` so the caller reports ``llm_used = false``.
* ``MockLLMClient`` (or any fake) can still be used for tests by *explicitly*
  injecting a client.
* Never leaks API keys, stack traces or environment values to the user or logs.
* Emits one structured log record per call (turn id, project id, stage,
  provider, model, success, latency, timestamp). User message text is not logged.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from app.llm.client import HuggingFaceError, HuggingFaceTimeoutError, LLMClient
from app.llm.configuration import LLMConfig
from app.llm.factory import create_llm_client

logger = logging.getLogger("planforge.chat")

STATUS_SUCCESS = "SUCCESS"
STATUS_UNAVAILABLE = "LLM_UNAVAILABLE"
STATUS_TIMEOUT = "LLM_TIMEOUT"
STATUS_NOT_CONFIGURED = "LLM_NOT_CONFIGURED"
STATUS_EMPTY = "LLM_EMPTY_RESPONSE"

_REAL_PROVIDERS = ("huggingface", "hf")

MSG_UNAVAILABLE = (
    "I couldn't reach the configured AI model right now. "
    "Please check the LLM provider configuration."
)
MSG_TIMEOUT = "The configured AI model took too long to respond. Please try again in a moment."
MSG_EMPTY = "The AI model returned an empty response. Please try again."

_SECRET_RE = re.compile(r"(hf_[A-Za-z0-9]{6,}|Bearer\s+[A-Za-z0-9._\-]+|api[_-]?key\s*[=:]\s*\S+)", re.I)
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)


def redact(text: object) -> str:
    """Mask anything that looks like a credential."""
    return _SECRET_RE.sub("[REDACTED]", str(text))


def clean_llm_text(raw: object) -> str:
    """Strip reasoning traces (<think>...</think>) so they are never shown to the user."""
    text = _THINK_BLOCK_RE.sub("", str(raw or ""))
    lowered = text.lower()
    if "<think>" in lowered:  # unterminated reasoning (truncated output) is unusable
        text = text[: lowered.index("<think>")]
    return text.replace("</think>", "").strip()


@dataclass
class LLMChatResult:
    """Outcome of one conversational LLM call."""

    ok: bool
    text: str = ""
    status: str = STATUS_SUCCESS
    user_message: str = ""
    provider: Optional[str] = None
    model: Optional[str] = None
    latency_ms: Optional[int] = None


class ConversationalLLMService:
    """Sends conversational prompts to the configured LLM and normalises the outcome."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config_loader: Optional[Callable[[], LLMConfig]] = None,
        client_factory: Optional[Callable[[LLMConfig], LLMClient]] = None,
    ) -> None:
        """
        Args:
            llm_client: Explicitly injected client (tests / explicit dev mode only).
            config_loader: Returns the LLMConfig; defaults to ``LLMConfig.from_env``.
            client_factory: Builds a client from config; defaults to ``create_llm_client``.
        """
        self._client = llm_client
        self._config_loader = config_loader or LLMConfig.from_env
        self._client_factory = client_factory or create_llm_client

    # ------------------------------------------------------------------
    def generate_reply(
        self,
        *,
        prompt: str,
        system_prompt: str,
        turn_id: str,
        project_id: Optional[str] = None,
        intent: str = "conversation",
    ) -> LLMChatResult:
        """Call the configured LLM with the prompt and return a normalised result."""
        started = time.perf_counter()
        cfg = self._config_loader()
        provider, model = cfg.provider, cfg.model_name

        # 1. Resolve the client. Never fall back to a mock when a real provider is expected.
        if self._client is not None:
            client = self._client
        else:
            if cfg.provider not in _REAL_PROVIDERS:
                return self._finish(
                    started, turn_id, project_id, intent, provider, model,
                    ok=False, status=STATUS_NOT_CONFIGURED,
                    user_message=(
                        f"The conversational AI is not enabled: PLANFORGE_LLM_PROVIDER is set to '{cfg.provider}'. "
                        "Set it to 'huggingface' (with a valid PLANFORGE_HF_API_KEY) to enable AI answers."
                    ),
                )
            try:
                client = self._client_factory(cfg)
            except Exception as exc:  # configuration/construction failure
                return self._finish(
                    started, turn_id, project_id, intent, provider, model,
                    ok=False, status=STATUS_UNAVAILABLE, user_message=MSG_UNAVAILABLE, error=exc,
                )

        # 2. The actual, observable LLM invocation.
        try:
            raw = client.generate(prompt=prompt, system_prompt=system_prompt)
        except HuggingFaceTimeoutError as exc:
            provider, model = self._labels(client, provider, model)
            return self._finish(
                started, turn_id, project_id, intent, provider, model,
                ok=False, status=STATUS_TIMEOUT, user_message=MSG_TIMEOUT, error=exc,
            )
        except (HuggingFaceError, Exception) as exc:  # noqa: BLE001 - any provider failure is non-fatal
            provider, model = self._labels(client, provider, model)
            return self._finish(
                started, turn_id, project_id, intent, provider, model,
                ok=False, status=STATUS_UNAVAILABLE, user_message=MSG_UNAVAILABLE, error=exc,
            )

        provider, model = self._labels(client, provider, model)
        text = clean_llm_text(raw)
        if not text:
            return self._finish(
                started, turn_id, project_id, intent, provider, model,
                ok=False, status=STATUS_EMPTY, user_message=MSG_EMPTY,
            )
        return self._finish(started, turn_id, project_id, intent, provider, model, ok=True, text=text)

    # ------------------------------------------------------------------
    def _labels(self, client: object, provider: str, model: str) -> tuple[str, str]:
        """Prefer the client's own factual runtime metadata over configuration values."""
        meta = getattr(client, "last_metadata", None) or {}
        if self._client is not None:
            provider = str(meta.get("provider") or type(client).__name__)
            model = str(meta.get("model") or "unknown")
        else:
            provider = str(meta.get("provider") or provider)
            model = str(meta.get("model") or model)
        return provider, model

    def _finish(
        self,
        started: float,
        turn_id: str,
        project_id: Optional[str],
        intent: str,
        provider: Optional[str],
        model: Optional[str],
        *,
        ok: bool,
        text: str = "",
        status: str = STATUS_SUCCESS,
        user_message: str = "",
        error: Optional[BaseException] = None,
    ) -> LLMChatResult:
        latency_ms = int((time.perf_counter() - started) * 1000)
        record = {
            "turn_id": turn_id,
            "project_id": project_id,
            "stage": "conversational_chat",
            "intent": intent,
            "provider": provider,
            "model": model,
            "success": ok,
            "status": status,
            "latency_ms": latency_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if error is not None:
            record["error_type"] = type(error).__name__
            record["error_detail"] = redact(error)[:200]
        (logger.info if ok else logger.warning)("conversational_llm_call %s", json.dumps(record, default=str))
        return LLMChatResult(
            ok=ok,
            text=text,
            status=status,
            user_message=user_message,
            provider=provider,
            model=model,
            latency_ms=latency_ms,
        )

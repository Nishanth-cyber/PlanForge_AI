"""LLM client abstraction and implementations for PlanForge AI."""

from __future__ import annotations
import json
import urllib.request
import urllib.error
import time
from typing import Any, Callable, Optional, Protocol
from app.llm.configuration import LLMConfig


class HuggingFaceError(RuntimeError):
    """Base exception for Hugging Face provider failures."""
    pass


class HuggingFaceConnectionError(HuggingFaceError):
    """Raised when network connection to Hugging Face API fails."""
    pass


class HuggingFaceTimeoutError(HuggingFaceError):
    """Raised when a Hugging Face API request times out."""
    pass


class HuggingFaceAPIError(HuggingFaceError):
    """Raised when Hugging Face API returns an HTTP error code or message."""
    pass


class LLMClient(Protocol):
    """Protocol defining the interface for LLM client implementations."""

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate a response text from the given prompt.

        Args:
            prompt: User/context prompt string.
            system_prompt: Optional system instruction prompt.

        Returns:
            Generated response string.
        """
        ...


class MockLLMClient:
    """Deterministic mock LLM client for testing without external service dependencies."""

    def __init__(
        self,
        default_response: Optional[str] = None,
        responses: Optional[list[str]] = None,
        response_map: Optional[dict[str, str]] = None,
        generator: Optional[Callable[[str, Optional[str]], str]] = None,
    ):
        """Initialize MockLLMClient.

        Args:
            default_response: Single fixed response string.
            responses: Sequential list of responses to return on consecutive calls.
            response_map: Dict mapping substring keywords in prompt to specific responses.
            generator: Callable receiving (prompt, system_prompt) and returning a string.
        """
        self.default_response = default_response or "{}"
        self.responses = list(responses) if responses else []
        self.response_map = response_map or {}
        self.generator = generator
        self.history: list[tuple[str, Optional[str]]] = []
        self.call_count: int = 0
        self.last_metadata: dict[str, Any] = {
            "provider": "mock",
            "model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
            "success": True,
        }

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate response from mock source."""
        self.history.append((prompt, system_prompt))
        self.call_count += 1

        if self.generator:
            res = self.generator(prompt, system_prompt)
            self.last_metadata = {
                "provider": "mock",
                "model": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                "success": True,
                "generator": "deterministic_mock_generator",
            }
            return res

        # Check response map
        for key, resp in self.response_map.items():
            if key in prompt:
                return resp

        # Check sequential responses
        if self.responses:
            return self.responses.pop(0)

        return self.default_response

    def set_default_response(self, response: str) -> None:
        """Update default response."""
        self.default_response = response

    def reset(self) -> None:
        """Reset call history and count."""
        self.history.clear()
        self.call_count = 0


class HuggingFaceClient:
    """Client for Hugging Face Serverless Inference API via REST.

    Allows utilizing free hosted open models (e.g. deepseek-ai/DeepSeek-R1-Distill-Qwen-7B,
    deepseek-ai/DeepSeek-V3, Qwen/Qwen2.5-7B-Instruct) over standard HTTP without additional dependencies.

    Supports both:
    1. Standard model inference endpoint: https://api-inference.huggingface.co/models/{model_name}
    2. OpenAI-compatible Router endpoint: https://router.huggingface.co/hf-inference/v1/chat/completions

    Guarantees:
    - Never silently falls back to MockLLMClient.
    - Captures factual execution metadata (timing, endpoint, status).
    - Preserves explicit structured errors.
    - Cleanly strips DeepSeek <think>...</think> reasoning traces to extract structured JSON.
    """

    DEFAULT_MODEL = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig(provider="huggingface", model_name=self.DEFAULT_MODEL)
        base_url = (self.config.api_base_url or "https://api-inference.huggingface.co/models").rstrip("/")
        if base_url.endswith("/v1") or "/chat/completions" in base_url:
            self.endpoint = base_url
            self.is_chat_completions = True
        else:
            self.endpoint = f"{base_url}/{self.config.model_name}"
            self.is_chat_completions = False
        self.last_metadata: dict[str, Any] = {}

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Send generation request to Hugging Face Inference API.

        Raises:
            HuggingFaceConnectionError: If network connection fails.
            HuggingFaceTimeoutError: If request exceeds timeout.
            HuggingFaceAPIError: If API returns error (including 503 model loading).
        """
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        if self.is_chat_completions:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            payload: dict[str, Any] = {
                "model": self.config.model_name,
                "messages": messages,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            }
        else:
            full_inputs = prompt
            if system_prompt:
                full_inputs = f"System: {system_prompt}\n\nUser: {prompt}\n\nAssistant:"

            payload = {
                "inputs": full_inputs,
                "parameters": {
                    "max_new_tokens": self.config.max_tokens,
                    "temperature": self.config.temperature,
                    "return_full_text": False,
                },
            }

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=req_data,
            headers=headers,
            method="POST",
        )

        start_time = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                status_code = response.getcode()
                raw_body = response.read().decode("utf-8", errors="ignore")
                elapsed = time.time() - start_time

                if status_code != 200:
                    self.last_metadata = {
                        "provider": "huggingface",
                        "model": self.config.model_name,
                        "endpoint": self.endpoint,
                        "elapsed_seconds": round(elapsed, 3),
                        "status": f"http_error_{status_code}",
                        "success": False,
                    }
                    raise HuggingFaceAPIError(f"Hugging Face returned HTTP {status_code}: {raw_body}")

                data = json.loads(raw_body)
                if self.is_chat_completions:
                    choices = data.get("choices", [])
                    if choices and isinstance(choices[0], dict):
                        generated_text = choices[0].get("message", {}).get("content", "")
                    else:
                        generated_text = str(data)
                elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                    generated_text = data[0].get("generated_text", "")
                elif isinstance(data, dict):
                    generated_text = data.get("generated_text", data.get("response", str(data)))
                else:
                    generated_text = str(data)

                # For DeepSeek reasoning models, strip <think>...</think> reasoning traces
                if "</think>" in generated_text:
                    post_think = generated_text.split("</think>", 1)[1].strip()
                    if post_think:
                        generated_text = post_think

                self.last_metadata = {
                    "provider": "huggingface",
                    "model": self.config.model_name,
                    "endpoint": self.endpoint,
                    "elapsed_seconds": round(elapsed, 3),
                    "status": "success",
                    "success": True,
                }
                return generated_text

        except urllib.error.HTTPError as e:
            elapsed = time.time() - start_time
            err_body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            self.last_metadata = {
                "provider": "huggingface",
                "model": self.config.model_name,
                "endpoint": self.endpoint,
                "elapsed_seconds": round(elapsed, 3),
                "status": f"http_error_{e.code}",
                "success": False,
            }
            if e.code == 503:
                raise HuggingFaceAPIError(
                    f"Hugging Face model {self.config.model_name} is loading (HTTP 503): {err_body}"
                ) from e
            raise HuggingFaceAPIError(f"Hugging Face API HTTP {e.code} error: {err_body}") from e

        except TimeoutError as e:
            elapsed = time.time() - start_time
            self.last_metadata = {
                "provider": "huggingface",
                "model": self.config.model_name,
                "endpoint": self.endpoint,
                "elapsed_seconds": round(elapsed, 3),
                "status": "timeout",
                "success": False,
            }
            raise HuggingFaceTimeoutError(
                f"Hugging Face request to {self.endpoint} timed out after {self.config.timeout_seconds}s"
            ) from e

        except urllib.error.URLError as e:
            elapsed = time.time() - start_time
            self.last_metadata = {
                "provider": "huggingface",
                "model": self.config.model_name,
                "endpoint": self.endpoint,
                "elapsed_seconds": round(elapsed, 3),
                "status": "connection_error",
                "success": False,
            }
            if "timed out" in str(e.reason).lower():
                raise HuggingFaceTimeoutError(
                    f"Hugging Face request timed out after {self.config.timeout_seconds}s: {e.reason}"
                ) from e
            raise HuggingFaceConnectionError(
                f"Failed to connect to Hugging Face at {self.endpoint}: {e.reason}"
            ) from e

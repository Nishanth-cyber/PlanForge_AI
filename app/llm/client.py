"""LLM client abstraction and implementations for PlanForge AI."""

from __future__ import annotations
import json
import logging
import urllib.request
import urllib.error
import time
from typing import Any, Callable, Optional, Protocol
from app.llm.configuration import LLMConfig

logger = logging.getLogger(__name__)


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


class OpenRouterError(RuntimeError):
    """Base exception for OpenRouter provider failures."""
    pass


class OpenRouterConnectionError(OpenRouterError):
    """Raised when network connection to OpenRouter API fails."""
    pass


class OpenRouterTimeoutError(OpenRouterError):
    """Raised when an OpenRouter API request times out."""
    pass


class OpenRouterAPIError(OpenRouterError):
    """Raised when OpenRouter API returns an HTTP error code or error message."""
    pass


class OpenRouterAuthError(OpenRouterAPIError):
    """Raised on HTTP 401 or 403 authentication/permission failure."""
    pass


class OpenRouterCreditError(OpenRouterAPIError):
    """Raised on HTTP 402 payment required / insufficient credits."""
    pass


class OpenRouterRateLimitError(OpenRouterAPIError):
    """Raised on HTTP 429 rate limit exceeded."""
    pass


class GoogleGeminiError(RuntimeError):
    """Base exception for Google Gemini provider failures."""
    pass


class GoogleGeminiConnectionError(GoogleGeminiError):
    """Raised when network connection to Gemini API fails."""
    pass


class GoogleGeminiTimeoutError(GoogleGeminiError):
    """Raised when a Gemini API request times out."""
    pass


class GoogleGeminiAPIError(GoogleGeminiError):
    """Raised when Gemini API returns an error."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class GoogleGeminiAuthError(GoogleGeminiAPIError):
    """Raised on invalid API key or authentication failure (HTTP 400/401/403)."""
    pass


class GoogleGeminiQuotaError(GoogleGeminiAPIError):
    """Raised on quota exhaustion (HTTP 429 / RESOURCE_EXHAUSTED)."""
    pass


class GoogleGeminiRateLimitError(GoogleGeminiAPIError):
    """Raised on rate limit exceeded (HTTP 429)."""
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
        if config is None:
            self.config = LLMConfig(
                provider="huggingface",
                model_name=self.DEFAULT_MODEL,
                api_base_url="https://api-inference.huggingface.co/models",
            )
        else:
            self.config = config
            if self.config.provider in ("huggingface", "hf"):
                if self.config.model_name in (
                    "gemini-2.0-flash",
                    "gemini-flash-latest",
                    "gemini-3.8-flash",
                ):
                    self.config.model_name = self.DEFAULT_MODEL
                if self.config.api_base_url in ("https://generativelanguage.googleapis.com", None):
                    self.config.api_base_url = "https://api-inference.huggingface.co/models"
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


def _parse_retry_after(headers: Any) -> Optional[float]:
    """Parse HTTP Retry-After header as delay seconds."""
    if not headers:
        return None
    val = None
    if hasattr(headers, "get"):
        val = headers.get("Retry-After") or headers.get("retry-after")
    elif isinstance(headers, dict):
        val = headers.get("Retry-After") or headers.get("retry-after")
    if not val:
        return None
    val_str = str(val).strip()
    try:
        parsed = float(val_str)
        if parsed >= 0:
            return parsed
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(val_str)
        diff = dt.timestamp() - time.time()
        return max(0.0, diff)
    except Exception:
        return None


def _calculate_backoff(attempt: int, base_delay: float, retry_after: Optional[float], remaining_time: float) -> float:
    """Calculate bounded backoff delay in seconds."""
    if retry_after is not None and retry_after >= 0:
        delay = retry_after
    else:
        delay = base_delay * (2 ** attempt)
    # Clamp delay: maximum 30 seconds backoff, keeping within remaining timeout
    max_delay = min(30.0, max(0.0, remaining_time - 0.5))
    return max(0.0, min(delay, max_delay))


class OpenRouterClient:
    """Client for OpenRouter API (OpenAI-compatible chat completions).

    Allows utilizing any hosted model on OpenRouter (e.g. meta-llama/llama-3.3-70b-instruct,
    deepseek/deepseek-chat, google/gemini-2.0-flash-001) over standard HTTP without extra dependencies.

    Guarantees:
    - Never silently falls back to MockLLMClient.
    - Captures factual execution metadata (timing, endpoint, status, finish_reason).
    - Preserves explicit structured errors (Auth, Credits, RateLimit, Server).
    - Bounded exponential-backoff retries for retryable HTTP 429 and transient 5xx errors.
    - Respects Retry-After header when available.
    - Never retries non-retryable 4xx errors (401, 402, 403, 400).
    - Supports configurable fallback models and provider routing.
    - Logs which model/provider actually succeeds.
    - Strips DeepSeek <think>...</think> reasoning traces to extract clean structured output.
    - Supports OpenRouter attribution headers (HTTP-Referer, X-Title).
    """

    DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig(provider="openrouter", model_name=self.DEFAULT_MODEL)
        self.endpoint = (self.config.api_base_url or self.DEFAULT_BASE_URL).strip()
        self.last_metadata: dict[str, Any] = {}

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Send chat generation request to OpenRouter API with backoff retry and fallback.

        Raises:
            OpenRouterAuthError: If API key is missing or invalid (HTTP 401/403).
            OpenRouterCreditError: If account credits are exhausted (HTTP 402).
            OpenRouterRateLimitError: If rate limit is exceeded (HTTP 429) after retries.
            OpenRouterAPIError: If API returns HTTP error or error payload.
            OpenRouterTimeoutError: If request exceeds timeout.
            OpenRouterConnectionError: If network connection fails after retries.
        """
        api_key = (self.config.api_key or "").strip()
        if not api_key:
            raise OpenRouterAuthError(
                "OpenRouter API key is missing. Set PLANFORGE_OPENROUTER_API_KEY in your environment."
            )

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        if getattr(self.config, "http_referer", None):
            headers["HTTP-Referer"] = self.config.http_referer
        if getattr(self.config, "app_title", None):
            headers["X-Title"] = self.config.app_title

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Prepare models to attempt (primary + configurable fallbacks)
        primary_model = self.config.model_name
        fallback_models = [m for m in getattr(self.config, "fallback_models", []) if m and m != primary_model]
        models_to_try = [primary_model] + fallback_models

        max_retries = max(0, getattr(self.config, "max_retries", 3))
        base_delay = getattr(self.config, "retry_delay", 1.0)
        timeout_seconds = self.config.timeout_seconds
        allow_fallbacks = getattr(self.config, "allow_provider_fallbacks", True)

        start_time = time.time()
        total_attempts = 0
        last_error: Optional[Exception] = None

        for model_idx, candidate_model in enumerate(models_to_try):
            for retry_idx in range(max_retries + 1):
                total_attempts += 1
                elapsed = time.time() - start_time
                remaining = timeout_seconds - elapsed
                if remaining <= 0.2:
                    self.last_metadata = {
                        "provider": "openrouter",
                        "model": self.config.model_name,
                        "endpoint": self.endpoint,
                        "elapsed_seconds": round(elapsed, 3),
                        "attempts": total_attempts,
                        "status": "timeout",
                        "success": False,
                    }
                    raise OpenRouterTimeoutError(
                        f"OpenRouter request timed out after {timeout_seconds}s across {total_attempts} attempts."
                    )

                # Build payload
                payload: dict[str, Any] = {
                    "model": candidate_model,
                    "messages": messages,
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens,
                }
                # If fallbacks are allowed and more models remain, pass models array for server-side fallback
                if allow_fallbacks and len(models_to_try) > 1:
                    remaining_models = [candidate_model] + [m for m in models_to_try if m != candidate_model]
                    payload["models"] = remaining_models[:3]  # OpenRouter requires <= 3 items
                    payload["provider"] = {"allow_fallbacks": True}
                    payload["route"] = "fallback"

                req_data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    self.endpoint,
                    data=req_data,
                    headers=headers,
                    method="POST",
                )

                try:
                    with urllib.request.urlopen(req, timeout=min(remaining, timeout_seconds)) as response:
                        status_code = response.getcode()
                        raw_body = response.read().decode("utf-8", errors="ignore")
                        call_elapsed = time.time() - start_time

                        if status_code != 200:
                            raise OpenRouterAPIError(f"OpenRouter returned HTTP {status_code}: {raw_body}")

                        data = json.loads(raw_body)
                        if "error" in data:
                            err_info = data["error"]
                            err_msg = err_info.get("message", str(err_info)) if isinstance(err_info, dict) else str(err_info)
                            err_code = err_info.get("code") if isinstance(err_info, dict) else None
                            if err_code == 429:
                                raise urllib.error.HTTPError(
                                    url=self.endpoint,
                                    code=429,
                                    msg=err_msg,
                                    hdrs=response.headers,
                                    fp=None,
                                )
                            raise OpenRouterAPIError(f"OpenRouter error payload: {err_msg}")

                        choices = data.get("choices", [])
                        if not choices or not isinstance(choices[0], dict):
                            raise OpenRouterAPIError("OpenRouter returned response with empty or invalid choices.")

                        first_choice = choices[0]
                        generated_text = first_choice.get("message", {}).get("content", "")
                        finish_reason = first_choice.get("finish_reason", "stop")

                        # Strip reasoning traces (<think>...</think>) if present
                        if "</think>" in generated_text:
                            post_think = generated_text.split("</think>", 1)[1].strip()
                            if post_think:
                                generated_text = post_think

                        # Identify which model actually responded (OpenRouter returns "model" in response)
                        actual_model = data.get("model") or candidate_model
                        fallback_used = (actual_model != self.config.model_name)
                        if fallback_used:
                            logger.info(
                                "OpenRouter generation succeeded using fallback model '%s' (requested: '%s', attempt=%d)",
                                actual_model, self.config.model_name, total_attempts
                            )
                        else:
                            logger.info(
                                "OpenRouter generation succeeded using model '%s' (attempt=%d)",
                                actual_model, total_attempts
                            )

                        self.last_metadata = {
                            "provider": "openrouter",
                            "model": actual_model,
                            "model_requested": self.config.model_name,
                            "fallback_used": fallback_used,
                            "endpoint": self.endpoint,
                            "elapsed_seconds": round(call_elapsed, 3),
                            "attempts": total_attempts,
                            "status": "success",
                            "success": True,
                            "finish_reason": finish_reason,
                            "usage": data.get("usage", {}),
                        }
                        return generated_text

                except urllib.error.HTTPError as e:
                    call_elapsed = time.time() - start_time
                    err_body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)

                    # 1. Non-retryable: 401, 403 (Authentication / Forbidden)
                    if e.code in (401, 403):
                        self.last_metadata = {
                            "provider": "openrouter",
                            "model": candidate_model,
                            "endpoint": self.endpoint,
                            "elapsed_seconds": round(call_elapsed, 3),
                            "attempts": total_attempts,
                            "status": f"http_error_{e.code}",
                            "success": False,
                        }
                        raise OpenRouterAuthError(
                            f"OpenRouter authentication failed (HTTP {e.code}): {err_body}"
                        ) from e

                    # 2. Non-retryable: 402 (Payment / Credits exhausted)
                    if e.code == 402:
                        self.last_metadata = {
                            "provider": "openrouter",
                            "model": candidate_model,
                            "endpoint": self.endpoint,
                            "elapsed_seconds": round(call_elapsed, 3),
                            "attempts": total_attempts,
                            "status": "http_error_402",
                            "success": False,
                        }
                        raise OpenRouterCreditError(
                            f"OpenRouter account credits exhausted or payment required (HTTP 402): {err_body}"
                        ) from e

                    # 3. Non-retryable other 4xx (e.g. 400 Bad Request, 404 Not Found)
                    if e.code != 429 and 400 <= e.code < 500:
                        self.last_metadata = {
                            "provider": "openrouter",
                            "model": candidate_model,
                            "endpoint": self.endpoint,
                            "elapsed_seconds": round(call_elapsed, 3),
                            "attempts": total_attempts,
                            "status": f"http_error_{e.code}",
                            "success": False,
                        }
                        raise OpenRouterAPIError(
                            f"OpenRouter API HTTP {e.code} error: {err_body}"
                        ) from e

                    # 4. Retryable: HTTP 429 or 5xx (500, 502, 503, 504)
                    last_error = e
                    remaining = timeout_seconds - (time.time() - start_time)
                    if retry_idx < max_retries and remaining > 0.5:
                        retry_after = _parse_retry_after(getattr(e, "headers", None))
                        delay = _calculate_backoff(retry_idx, base_delay, retry_after, remaining)
                        logger.warning(
                            "OpenRouter HTTP %d on model '%s' (attempt %d). Retrying in %.2fs...",
                            e.code, candidate_model, total_attempts, delay
                        )
                        time.sleep(delay)
                        continue
                    else:
                        # Retries on candidate_model exhausted. Check if another fallback model is available.
                        if model_idx + 1 < len(models_to_try):
                            next_model = models_to_try[model_idx + 1]
                            logger.warning(
                                "OpenRouter retries exhausted on model '%s' (HTTP %d). Trying fallback model '%s'...",
                                candidate_model, e.code, next_model
                            )
                            break  # Exit inner retry loop to try next candidate_model in outer loop
                        else:
                            # All models and retries exhausted
                            self.last_metadata = {
                                "provider": "openrouter",
                                "model": candidate_model,
                                "endpoint": self.endpoint,
                                "elapsed_seconds": round(call_elapsed, 3),
                                "attempts": total_attempts,
                                "status": "rate_limited" if e.code == 429 else f"http_error_{e.code}",
                                "success": False,
                            }
                            if e.code == 429:
                                raise OpenRouterRateLimitError(
                                    f"OpenRouter rate limit exceeded (HTTP 429) after {total_attempts} attempts: {err_body}"
                                ) from e
                            raise OpenRouterAPIError(
                                f"OpenRouter server error (HTTP {e.code}) after {total_attempts} attempts: {err_body}"
                            ) from e

                except TimeoutError as e:
                    call_elapsed = time.time() - start_time
                    last_error = e
                    remaining = timeout_seconds - (time.time() - start_time)
                    if retry_idx < max_retries and remaining > 0.5:
                        delay = _calculate_backoff(retry_idx, base_delay, None, remaining)
                        time.sleep(delay)
                        continue
                    elif model_idx + 1 < len(models_to_try):
                        break
                    else:
                        self.last_metadata = {
                            "provider": "openrouter",
                            "model": candidate_model,
                            "endpoint": self.endpoint,
                            "elapsed_seconds": round(call_elapsed, 3),
                            "attempts": total_attempts,
                            "status": "timeout",
                            "success": False,
                        }
                        raise OpenRouterTimeoutError(
                            f"OpenRouter request timed out after {timeout_seconds}s ({total_attempts} attempts)"
                        ) from e

                except urllib.error.URLError as e:
                    call_elapsed = time.time() - start_time
                    last_error = e
                    remaining = timeout_seconds - (time.time() - start_time)
                    if "timed out" in str(e.reason).lower():
                        if retry_idx < max_retries and remaining > 0.5:
                            delay = _calculate_backoff(retry_idx, base_delay, None, remaining)
                            time.sleep(delay)
                            continue
                        elif model_idx + 1 < len(models_to_try):
                            break
                        else:
                            self.last_metadata = {
                                "provider": "openrouter",
                                "model": candidate_model,
                                "endpoint": self.endpoint,
                                "elapsed_seconds": round(call_elapsed, 3),
                                "attempts": total_attempts,
                                "status": "timeout",
                                "success": False,
                            }
                            raise OpenRouterTimeoutError(
                                f"OpenRouter request timed out after {timeout_seconds}s: {e.reason}"
                            ) from e

                    if retry_idx < max_retries and remaining > 0.5:
                        delay = _calculate_backoff(retry_idx, base_delay, None, remaining)
                        time.sleep(delay)
                        continue
                    elif model_idx + 1 < len(models_to_try):
                        break
                    else:
                        self.last_metadata = {
                            "provider": "openrouter",
                            "model": candidate_model,
                            "endpoint": self.endpoint,
                            "elapsed_seconds": round(call_elapsed, 3),
                            "attempts": total_attempts,
                            "status": "connection_error",
                            "success": False,
                        }
                        raise OpenRouterConnectionError(
                            f"Failed to connect to OpenRouter at {self.endpoint}: {e.reason}"
                        ) from e

        if last_error:
            raise last_error
        raise OpenRouterAPIError("OpenRouter request failed: exhausted all attempts without response.")


class GoogleGeminiClient:
    """Client for Google Gemini API via official google-genai SDK.

    Allows utilizing Google Gemini models (e.g. gemini-2.0-flash, gemini-1.5-flash)
    for high-speed architectural reasoning, requirements interpretation, and structured output.

    Guarantees:
    - Never silently falls back to MockLLMClient.
    - Captures factual execution metadata (timing, endpoint, status, finish_reason).
    - Preserves explicit structured errors (Auth, Quota, RateLimit, Server).
    - Bounded exponential-backoff retries for transient 429 and 5xx errors.
    - Never retries non-retryable 4xx errors (authentication failures, invalid model IDs).
    - Supports configurable fallback models and optional fallback client/provider (e.g. OpenRouter).
    - Strips DeepSeek/Gemini <think>...</think> reasoning traces for clean structured output.
    """

    DEFAULT_MODEL = "gemini-flash-latest"

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        fallback_client: Optional[LLMClient] = None,
    ):
        self.config = config or LLMConfig(provider="google", model_name=self.DEFAULT_MODEL)
        self.endpoint = "https://generativelanguage.googleapis.com"
        self.base_url = "https://generativelanguage.googleapis.com"
        self.last_metadata: dict[str, Any] = {}
        self.fallback_client = fallback_client
        self._genai_client = None

    def _get_client(self, api_key: str):
        if self._genai_client is None:
            try:
                from google import genai
                from google.genai import types
                timeout_ms = int(self.config.timeout_seconds * 1000)
                http_opts = types.HttpOptions(timeout=timeout_ms)
                self._genai_client = genai.Client(api_key=api_key, http_options=http_opts)
            except ImportError as e:
                raise GoogleGeminiAPIError(
                    "The 'google-genai' library is required to use the Google provider. "
                    "Install it via 'pip install google-genai'."
                ) from e
        return self._genai_client

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Send chat generation request to Google Gemini API with backoff retry and fallback.

        Raises:
            GoogleGeminiAuthError: If API key is missing or invalid (HTTP 400/401/403).
            GoogleGeminiQuotaError: If quota is exhausted (HTTP 429 / RESOURCE_EXHAUSTED).
            GoogleGeminiRateLimitError: If rate limit is exceeded (HTTP 429).
            GoogleGeminiAPIError: If API returns error payload or invalid response.
            GoogleGeminiTimeoutError: If request exceeds timeout.
            GoogleGeminiConnectionError: If network connection fails after retries.
        """
        api_key = (self.config.api_key or "").strip()
        if not api_key:
            raise GoogleGeminiAuthError(
                "Google Gemini API key is missing. Set PLANFORGE_GOOGLE_API_KEY in your environment."
            )

        client = self._get_client(api_key)
        from google.genai import types
        from google.genai import errors as genai_errors

        primary_model = self.config.model_name
        fallback_models = [m for m in getattr(self.config, "fallback_models", []) if m and m != primary_model]
        models_to_try = [primary_model] + fallback_models

        max_retries = max(0, getattr(self.config, "max_retries", 3))
        base_delay = getattr(self.config, "retry_delay", 1.0)
        timeout_seconds = self.config.timeout_seconds

        start_time = time.time()
        total_attempts = 0
        last_error: Optional[Exception] = None

        config = types.GenerateContentConfig(
            system_instruction=system_prompt if system_prompt else None,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_tokens,
        )

        for model_idx, candidate_model in enumerate(models_to_try):
            for retry_idx in range(max_retries + 1):
                total_attempts += 1
                elapsed = time.time() - start_time
                remaining = timeout_seconds - elapsed
                if remaining <= 0.2:
                    self.last_metadata = {
                        "provider": "google",
                        "model": self.config.model_name,
                        "elapsed_seconds": round(elapsed, 3),
                        "attempts": total_attempts,
                        "status": "timeout",
                        "success": False,
                    }
                    raise GoogleGeminiTimeoutError(
                        f"Google Gemini request timed out after {timeout_seconds}s across {total_attempts} attempts."
                    )

                clean_model = candidate_model
                for prefix in ("google-gla:", "google-vertex:", "google:"):
                    if clean_model.startswith(prefix):
                        clean_model = clean_model[len(prefix):]
                        break

                try:
                    response = client.models.generate_content(
                        model=clean_model,
                        contents=prompt,
                        config=config,
                    )
                    call_elapsed = time.time() - start_time

                    text = getattr(response, "text", None) or ""
                    candidates = getattr(response, "candidates", None) or []
                    finish_reason = "stop"
                    if candidates:
                        raw_fr = getattr(candidates[0], "finish_reason", None)
                        finish_reason = str(raw_fr.name if hasattr(raw_fr, "name") else raw_fr or "stop")

                    if not text.strip():
                        if finish_reason not in ("stop", "STOP"):
                            raise GoogleGeminiAPIError(
                                f"Google Gemini content generation blocked or incomplete (finish_reason: {finish_reason})."
                            )
                        raise GoogleGeminiAPIError("Google Gemini returned empty response.")

                    # Strip any reasoning traces (<think>...</think>)
                    if "</think>" in text:
                        post_think = text.split("</think>", 1)[1].strip()
                        if post_think:
                            text = post_think

                    usage = {}
                    usage_meta = getattr(response, "usage_metadata", None)
                    if usage_meta:
                        usage = {
                            "prompt_tokens": getattr(usage_meta, "prompt_token_count", None),
                            "completion_tokens": getattr(usage_meta, "candidates_token_count", None),
                            "total_tokens": getattr(usage_meta, "total_token_count", None),
                        }

                    fallback_used = (candidate_model != self.config.model_name)
                    if fallback_used:
                        logger.info(
                            "Google Gemini generation succeeded using fallback model '%s' (requested: '%s', attempt=%d)",
                            candidate_model, self.config.model_name, total_attempts
                        )
                    else:
                        logger.info(
                            "Google Gemini generation succeeded using model '%s' (attempt=%d)",
                            candidate_model, total_attempts
                        )

                    self.last_metadata = {
                        "provider": "google",
                        "model": candidate_model,
                        "model_requested": self.config.model_name,
                        "fallback_used": fallback_used,
                        "elapsed_seconds": round(call_elapsed, 3),
                        "latency_ms": int(call_elapsed * 1000),
                        "attempts": total_attempts,
                        "status": "success",
                        "success": True,
                        "finish_reason": finish_reason,
                        "usage": usage,
                    }
                    return text

                except genai_errors.APIError as e:
                    call_elapsed = time.time() - start_time
                    err_msg = getattr(e, "message", str(e))
                    code = getattr(e, "code", None)

                    # 1. Non-retryable authentication / permission failures
                    if code in (400, 401, 403) and (
                        "API key" in err_msg
                        or "PERMISSION_DENIED" in err_msg
                        or "UNAUTHENTICATED" in err_msg
                        or "not valid" in err_msg.lower()
                    ):
                        self.last_metadata = {
                            "provider": "google",
                            "model": candidate_model,
                            "elapsed_seconds": round(call_elapsed, 3),
                            "latency_ms": int(call_elapsed * 1000),
                            "attempts": total_attempts,
                            "status": f"http_error_{code}",
                            "success": False,
                        }
                        raise GoogleGeminiAuthError(
                            f"Google Gemini authentication failed (HTTP {code}): {err_msg}"
                        ) from e

                    # 2. Non-retryable model not found (HTTP 404)
                    if code == 404 or ("NOT_FOUND" in err_msg and "model" in err_msg.lower()):
                        last_error = e
                        if model_idx + 1 < len(models_to_try):
                            next_model = models_to_try[model_idx + 1]
                            logger.warning(
                                "Google Gemini model '%s' not found (HTTP 404). Falling back to '%s'...",
                                candidate_model,
                                next_model,
                            )
                            break
                        self.last_metadata = {
                            "provider": "google",
                            "model": candidate_model,
                            "elapsed_seconds": round(call_elapsed, 3),
                            "latency_ms": int(call_elapsed * 1000),
                            "attempts": total_attempts,
                            "status": "model_not_found",
                            "success": False,
                        }
                        raise GoogleGeminiAPIError(
                            f"Google Gemini model '{candidate_model}' not found (HTTP 404): {err_msg}"
                        ) from e

                    # 3. Retryable quota / rate limits (HTTP 429 / RESOURCE_EXHAUSTED)
                    is_rate_limit = (code == 429 or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower())
                    if is_rate_limit:
                        last_error = e
                        remaining = timeout_seconds - (time.time() - start_time)
                        if retry_idx < max_retries and remaining > 0.5:
                            delay = _calculate_backoff(retry_idx, base_delay, None, remaining)
                            logger.warning(
                                "Google Gemini HTTP 429 / Quota on model '%s' (attempt %d). Retrying in %.2fs...",
                                candidate_model, total_attempts, delay
                            )
                            time.sleep(delay)
                            continue
                        elif model_idx + 1 < len(models_to_try):
                            next_model = models_to_try[model_idx + 1]
                            logger.warning(
                                "Google Gemini retries exhausted on model '%s' (quota/rate-limit). Falling back to '%s'...",
                                candidate_model, next_model
                            )
                            break
                        elif self.fallback_client:
                            logger.warning(
                                "Google Gemini quota exhausted on all models. Routing to configured fallback provider..."
                            )
                            res = self.fallback_client.generate(prompt, system_prompt)
                            fb_meta = getattr(self.fallback_client, "last_metadata", {})
                            self.last_metadata = {
                                "provider": fb_meta.get("provider", "fallback"),
                                "model": fb_meta.get("model", "unknown"),
                                "primary_provider": "google",
                                "fallback_provider_used": True,
                                "status": "success",
                                "success": True,
                                "elapsed_seconds": round(time.time() - start_time, 3),
                                "attempts": total_attempts,
                            }
                            return res
                        else:
                            self.last_metadata = {
                                "provider": "google",
                                "model": candidate_model,
                                "elapsed_seconds": round(call_elapsed, 3),
                                "attempts": total_attempts,
                                "status": "rate_limited",
                                "success": False,
                            }
                            if "quota" in err_msg.lower():
                                raise GoogleGeminiQuotaError(
                                    f"Google Gemini quota exhausted (HTTP 429) after {total_attempts} attempts: {err_msg}"
                                ) from e
                            raise GoogleGeminiRateLimitError(
                                f"Google Gemini rate limit exceeded (HTTP 429) after {total_attempts} attempts: {err_msg}"
                            ) from e

                    # 4. Retryable upstream 5xx errors
                    is_5xx = (code in (500, 502, 503, 504) or isinstance(e, genai_errors.ServerError))
                    if is_5xx:
                        last_error = e
                        remaining = timeout_seconds - (time.time() - start_time)
                        if retry_idx < max_retries and remaining > 0.5:
                            delay = _calculate_backoff(retry_idx, base_delay, None, remaining)
                            logger.warning(
                                "Google Gemini server error HTTP %s (attempt %d). Retrying in %.2fs...",
                                code, total_attempts, delay
                            )
                            time.sleep(delay)
                            continue
                        elif model_idx + 1 < len(models_to_try):
                            break
                        else:
                            self.last_metadata = {
                                "provider": "google",
                                "model": candidate_model,
                                "elapsed_seconds": round(call_elapsed, 3),
                                "attempts": total_attempts,
                                "status": f"http_error_{code}",
                                "success": False,
                            }
                            raise GoogleGeminiAPIError(
                                f"Google Gemini server error (HTTP {code}) after {total_attempts} attempts: {err_msg}"
                            ) from e

                    # Other non-retryable 4xx
                    self.last_metadata = {
                        "provider": "google",
                        "model": candidate_model,
                        "elapsed_seconds": round(call_elapsed, 3),
                        "attempts": total_attempts,
                        "status": f"http_error_{code}",
                        "success": False,
                    }
                    raise GoogleGeminiAPIError(f"Google Gemini API error (HTTP {code}): {err_msg}") from e

                except TimeoutError as e:
                    call_elapsed = time.time() - start_time
                    last_error = e
                    remaining = timeout_seconds - (time.time() - start_time)
                    if retry_idx < max_retries and remaining > 0.5:
                        delay = _calculate_backoff(retry_idx, base_delay, None, remaining)
                        time.sleep(delay)
                        continue
                    elif model_idx + 1 < len(models_to_try):
                        break
                    else:
                        self.last_metadata = {
                            "provider": "google",
                            "model": candidate_model,
                            "elapsed_seconds": round(call_elapsed, 3),
                            "attempts": total_attempts,
                            "status": "timeout",
                            "success": False,
                        }
                        raise GoogleGeminiTimeoutError(
                            f"Google Gemini request timed out after {timeout_seconds}s ({total_attempts} attempts)"
                        ) from e

                except Exception as e:
                    call_elapsed = time.time() - start_time
                    err_str = str(e).lower()
                    last_error = e
                    if "connection" in err_str or "network" in err_str or "timed out" in err_str:
                        remaining = timeout_seconds - (time.time() - start_time)
                        if retry_idx < max_retries and remaining > 0.5:
                            delay = _calculate_backoff(retry_idx, base_delay, None, remaining)
                            time.sleep(delay)
                            continue
                        elif model_idx + 1 < len(models_to_try):
                            break
                        else:
                            self.last_metadata = {
                                "provider": "google",
                                "model": candidate_model,
                                "elapsed_seconds": round(call_elapsed, 3),
                                "attempts": total_attempts,
                                "status": "connection_error",
                                "success": False,
                            }
                            raise GoogleGeminiConnectionError(f"Failed to connect to Google Gemini: {e}") from e
                    raise

        if last_error:
            raise last_error
        raise GoogleGeminiAPIError("Google Gemini request failed: exhausted all attempts without response.")




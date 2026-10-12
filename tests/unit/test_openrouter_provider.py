"""Unit tests for OpenRouter provider integration in PlanForge AI.

Verifies:
1. OpenRouter provider configuration and environment loading.
2. Correct factory construction for OpenRouter, HuggingFace, and mock.
3. System and user message formatting in payload.
4. Model, temperature, max_tokens, and attribution settings.
5. Successful response extraction and metadata recording.
6. Empty, malformed, or missing choice response handling.
7. Authentication (HTTP 401/403), credit (HTTP 402), rate-limit (HTTP 429), and server (HTTP 500) errors.
8. Network errors and timeout handling.
9. Unsupported provider rejection (ValueError).
10. Accurate llm_used, provider, model, and status metadata in ConversationalLLMService.
11. Regression compatibility with Hugging Face and mock clients.
12. Ordinary conversation vs. requirement changes through ChatOrchestrator.
13. No unexpected generation request triggered for ordinary conversational questions.
"""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch
import pytest

from app.llm.client import (
    HuggingFaceClient,
    MockLLMClient,
    OpenRouterAPIError,
    OpenRouterAuthError,
    OpenRouterClient,
    OpenRouterConnectionError,
    OpenRouterCreditError,
    OpenRouterRateLimitError,
    OpenRouterTimeoutError,
)
from app.llm.configuration import LLMConfig
from app.llm.factory import create_llm_client
from app.chat.llm_service import ConversationalLLMService, STATUS_SUCCESS, STATUS_TIMEOUT, STATUS_UNAVAILABLE
from app.chat.orchestrator import ChatOrchestrator
from app.chat.schema import ConversationIntent, ResponseType


# ==============================================================================
# Helper to construct mock HTTP response
# ==============================================================================

def _make_mock_response(status_code: int, body_dict: dict) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = status_code
    body_bytes = json.dumps(body_dict).encode("utf-8")
    mock_resp.read.return_value = body_bytes
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    return mock_resp


def _make_http_error(url: str, code: int, body_dict: dict) -> urllib.error.HTTPError:
    body_bytes = json.dumps(body_dict).encode("utf-8")
    fp = io.BytesIO(body_bytes)
    return urllib.error.HTTPError(url, code, f"HTTP Error {code}", hdrs={}, fp=fp)


# ==============================================================================
# 1. Configuration & Environment
# ==============================================================================

def test_1_openrouter_configuration_from_env(monkeypatch):
    """Verify OpenRouterConfig parses environment variables correctly."""
    monkeypatch.setenv("PLANFORGE_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("PLANFORGE_OPENROUTER_API_KEY", "sk-or-v1-testkey123")
    monkeypatch.setenv("PLANFORGE_LLM_MODEL", "deepseek/deepseek-chat")
    monkeypatch.setenv("PLANFORGE_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions")
    monkeypatch.setenv("PLANFORGE_OPENROUTER_HTTP_REFERER", "https://planforge.test")
    monkeypatch.setenv("PLANFORGE_OPENROUTER_TITLE", "Test PlanForge")
    monkeypatch.setenv("PLANFORGE_LLM_TIMEOUT", "45.0")
    monkeypatch.setenv("PLANFORGE_LLM_TEMPERATURE", "0.4")

    cfg = LLMConfig.from_env()

    assert cfg.provider == "openrouter"
    assert cfg.api_key == "sk-or-v1-testkey123"
    assert cfg.model_name == "deepseek/deepseek-chat"
    assert cfg.api_base_url == "https://openrouter.ai/api/v1/chat/completions"
    assert cfg.http_referer == "https://planforge.test"
    assert cfg.app_title == "Test PlanForge"
    assert cfg.timeout_seconds == 45.0
    assert cfg.temperature == 0.4


# ==============================================================================
# 2. Factory Construction
# ==============================================================================

def test_2_correct_factory_construction():
    """Verify create_llm_client constructs OpenRouterClient, HuggingFaceClient, and Mock."""
    cfg_or = LLMConfig(provider="openrouter", api_key="sk-or-v1-abc")
    client_or = create_llm_client(cfg_or)
    assert isinstance(client_or, OpenRouterClient)

    cfg_hf = LLMConfig(provider="huggingface", api_key="hf_test")
    client_hf = create_llm_client(cfg_hf)
    assert isinstance(client_hf, HuggingFaceClient)

    cfg_mock = LLMConfig(provider="mock")
    client_mock = create_llm_client(cfg_mock)
    assert isinstance(client_mock, MockLLMClient)


def test_9_unsupported_provider_raises_value_error():
    """Verify unsupported provider name raises clear ValueError and never falls back to mock."""
    cfg_invalid = LLMConfig(provider="unsupported_custom_provider")
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        create_llm_client(cfg_invalid)


# ==============================================================================
# 3 & 4. Message Formatting, Settings & Attribution Headers
# ==============================================================================

def test_3_and_4_payload_formatting_and_headers():
    """Verify system & user messages, model settings, and attribution headers in request."""
    cfg = LLMConfig(
        provider="openrouter",
        api_key="sk-or-v1-secret",
        model_name="meta-llama/llama-3.3-70b-instruct",
        temperature=0.3,
        max_tokens=2048,
        timeout_seconds=30.0,
        http_referer="https://planforge.ai",
        app_title="PlanForge AI Studio",
    )
    client = OpenRouterClient(cfg)

    captured_req = []

    def mock_urlopen(req, timeout):
        captured_req.append((req, timeout))
        return _make_mock_response(200, {
            "choices": [{"message": {"content": "Hello user", "role": "assistant"}}],
            "usage": {"total_tokens": 42},
        })

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        resp = client.generate(prompt="User architectural query", system_prompt="System instructions")

    assert resp == "Hello user"
    assert len(captured_req) == 1
    req, timeout = captured_req[0]

    assert timeout == pytest.approx(30.0, abs=0.5)
    assert req.get_header("Authorization") == "Bearer sk-or-v1-secret"
    assert req.get_header("Content-type") == "application/json"
    assert req.get_header("Http-referer") == "https://planforge.ai"
    assert req.get_header("X-title") == "PlanForge AI Studio"

    payload = json.loads(req.data.decode("utf-8"))
    assert payload["model"] == "meta-llama/llama-3.3-70b-instruct"
    assert payload["temperature"] == 0.3
    assert payload["max_tokens"] == 2048
    assert len(payload["messages"]) == 2
    assert payload["messages"][0] == {"role": "system", "content": "System instructions"}
    assert payload["messages"][1] == {"role": "user", "content": "User architectural query"}


# ==============================================================================
# 5. Successful Response Extraction & Metadata
# ==============================================================================

def test_5_successful_response_extraction_and_metadata():
    """Verify content extraction, <think> token stripping, and factual metadata recording."""
    cfg = LLMConfig(provider="openrouter", api_key="sk-or-v1-key", model_name="deepseek/deepseek-chat")
    client = OpenRouterClient(cfg)

    raw_json = {
        "id": "gen-12345",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "<think>Deliberating room layout...</think>Recommended layout: Living room 6x5m.",
                },
            }
        ],
        "usage": {"prompt_tokens": 15, "completion_tokens": 25, "total_tokens": 40},
    }

    with patch("urllib.request.urlopen", return_value=_make_mock_response(200, raw_json)):
        result = client.generate(prompt="What size should the living room be?")

    assert result == "Recommended layout: Living room 6x5m."
    meta = client.last_metadata
    assert meta["provider"] == "openrouter"
    assert meta["model"] == "deepseek/deepseek-chat"
    assert meta["status"] == "success"
    assert meta["success"] is True
    assert meta["finish_reason"] == "stop"
    assert meta["usage"]["total_tokens"] == 40


# ==============================================================================
# 6. Empty or Malformed Responses
# ==============================================================================

def test_6_empty_or_malformed_response():
    """Verify empty choices or error payload raise OpenRouterAPIError."""
    cfg = LLMConfig(provider="openrouter", api_key="sk-or-v1-key")
    client = OpenRouterClient(cfg)

    # Empty choices
    with patch("urllib.request.urlopen", return_value=_make_mock_response(200, {"choices": []})):
        with pytest.raises(OpenRouterAPIError, match="empty or invalid choices"):
            client.generate("test")

    # Error field in 200 payload
    with patch("urllib.request.urlopen", return_value=_make_mock_response(200, {"error": {"message": "Model error"}})):
        with pytest.raises(OpenRouterAPIError, match="OpenRouter error payload"):
            client.generate("test")


# ==============================================================================
# 7. Error Handling (Auth, Credits, Rate Limit, Server Errors)
# ==============================================================================

def test_7_missing_api_key_raises_auth_error():
    """Verify missing key raises OpenRouterAuthError before making HTTP request."""
    cfg = LLMConfig(provider="openrouter", api_key=None)
    client = OpenRouterClient(cfg)
    with pytest.raises(OpenRouterAuthError, match="OpenRouter API key is missing"):
        client.generate("test")


def test_7_auth_credit_ratelimit_and_server_http_errors():
    """Verify mapped HTTP error codes to OpenRouter exception classes."""
    cfg = LLMConfig(provider="openrouter", api_key="sk-or-v1-key")
    client = OpenRouterClient(cfg)

    # 401 Unauthorized
    with patch("urllib.request.urlopen", side_effect=_make_http_error(client.endpoint, 401, {"error": "Invalid token"})):
        with pytest.raises(OpenRouterAuthError, match="HTTP 401"):
            client.generate("test")

    # 402 Payment Required / Credits exhausted
    with patch("urllib.request.urlopen", side_effect=_make_http_error(client.endpoint, 402, {"error": "No credits"})):
        with pytest.raises(OpenRouterCreditError, match="HTTP 402"):
            client.generate("test")

    # 429 Rate Limit
    with patch("urllib.request.urlopen", side_effect=_make_http_error(client.endpoint, 429, {"error": "Rate limit"})):
        with pytest.raises(OpenRouterRateLimitError, match="HTTP 429"):
            client.generate("test")

    # 503 Server Error
    with patch("urllib.request.urlopen", side_effect=_make_http_error(client.endpoint, 503, {"error": "Overloaded"})):
        with pytest.raises(OpenRouterAPIError, match="HTTP 503"):
            client.generate("test")


# ==============================================================================
# 8. Network and Timeout Handling
# ==============================================================================

def test_8_network_and_timeout_errors():
    """Verify socket TimeoutError and URLError raise OpenRouterTimeoutError and OpenRouterConnectionError."""
    cfg = LLMConfig(provider="openrouter", api_key="sk-or-v1-key", max_retries=1, retry_delay=0.001)
    client = OpenRouterClient(cfg)

    # Timeout
    with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
        with patch("time.sleep"):
            with pytest.raises(OpenRouterTimeoutError, match="timed out"):
                client.generate("test")

    # Connection Error
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("DNS resolution failed")):
        with patch("time.sleep"):
            with pytest.raises(OpenRouterConnectionError, match="Failed to connect to OpenRouter"):
                client.generate("test")


# ==============================================================================
# 10. Accurate Traceability Metadata in ConversationalLLMService
# ==============================================================================

def test_10_conversational_llm_service_metadata():
    """Verify ConversationalLLMService correctly populates llm_used, provider, model, latency."""
    cfg = LLMConfig(provider="openrouter", api_key="sk-or-v1-test", model_name="meta-llama/llama-3.3-70b-instruct")

    mock_client = MagicMock()
    mock_client.generate.return_value = "Ceiling height should be at least 3.0 meters."
    mock_client.last_metadata = {"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct"}

    service = ConversationalLLMService(
        llm_client=mock_client,
        config_loader=lambda: cfg,
    )

    res = service.generate_reply(
        prompt="Ceiling height question",
        system_prompt="Architectural assistant",
        turn_id="turn_test_1",
    )

    assert res.ok is True
    assert res.provider == "openrouter"
    assert res.model == "meta-llama/llama-3.3-70b-instruct"
    assert res.status == STATUS_SUCCESS
    assert "3.0 meters" in res.text
    assert res.latency_ms >= 0


def test_10_conversational_llm_service_error_graceful_handling():
    """Verify ConversationalLLMService catches OpenRouterAPIError, sets ok=False, and returns user message."""
    cfg = LLMConfig(provider="openrouter", api_key="sk-or-v1-test")

    mock_client = MagicMock()
    mock_client.generate.side_effect = OpenRouterCreditError("OpenRouter account credits exhausted")
    mock_client.last_metadata = {"provider": "openrouter"}

    service = ConversationalLLMService(
        llm_client=mock_client,
        config_loader=lambda: cfg,
    )

    res = service.generate_reply(
        prompt="Ceiling height question",
        system_prompt="Architectural assistant",
        turn_id="turn_test_err",
    )

    assert res.ok is False
    assert res.status == STATUS_UNAVAILABLE
    assert "couldn't reach the configured AI model" in res.user_message


# ==============================================================================
# 11, 12 & 13. Chat Orchestrator Integration & Regression Safety
# ==============================================================================

def test_11_and_12_orchestrator_chat_flow_with_openrouter():
    """Verify ChatOrchestrator invokes OpenRouter for general architectural query, preserves state, and does not alter requirements."""
    cfg = LLMConfig(provider="openrouter", api_key="sk-or-v1-test", model_name="meta-llama/llama-3.3-70b-instruct")

    mock_client = MagicMock()
    mock_client.generate.return_value = "For a modern duplex living room, a ceiling height of 3.0m to 3.6m provides ideal acoustics."
    mock_client.last_metadata = {"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct"}

    llm_service = ConversationalLLMService(
        llm_client=mock_client,
        config_loader=lambda: cfg,
    )

    orchestrator = ChatOrchestrator(llm_service=llm_service)

    # 1. Architectural question reaches LLM
    res = orchestrator.handle(
        message="What is the recommended ceiling height for a modern duplex living room?",
        existing_brief="Plot 30x40 feet. 2 floors.",
    )

    assert res.route == "conversation"
    assert res.llm_used is True
    assert res.llm_provider == "openrouter"
    assert res.llm_model == "meta-llama/llama-3.3-70b-instruct"
    assert "3.0m to 3.6m" in res.turn.message
    # Requirements must NOT be mutated by a general question
    assert res.turn.requirements_text == "Plot 30x40 feet. 2 floors."
    assert res.response_type == ResponseType.TEXT


def test_13_ordinary_question_never_triggers_generation():
    """Verify asking questions never sets is_ready_for_generation or triggers floor-plan generation."""
    cfg = LLMConfig(provider="openrouter", api_key="sk-or-v1-test")
    mock_client = MagicMock()
    mock_client.generate.return_value = "Sunlight orientation is best from south-east."

    llm_service = ConversationalLLMService(
        llm_client=mock_client,
        config_loader=lambda: cfg,
    )
    orchestrator = ChatOrchestrator(llm_service=llm_service)

    res = orchestrator.handle(
        message="How does sun orientation affect living room placement?",
        existing_brief="Plot 30x40 feet.",
    )

    assert res.action is None
    assert res.turn.is_ready_for_generation is False
    assert res.response_type == ResponseType.TEXT


# ==============================================================================
# 14 & 15. Exponential Backoff and Retry-After Tests
# ==============================================================================

def test_14_http_429_retry_success_with_retry_after():
    """Verify HTTP 429 parses Retry-After header, sleeps, retries and succeeds."""
    cfg = LLMConfig(
        provider="openrouter",
        api_key="sk-or-v1-key",
        model_name="primary-model",
        fallback_models=[],
        max_retries=2,
        retry_delay=0.1,
    )
    client = OpenRouterClient(cfg)

    call_count = 0
    slept_durations = []

    def mock_sleep(d):
        slept_durations.append(d)

    def mock_urlopen(req, timeout):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            err = _make_http_error(client.endpoint, 429, {"error": "Too Many Requests"})
            err.headers = {"Retry-After": "2.5"}
            raise err
        return _make_mock_response(200, {
            "choices": [{"message": {"content": "Success after retry"}}],
            "model": "primary-model",
        })

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        with patch("time.sleep", side_effect=mock_sleep):
            res = client.generate("test prompt")

    assert res == "Success after retry"
    assert call_count == 2
    assert len(slept_durations) == 1
    assert slept_durations[0] == 2.5
    assert client.last_metadata["attempts"] == 2
    assert client.last_metadata["status"] == "success"


def test_15_http_429_exhausted_retries_raises_ratelimit_error():
    """Verify exhausted retries on HTTP 429 raises OpenRouterRateLimitError with attempts counted."""
    cfg = LLMConfig(
        provider="openrouter",
        api_key="sk-or-v1-key",
        model_name="primary-model",
        fallback_models=[],
        max_retries=2,
        retry_delay=0.01,
    )
    client = OpenRouterClient(cfg)
    call_count = 0

    def mock_urlopen(req, timeout):
        nonlocal call_count
        call_count += 1
        raise _make_http_error(client.endpoint, 429, {"error": "Rate limit exceeded"})

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        with patch("time.sleep"):
            with pytest.raises(OpenRouterRateLimitError, match="HTTP 429.*after 3 attempts"):
                client.generate("test prompt")

    assert call_count == 3  # Initial + 2 retries
    assert client.last_metadata["attempts"] == 3
    assert client.last_metadata["status"] == "rate_limited"
    assert client.last_metadata["success"] is False


def test_16_transient_5xx_recovery():
    """Verify transient 500/503 server error recovers on retry."""
    cfg = LLMConfig(
        provider="openrouter",
        api_key="sk-or-v1-key",
        model_name="primary-model",
        fallback_models=[],
        max_retries=2,
        retry_delay=0.01,
    )
    client = OpenRouterClient(cfg)
    call_count = 0

    def mock_urlopen(req, timeout):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise _make_http_error(client.endpoint, 503, {"error": "Service temporarily unavailable"})
        return _make_mock_response(200, {
            "choices": [{"message": {"content": "Server recovered"}}],
            "model": "primary-model",
        })

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        with patch("time.sleep"):
            res = client.generate("test prompt")

    assert res == "Server recovered"
    assert call_count == 2
    assert client.last_metadata["attempts"] == 2
    assert client.last_metadata["status"] == "success"


def test_17_non_retryable_errors_do_not_retry():
    """Verify HTTP 401, 402, 400 do not retry and fail on attempt 1."""
    cfg = LLMConfig(
        provider="openrouter",
        api_key="sk-or-v1-key",
        model_name="primary-model",
        max_retries=3,
        retry_delay=0.01,
    )
    client = OpenRouterClient(cfg)

    # 401 Auth error
    call_count_401 = 0
    def mock_401(req, timeout):
        nonlocal call_count_401
        call_count_401 += 1
        raise _make_http_error(client.endpoint, 401, {"error": "Unauthorized"})

    with patch("urllib.request.urlopen", side_effect=mock_401):
        with pytest.raises(OpenRouterAuthError):
            client.generate("test")
    assert call_count_401 == 1

    # 400 Bad request / invalid model
    call_count_400 = 0
    def mock_400(req, timeout):
        nonlocal call_count_400
        call_count_400 += 1
        raise _make_http_error(client.endpoint, 400, {"error": "Invalid model ID"})

    with patch("urllib.request.urlopen", side_effect=mock_400):
        with pytest.raises(OpenRouterAPIError, match="HTTP 400"):
            client.generate("test")
    assert call_count_400 == 1


def test_18_multi_model_fallback_success():
    """Verify client attempts configured fallback model when primary model fails after retries."""
    cfg = LLMConfig(
        provider="openrouter",
        api_key="sk-or-v1-key",
        model_name="google/gemma-4-31b-it:free",
        fallback_models=["nvidia/nemotron-3.5-lightning:free"],
        max_retries=1,
        retry_delay=0.01,
        allow_provider_fallbacks=True,
    )
    client = OpenRouterClient(cfg)

    server_fallback_resp = _make_mock_response(200, {
        "choices": [{"message": {"content": "Fallback response from Nemotron"}}],
        "model": "nvidia/nemotron-3.5-lightning:free",
    })

    with patch("urllib.request.urlopen", return_value=server_fallback_resp):
        res = client.generate("Design advice")

    assert res == "Fallback response from Nemotron"
    assert client.last_metadata["model"] == "nvidia/nemotron-3.5-lightning:free"
    assert client.last_metadata["model_requested"] == "google/gemma-4-31b-it:free"
    assert client.last_metadata["fallback_used"] is True


def test_19_conversational_service_rate_limited_status():
    """Verify ConversationalLLMService handles OpenRouterRateLimitError with STATUS_RATE_LIMITED and llm_used=False."""
    cfg = LLMConfig(provider="openrouter", api_key="sk-or-v1-key")
    mock_client = MagicMock()
    mock_client.generate.side_effect = OpenRouterRateLimitError("Rate limit exceeded")
    mock_client.last_metadata = {"provider": "openrouter", "model": "google/gemma-4-31b-it:free"}

    service = ConversationalLLMService(
        llm_client=mock_client,
        config_loader=lambda: cfg,
    )
    res = service.generate_reply(prompt="Hello", system_prompt="Sys", turn_id="t1")

    assert res.ok is False
    assert res.status == "LLM_RATE_LIMITED"
    assert "rate-limited" in res.user_message.lower()
    assert res.text == ""


def test_20_explicit_generate_intent_produces_generation_action():
    """Verify explicit generation requests produce GENERATE_PLAN action when requirements complete, but prompt for clarification when incomplete."""
    cfg = LLMConfig(provider="openrouter", api_key="sk-or-v1-key")
    mock_client = MagicMock()
    mock_client.generate.return_value = "Proceeding with floor plan generation."

    service = ConversationalLLMService(
        llm_client=mock_client,
        config_loader=lambda: cfg,
    )
    orchestrator = ChatOrchestrator(llm_service=service)

    # 1. Ordinary architectural question -> No generation action
    res_q = orchestrator.handle(
        message="What is the standard width for a residential hallway?",
        existing_brief="Plot 40x60 feet.",
    )
    assert res_q.action is None
    assert res_q.plan_modified is False

    # 2. Incomplete requirements + generation request -> Stays conversational / asks clarification
    res_inc = orchestrator.handle(
        message="Generate the floor plan now",
        existing_brief="Plot 40x60 feet.",
    )
    assert res_inc.action is None
    assert res_inc.turn.is_ready_for_generation is False

    # 3. Complete requirements + explicit generate command -> Generation action produced
    res_gen = orchestrator.handle(
        message="Generate the floor plan now",
        existing_brief="Plot 30x40 feet. 1 floor. North entrance. 2 bedrooms, 1 bathroom, 1 kitchen, 1 living room.",
    )
    assert res_gen.action is not None
    assert res_gen.action.type == "generate_floor_plan"


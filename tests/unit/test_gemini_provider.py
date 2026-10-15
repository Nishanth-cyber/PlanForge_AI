"""Unit tests for Google Gemini provider integration in PlanForge AI.

Verifies:
1. Google Gemini provider configuration and environment loading.
2. Factory construction for Google Gemini (and alias 'gemini'), OpenRouter, HuggingFace, and mock.
3. API request formatting, system instructions, temperature, max output tokens, and auth options.
4. Successful text and structured JSON responses with metadata extraction.
5. Empty, malformed, or safety-blocked response handling.
6. Authentication failures (missing key, invalid key HTTP 400/401/403) without retries.
7. Quota and rate-limit errors (HTTP 429 RESOURCE_EXHAUSTED).
8. Retry behavior with exponential backoff on transient errors.
9. Multi-model fallback (gemini-2.0-flash -> gemini-1.5-flash).
10. Secondary provider fallback (Gemini -> OpenRouter) on quota exhaustion.
11. ConversationalLLMService integration: status, latency, provider, model, error classification, redaction.
12. Conversational chat vs. floor-plan generation isolation in ChatOrchestrator:
    - Greetings and architectural inquiries never trigger floor plans.
    - Incomplete plot/rooms triggers clarification/update.
    - Explicit generation requests follow deterministic requirements and validation workflow.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest

from app.llm.client import (
    GoogleGeminiAPIError,
    GoogleGeminiAuthError,
    GoogleGeminiClient,
    GoogleGeminiConnectionError,
    GoogleGeminiError,
    GoogleGeminiQuotaError,
    GoogleGeminiRateLimitError,
    GoogleGeminiTimeoutError,
    HuggingFaceClient,
    MockLLMClient,
    OpenRouterClient,
)
from app.llm.configuration import LLMConfig
from app.llm.factory import create_llm_client
from app.llm.response_parser import LLMResponseParser
from app.chat.llm_service import (
    ConversationalLLMService,
    STATUS_RATE_LIMITED,
    STATUS_SUCCESS,
    STATUS_TIMEOUT,
    STATUS_UNAVAILABLE,
)
from app.chat.orchestrator import ChatOrchestrator
from app.chat.schema import ConversationIntent, ResponseType


# ==============================================================================
# Helper Mock Objects for Google Gen AI SDK
# ==============================================================================

def _make_gemini_response(
    text: str = "Test response",
    finish_reason: str = "STOP",
    prompt_tokens: int = 15,
    candidates_tokens: int = 25,
    total_tokens: int = 40,
) -> MagicMock:
    """Create a mock GenerateContentResponse matching google-genai SDK structure."""
    mock_resp = MagicMock()
    mock_resp.text = text

    mock_part = MagicMock()
    mock_part.text = text

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.finish_reason = finish_reason
    mock_candidate.content = mock_content

    mock_resp.candidates = [mock_candidate]

    mock_usage = MagicMock()
    mock_usage.prompt_token_count = prompt_tokens
    mock_usage.candidates_token_count = candidates_tokens
    mock_usage.total_token_count = total_tokens
    mock_resp.usage_metadata = mock_usage

    return mock_resp


def _make_api_error(code: int, message: str) -> Exception:
    """Create a mock google.genai.errors.APIError."""
    try:
        from google.genai.errors import APIError
        err = APIError(code, message)
        err.code = code
        err.message = message
        return err
    except Exception:
        exc = RuntimeError(f"HTTP {code}: {message}")
        exc.code = code
        exc.message = message
        return exc


# ==============================================================================
# 1. Configuration & Environment
# ==============================================================================

def test_1_gemini_configuration_from_env(monkeypatch):
    """Verify LLMConfig parses Google Gemini environment variables correctly."""
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("PLANFORGE_LLM_PROVIDER", "google")
    monkeypatch.setenv("PLANFORGE_GOOGLE_API_KEY", "AIzaSy_test_secret_key_1234567890")
    monkeypatch.setenv("PLANFORGE_LLM_MODEL", "gemini-2.0-flash")
    monkeypatch.setenv("PLANFORGE_FALLBACK_PROVIDER", "openrouter")
    monkeypatch.setenv("PLANFORGE_LLM_TIMEOUT", "60.0")
    monkeypatch.setenv("PLANFORGE_LLM_TEMPERATURE", "0.3")
    monkeypatch.setenv("PLANFORGE_LLM_MAX_TOKENS", "2048")
    monkeypatch.setenv("PLANFORGE_LLM_MAX_RETRIES", "2")
    monkeypatch.setenv("PLANFORGE_LLM_RETRY_DELAY", "0.5")

    cfg = LLMConfig.from_env()

    assert cfg.provider == "google"
    assert cfg.api_key == "AIzaSy_test_secret_key_1234567890"
    assert cfg.model_name == "gemini-2.0-flash"
    assert cfg.fallback_provider == "openrouter"
    assert cfg.timeout_seconds == 60.0
    assert cfg.temperature == 0.3
    assert cfg.max_tokens == 2048
    assert cfg.max_retries == 2
    assert cfg.retry_delay == 0.5
    assert "gemini-3.8-flash" in cfg.fallback_models


def test_1_gemini_alias_and_alternative_env_keys(monkeypatch):
    """Verify 'gemini' alias and GEMINI_API_KEY / GOOGLE_API_KEY env fallbacks."""
    monkeypatch.setattr("app.llm.configuration.load_dotenv_file", lambda *a, **k: None)
    monkeypatch.delenv("PLANFORGE_GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("PLANFORGE_LLM_API_KEY", raising=False)
    monkeypatch.setenv("PLANFORGE_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSy_gemini_alt_key")

    cfg = LLMConfig.from_env()
    assert cfg.provider == "gemini"
    assert cfg.api_key == "AIzaSy_gemini_alt_key"


def test_1_gemini_google_model_env_variable(monkeypatch):
    """Verify GOOGLE_MODEL env variable and google-gla: prefix stripping."""
    monkeypatch.setattr("app.llm.configuration.load_dotenv_file", lambda *a, **k: None)
    monkeypatch.delenv("PLANFORGE_LLM_MODEL", raising=False)
    monkeypatch.setenv("PLANFORGE_LLM_PROVIDER", "google")
    monkeypatch.setenv("PLANFORGE_GOOGLE_API_KEY", "AIzaSy_test_key")
    monkeypatch.setenv("GOOGLE_MODEL", "google-gla:gemini-3.8-flash")

    cfg = LLMConfig.from_env()
    assert cfg.model_name == "gemini-3.8-flash"


# ==============================================================================
# 2. Factory Construction
# ==============================================================================

def test_2_correct_factory_construction():
    """Verify create_llm_client constructs GoogleGeminiClient for google & gemini."""
    cfg_google = LLMConfig(provider="google", api_key="AIzaSy_test")
    client_google = create_llm_client(cfg_google)
    assert isinstance(client_google, GoogleGeminiClient)

    cfg_gemini = LLMConfig(provider="gemini", api_key="AIzaSy_test")
    client_gemini = create_llm_client(cfg_gemini)
    assert isinstance(client_gemini, GoogleGeminiClient)

    cfg_or = LLMConfig(provider="openrouter", api_key="sk-or-v1-abc")
    assert isinstance(create_llm_client(cfg_or), OpenRouterClient)

    cfg_hf = LLMConfig(provider="huggingface", api_key="hf_test")
    assert isinstance(create_llm_client(cfg_hf), HuggingFaceClient)

    cfg_mock = LLMConfig(provider="mock")
    assert isinstance(create_llm_client(cfg_mock), MockLLMClient)


def test_2_factory_constructs_fallback_provider():
    """Verify factory hooks up OpenRouter as fallback_client when requested."""
    cfg = LLMConfig(provider="google", api_key="AIzaSy_test", fallback_provider="openrouter")
    client = create_llm_client(cfg)
    assert isinstance(client, GoogleGeminiClient)
    assert isinstance(client.fallback_client, OpenRouterClient)


def test_2_unsupported_provider_raises_value_error():
    """Verify unsupported provider name raises clear ValueError and never falls back to mock."""
    cfg_invalid = LLMConfig(provider="unsupported_custom_provider")
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        create_llm_client(cfg_invalid)


# ==============================================================================
# 3. Request Formatting & SDK Invocation
# ==============================================================================

def test_3_request_formatting_and_sdk_call():
    """Verify prompt, system prompt, temperature, max_tokens passed to SDK."""
    cfg = LLMConfig(
        provider="google",
        api_key="AIzaSy_valid_key",
        model_name="gemini-2.0-flash",
        temperature=0.2,
        max_tokens=1024,
        timeout_seconds=45.0,
    )
    client = GoogleGeminiClient(cfg)

    mock_sdk_client = MagicMock()
    mock_sdk_client.models.generate_content.return_value = _make_gemini_response(
        "Architectural recommendation"
    )

    with patch.object(client, "_get_client", return_value=mock_sdk_client):
        resp = client.generate(
            prompt="Design living room",
            system_prompt="You are an architect assistant",
        )

    assert resp == "Architectural recommendation"
    mock_sdk_client.models.generate_content.assert_called_once()
    call_kwargs = mock_sdk_client.models.generate_content.call_args[1]

    assert call_kwargs["model"] == "gemini-2.0-flash"
    assert call_kwargs["contents"] == "Design living room"
    gen_config = call_kwargs["config"]
    assert gen_config.system_instruction == "You are an architect assistant"
    assert gen_config.temperature == 0.2
    assert gen_config.max_output_tokens == 1024


# ==============================================================================
# 4. Successful Text and Structured JSON Responses & Metadata
# ==============================================================================

def test_4_successful_structured_json_response_and_metadata():
    """Verify JSON room plan generation, think tag stripping, and factual metadata."""
    cfg = LLMConfig(provider="google", api_key="AIzaSy_key", model_name="gemini-2.0-flash")
    client = GoogleGeminiClient(cfg)

    json_payload = """<think>Designing floor layout</think>{
        "room_type": "living",
        "intended_shape": "rectangular",
        "intended_dimensions": [6.0, 5.0],
        "intended_area_sqm": 30.0,
        "design_rationale": "Spacious living area"
    }"""

    mock_sdk_client = MagicMock()
    mock_sdk_client.models.generate_content.return_value = _make_gemini_response(
        text=json_payload, finish_reason="STOP", prompt_tokens=20, candidates_tokens=45, total_tokens=65
    )

    with patch.object(client, "_get_client", return_value=mock_sdk_client):
        result = client.generate("Generate living room")

    assert "<think>" not in result
    parsed = LLMResponseParser.parse_json(result)
    assert parsed["room_type"] == "living"
    assert parsed["intended_dimensions"] == [6.0, 5.0]

    meta = client.last_metadata
    assert meta["provider"] == "google"
    assert meta["model"] == "gemini-2.0-flash"
    assert meta["status"] == "success"
    assert meta["success"] is True
    assert meta["finish_reason"] == "STOP"
    assert meta["usage"]["total_tokens"] == 65
    assert meta["latency_ms"] >= 0


# ==============================================================================
# 5. Empty, Malformed, and Safety-Blocked Responses
# ==============================================================================

def test_5_empty_or_blocked_response_raises_api_error():
    """Verify empty candidates or blocked finish reasons raise GoogleGeminiAPIError."""
    cfg = LLMConfig(provider="google", api_key="AIzaSy_key")
    client = GoogleGeminiClient(cfg)

    # Empty text and empty parts
    mock_sdk = MagicMock()
    empty_resp = MagicMock()
    empty_resp.text = ""
    empty_resp.candidates = []
    mock_sdk.models.generate_content.return_value = empty_resp

    with patch.object(client, "_get_client", return_value=mock_sdk):
        with pytest.raises(GoogleGeminiAPIError, match=r"(?i)empty response|blocked"):
            client.generate("test")

    # Safety blocked candidate
    blocked_resp = _make_gemini_response(text="", finish_reason="SAFETY")
    blocked_resp.candidates[0].content.parts = []
    mock_sdk.models.generate_content.return_value = blocked_resp

    with patch.object(client, "_get_client", return_value=mock_sdk):
        with pytest.raises(GoogleGeminiAPIError, match=r"(?i)empty response|blocked"):
            client.generate("test")


# ==============================================================================
# 6. Authentication Failures (Missing or Invalid Key)
# ==============================================================================

def test_6_missing_api_key_raises_auth_error():
    """Verify missing API key raises GoogleGeminiAuthError before making any call."""
    cfg = LLMConfig(provider="google", api_key=None)
    client = GoogleGeminiClient(cfg)
    with pytest.raises(GoogleGeminiAuthError, match="Google Gemini API key is missing"):
        client.generate("test")


def test_6_invalid_api_key_fails_immediately_without_retries():
    """Verify HTTP 400 (API key not valid) or HTTP 401/403 fails immediately without retrying."""
    cfg = LLMConfig(provider="google", api_key="AIzaSy_invalid", max_retries=3)
    client = GoogleGeminiClient(cfg)

    mock_sdk = MagicMock()
    api_err = _make_api_error(400, "API key not valid. Please pass a valid API key.")
    mock_sdk.models.generate_content.side_effect = api_err

    with patch.object(client, "_get_client", return_value=mock_sdk):
        with pytest.raises(GoogleGeminiAuthError, match=r"(?i)authentication failed"):
            client.generate("test")

    # Only 1 attempt must be made: no backoff retries on auth failure
    assert mock_sdk.models.generate_content.call_count == 1


# ==============================================================================
# 7. Quota and Rate-Limit Errors
# ==============================================================================

def test_7_quota_exhausted_raises_quota_error():
    """Verify HTTP 429 RESOURCE_EXHAUSTED raises GoogleGeminiQuotaError."""
    cfg = LLMConfig(provider="google", api_key="AIzaSy_key", max_retries=1, retry_delay=0.01)
    client = GoogleGeminiClient(cfg)

    mock_sdk = MagicMock()
    quota_err = _make_api_error(429, "Resource has been exhausted (e.g. check quota).")
    mock_sdk.models.generate_content.side_effect = quota_err

    with patch.object(client, "_get_client", return_value=mock_sdk):
        with pytest.raises(GoogleGeminiQuotaError, match=r"(?i)quota exhausted"):
            client.generate("test")


# ==============================================================================
# 8. Retry and Timeout Behavior
# ==============================================================================

def test_8_retry_on_transient_error_succeeds_eventually():
    """Verify transient 503 or transient 429 retries with backoff and succeeds."""
    cfg = LLMConfig(provider="google", api_key="AIzaSy_key", max_retries=2, retry_delay=0.01)
    client = GoogleGeminiClient(cfg)

    mock_sdk = MagicMock()
    err_503 = _make_api_error(503, "Service Unavailable")
    success_resp = _make_gemini_response("Recovered after transient error")
    mock_sdk.models.generate_content.side_effect = [err_503, success_resp]

    with patch.object(client, "_get_client", return_value=mock_sdk):
        resp = client.generate("test")

    assert resp == "Recovered after transient error"
    assert mock_sdk.models.generate_content.call_count == 2


def test_8_timeout_raises_timeout_error():
    """Verify TimeoutError raises GoogleGeminiTimeoutError."""
    cfg = LLMConfig(provider="google", api_key="AIzaSy_key", timeout_seconds=5.0)
    client = GoogleGeminiClient(cfg)

    mock_sdk = MagicMock()
    mock_sdk.models.generate_content.side_effect = TimeoutError("Request timed out")

    with patch.object(client, "_get_client", return_value=mock_sdk):
        with pytest.raises(GoogleGeminiTimeoutError, match="timed out"):
            client.generate("test")


# ==============================================================================
# 9. Multi-Model Fallback
# ==============================================================================

def test_9_multi_model_fallback_on_model_not_found():
    """Verify that if primary model fails with 404, secondary fallback model is attempted."""
    cfg = LLMConfig(
        provider="google",
        api_key="AIzaSy_key",
        model_name="gemini-2.0-flash",
        fallback_models=["gemini-1.5-flash"],
    )
    client = GoogleGeminiClient(cfg)

    mock_sdk = MagicMock()
    err_404 = _make_api_error(404, "models/gemini-2.0-flash is not found")
    success_resp = _make_gemini_response("Response from gemini-1.5-flash")

    mock_sdk.models.generate_content.side_effect = [err_404, success_resp]

    with patch.object(client, "_get_client", return_value=mock_sdk):
        resp = client.generate("test")

    assert resp == "Response from gemini-1.5-flash"
    assert client.last_metadata["model"] == "gemini-1.5-flash"
    assert client.last_metadata["fallback_used"] is True


# ==============================================================================
# 10. Secondary Provider Fallback (Gemini -> OpenRouter)
# ==============================================================================

def test_10_secondary_provider_fallback_on_gemini_quota_exhaustion():
    """Verify that when Gemini quota is exhausted, fallback_client is invoked and recorded."""
    cfg = LLMConfig(
        provider="google",
        api_key="AIzaSy_key",
        model_name="gemini-2.0-flash",
        fallback_models=[],
        max_retries=1,
        retry_delay=0.01,
    )
    mock_fallback_client = MagicMock()
    mock_fallback_client.generate.return_value = "Response from fallback OpenRouter"
    mock_fallback_client.last_metadata = {"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct"}

    client = GoogleGeminiClient(cfg, fallback_client=mock_fallback_client)

    mock_sdk = MagicMock()
    quota_err = _make_api_error(429, "Resource has been exhausted (quota exceeded).")
    mock_sdk.models.generate_content.side_effect = quota_err

    with patch.object(client, "_get_client", return_value=mock_sdk):
        resp = client.generate("test")

    assert resp == "Response from fallback OpenRouter"
    assert client.last_metadata["fallback_provider_used"] is True
    assert client.last_metadata["provider"] == "openrouter"


# ==============================================================================
# 11. ConversationalLLMService Integration
# ==============================================================================

def test_11_conversational_service_success():
    """Verify ConversationalLLMService normalizes success response with Google Gemini."""
    cfg = LLMConfig(provider="google", api_key="AIzaSy_key", model_name="gemini-2.0-flash")
    mock_client = MagicMock()
    mock_client.generate.return_value = "Living rooms usually require at least 20 square meters."
    mock_client.last_metadata = {
        "provider": "google",
        "model": "gemini-2.0-flash",
        "latency_ms": 320,
    }

    service = ConversationalLLMService(
        llm_client=mock_client,
        config_loader=lambda: cfg,
    )

    result = service.generate_reply(
        prompt="How big should a living room be?",
        system_prompt="Architect assistant",
        turn_id="turn-1",
    )

    assert result.ok is True
    assert result.status == STATUS_SUCCESS
    assert result.provider == "google"
    assert result.model == "gemini-2.0-flash"
    assert "Living rooms usually require" in result.text


def test_11_conversational_service_quota_and_rate_limit():
    """Verify ConversationalLLMService translates Gemini quota/rate limits to STATUS_RATE_LIMITED."""
    cfg = LLMConfig(provider="google", api_key="AIzaSy_key")
    mock_client = MagicMock()
    mock_client.generate.side_effect = GoogleGeminiQuotaError("HTTP 429: Quota exhausted")
    mock_client.last_metadata = {"provider": "google", "model": "gemini-2.0-flash"}

    service = ConversationalLLMService(
        llm_client=mock_client,
        config_loader=lambda: cfg,
    )

    result = service.generate_reply(
        prompt="test",
        system_prompt="sys",
        turn_id="turn-2",
    )

    assert result.ok is False
    assert result.status == STATUS_RATE_LIMITED
    assert "rate-limited" in result.user_message.lower()


def test_11_conversational_service_redacts_google_api_key():
    """Verify Google API key starting with AIzaSy is scrubbed from error logs."""
    cfg = LLMConfig(provider="google", api_key="AIzaSy_SECRET_KEY_1234567890abcdef")
    mock_client = MagicMock()
    mock_client.generate.side_effect = GoogleGeminiAPIError(
        400, "Error with key AIzaSy_SECRET_KEY_1234567890abcdef in request"
    )

    service = ConversationalLLMService(
        llm_client=mock_client,
        config_loader=lambda: cfg,
    )

    result = service.generate_reply(prompt="test", system_prompt="sys", turn_id="turn-3")
    assert result.ok is False
    assert result.status == STATUS_UNAVAILABLE
    assert "AIzaSy_SECRET_KEY" not in result.user_message


# ==============================================================================
# 12. Agentic Conversation vs. Generation Isolation in ChatOrchestrator
# ==============================================================================

def test_12_greeting_does_not_trigger_floor_plan():
    """Verify greetings answer conversationally and never trigger floor-plan generation."""
    mock_llm_client = MagicMock()
    mock_llm_client.generate.return_value = "Hello! I am PlanForge AI. How can I help you design your home today?"
    mock_llm_client.last_metadata = {"provider": "google", "model": "gemini-2.0-flash"}

    service = ConversationalLLMService(
        llm_client=mock_llm_client,
        config_loader=lambda: LLMConfig(provider="google", api_key="AIzaSy_test"),
    )
    orchestrator = ChatOrchestrator(llm_service=service)

    result = orchestrator.handle(
        message="Hello, how can you help me?",
        existing_brief="",
    )

    assert result.action is None
    assert result.plan_modified is False
    assert "PlanForge AI" in result.turn.message
    assert result.llm_used is True
    assert result.llm_provider == "google"


def test_12_architectural_inquiry_does_not_trigger_floor_plan():
    """Verify architectural questions receive explanations without generating a floor plan."""
    mock_llm_client = MagicMock()
    mock_llm_client.generate.return_value = (
        "For a master bedroom, standard dimensions are typically 4.5m x 4.0m (around 18 sqm) to comfortably fit a king bed."
    )
    mock_llm_client.last_metadata = {"provider": "google", "model": "gemini-2.0-flash"}

    service = ConversationalLLMService(
        llm_client=mock_llm_client,
        config_loader=lambda: LLMConfig(provider="google", api_key="AIzaSy_test"),
    )
    orchestrator = ChatOrchestrator(llm_service=service)

    result = orchestrator.handle(
        message="What are standard master bedroom dimensions?",
        existing_brief="Plot 40x60 feet.",
    )

    assert result.action is None
    assert result.plan_modified is False
    assert "master bedroom" in result.turn.message.lower()
    assert result.llm_used is True


def test_12_incomplete_plot_requirements_trigger_clarification():
    """Verify incomplete requirements trigger clarification questions without generating plan."""
    mock_llm_client = MagicMock()
    mock_llm_client.generate.return_value = "Noted."
    mock_llm_client.last_metadata = {"provider": "google", "model": "gemini-2.0-flash"}

    service = ConversationalLLMService(
        llm_client=mock_llm_client,
        config_loader=lambda: LLMConfig(provider="google", api_key="AIzaSy_test"),
    )
    orchestrator = ChatOrchestrator(llm_service=service)

    result = orchestrator.handle(
        message="Generate the floor plan now",
        existing_brief="Plot 40x60 feet.",
    )

    assert result.action is None
    assert result.turn.is_ready_for_generation is False


def test_12_explicit_generate_with_satisfied_requirements_triggers_generation():
    """Verify explicit generate command with satisfied requirements triggers floor-plan generation."""
    mock_llm_client = MagicMock()
    mock_llm_client.generate.return_value = "Proceeding with floor plan generation."
    mock_llm_client.last_metadata = {"provider": "google", "model": "gemini-2.0-flash"}

    service = ConversationalLLMService(
        llm_client=mock_llm_client,
        config_loader=lambda: LLMConfig(provider="google", api_key="AIzaSy_test"),
    )
    orchestrator = ChatOrchestrator(llm_service=service)

    result = orchestrator.handle(
        message="Generate the floor plan now",
        existing_brief="Plot 30x40 feet. 1 floor. North entrance. 2 bedrooms, 1 bathroom, 1 kitchen, 1 living room.",
    )

    assert result.action is not None
    assert result.action.type == "generate_floor_plan"

"""Unit tests for Hugging Face DeepSeek provider integration, selection, failures, and dimension handling."""

import json
import os
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from app.agents.architectural_agent.agent import ArchitecturalAgent
from app.agents.architectural_agent.context import ContextBuilder
from app.agents.architectural_agent.structured_output import (
    MalformedLLMResponseError,
    UserDimensionConstraintViolationError,
)
from app.agents.requirement_agent.parser import RequirementParser
from app.llm.client import (
    HuggingFaceAPIError,
    HuggingFaceClient,
    HuggingFaceConnectionError,
    HuggingFaceTimeoutError,
    MockLLMClient,
)
from app.llm.configuration import LLMConfig
from app.llm.factory import create_llm_client
from app.models.allocation import AllocatedRegion, Allocation, AllocationSet
from app.models.planning import FloorPlanSpec, PlanningSpec, RoomSpec
from app.models.requirements import FloorRequirement, Requirements, RoomRequirement


# ==============================================================================
# A. Provider Selection
# ==============================================================================

def test_provider_selection_mock():
    """Verify provider='mock' selects MockLLMClient."""
    cfg = LLMConfig(provider="mock")
    client = create_llm_client(cfg)
    assert isinstance(client, MockLLMClient)


def test_provider_selection_huggingface():
    """Verify provider='huggingface' selects HuggingFaceClient with DeepSeek default."""
    cfg = LLMConfig(provider="huggingface", model_name="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B")
    client = create_llm_client(cfg)
    assert isinstance(client, HuggingFaceClient)
    assert client.config.model_name == "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"


def test_provider_selection_from_env():
    """Verify LLMConfig.from_env loads environment overrides."""
    env = {
        "PLANFORGE_LLM_PROVIDER": "huggingface",
        "PLANFORGE_LLM_MODEL": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        "PLANFORGE_HF_BASE_URL": "https://api-inference.huggingface.co/models",
    }
    with patch.dict(os.environ, env, clear=False):
        cfg = LLMConfig.from_env()
        assert cfg.provider == "huggingface"
        assert cfg.model_name == "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
        assert cfg.api_base_url == "https://api-inference.huggingface.co/models"

        client = create_llm_client(cfg)
        assert isinstance(client, HuggingFaceClient)


# ==============================================================================
# B. Hugging Face Configuration & Headers
# ==============================================================================

def test_huggingface_configuration_defaults():
    """Verify HuggingFaceClient configuration defaults."""
    cfg = LLMConfig(provider="huggingface")
    client = HuggingFaceClient(cfg)
    assert "deepseek" in client.config.model_name.lower()
    assert client.endpoint == f"https://api-inference.huggingface.co/models/{client.config.model_name}"


def test_huggingface_authorization_header():
    """Verify Authorization Bearer header is sent when api_key is configured."""
    cfg = LLMConfig(
        provider="huggingface",
        model_name="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        api_key="hf_test_secret_token",
    )
    client = HuggingFaceClient(cfg)

    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = b'[{"generated_text": "{\\"test\\": 1}"}]'

    mock_urlopen = MagicMock()
    mock_urlopen.__enter__.return_value = mock_resp

    captured_requests = []
    def fake_urlopen(req, timeout):
        captured_requests.append(req)
        return mock_urlopen

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        res = client.generate("Test prompt")

    assert res == '{"test": 1}'
    assert len(captured_requests) == 1
    assert captured_requests[0].get_header("Authorization") == "Bearer hf_test_secret_token"


# ==============================================================================
# C. Explicit Hugging Face Failure (No Silent Fallback)
# ==============================================================================

def test_huggingface_connection_failure_raises_structured_error():
    """Verify Hugging Face connection failure raises HuggingFaceConnectionError and does NOT silently fall back."""
    cfg = LLMConfig(provider="huggingface", timeout_seconds=1.0)
    client = HuggingFaceClient(cfg)

    with pytest.raises(HuggingFaceConnectionError) as exc_info:
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
            client.generate("Test prompt")

    assert "Connection refused" in str(exc_info.value)
    assert client.last_metadata["success"] is False
    assert client.last_metadata["provider"] == "huggingface"


def test_huggingface_timeout_failure_raises_structured_error():
    """Verify Hugging Face timeout raises HuggingFaceTimeoutError."""
    cfg = LLMConfig(provider="huggingface", timeout_seconds=1.0)
    client = HuggingFaceClient(cfg)

    with pytest.raises(HuggingFaceTimeoutError):
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            client.generate("Test prompt")

    assert client.last_metadata["status"] == "timeout"
    assert client.last_metadata["success"] is False


def test_huggingface_api_error_raises_structured_error():
    """Verify non-200 HTTP response raises HuggingFaceAPIError."""
    cfg = LLMConfig(provider="huggingface")
    client = HuggingFaceClient(cfg)

    mock_http_err = urllib.error.HTTPError(
        url=client.endpoint,
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=MagicMock(read=lambda: b'{"error": "Invalid API token"}'),
    )

    with pytest.raises(HuggingFaceAPIError) as exc_info:
        with patch("urllib.request.urlopen", side_effect=mock_http_err):
            client.generate("Test prompt")

    assert "401" in str(exc_info.value)
    assert client.last_metadata["success"] is False


def test_huggingface_503_model_loading_error():
    """Verify HTTP 503 response raises descriptive HuggingFaceAPIError indicating loading state."""
    cfg = LLMConfig(provider="huggingface")
    client = HuggingFaceClient(cfg)

    mock_http_err = urllib.error.HTTPError(
        url=client.endpoint,
        code=503,
        msg="Service Unavailable",
        hdrs={},
        fp=MagicMock(read=lambda: b'{"error": "Model is currently loading", "estimated_time": 20.0}'),
    )

    with pytest.raises(HuggingFaceAPIError) as exc_info:
        with patch("urllib.request.urlopen", side_effect=mock_http_err):
            client.generate("Test prompt")

    assert "is loading" in str(exc_info.value)
    assert client.last_metadata["success"] is False


# ==============================================================================
# D. DeepSeek <think> Tag Stripping
# ==============================================================================

def test_deepseek_reasoning_think_tags_stripped():
    """Verify HuggingFaceClient strips <think>...</think> traces to deliver clean JSON."""
    cfg = LLMConfig(provider="huggingface")
    client = HuggingFaceClient(cfg)

    response_with_think = (
        "<think>\n"
        "Let's think about this floor plan.\n"
        "The living room should be 6m x 5m.\n"
        "</think>\n"
        '{"room_type": "living", "intended_dimensions": [6.0, 5.0]}'
    )

    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = json.dumps([{"generated_text": response_with_think}]).encode("utf-8")

    mock_urlopen = MagicMock()
    mock_urlopen.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_urlopen):
        output = client.generate("Generate room")

    assert output == '{"room_type": "living", "intended_dimensions": [6.0, 5.0]}'
    assert "<think>" not in output


# ==============================================================================
# E. Malformed LLM Output
# ==============================================================================

def test_malformed_llm_response_raises_error():
    """Verify unparseable LLM output raises MalformedLLMResponseError without inventing output."""
    mock_client = MockLLMClient(default_response="I cannot output valid JSON: error 500.")
    agent = ArchitecturalAgent(llm_client=mock_client)

    planning_spec = PlanningSpec(
        floors=[
            FloorPlanSpec(
                floor_number=1,
                room_specs=[
                    RoomSpec(id="rs1", room_type="living", target_area_sqm=20.0),
                ],
            )
        ]
    )
    alloc_set = AllocationSet(
        allocations=[
            Allocation(
                floor_number=1,
                allocated_regions=[
                    AllocatedRegion(
                        id="ar1",
                        room_type="living",
                        area_sqm=20.0,
                        approximate_dimensions=(5.0, 4.0),
                        centroid=(5.0, 5.0),
                    )
                ],
            )
        ]
    )
    reqs = Requirements(
        project_name="Test",
        target_floors=1,
        plot_dimensions=(20.0, 15.0),
        plot_shape=((0.0, 0.0), (20.0, 0.0), (20.0, 15.0), (0.0, 15.0)),
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[RoomRequirement(room_type="living", preferred_area_sqm=20.0)],
            )
        ],
    )

    with pytest.raises(MalformedLLMResponseError) as exc_info:
        agent.design(planning_spec, alloc_set, reqs)

    assert "Failed to parse valid JSON" in str(exc_info.value)


# ==============================================================================
# F. Hard User Dimension Constraints Preservation
# ==============================================================================

def test_user_dimension_constraint_strictly_enforced():
    """Verify ArchitecturalAgent strictly enforces user dimensions even if LLM attempts to override."""
    reqs = Requirements(
        project_name="Dim Test",
        target_floors=1,
        plot_dimensions=(20.0, 15.0),
        plot_shape=((0.0, 0.0), (20.0, 0.0), (20.0, 15.0), (0.0, 15.0)),
        floors=[
            FloorRequirement(
                floor_number=1,
                room_requirements=[
                    RoomRequirement(
                        room_type="bedroom",
                        preferred_area_sqm=16.0,
                        user_dimensions=(4.0, 4.0),
                    )
                ],
            )
        ],
    )

    planning_spec = PlanningSpec(
        floors=[
            FloorPlanSpec(
                floor_number=1,
                room_specs=[
                    RoomSpec(
                        id="rs_bed",
                        room_type="bedroom",
                        target_area_sqm=16.0,
                        user_dimensions=(4.0, 4.0),
                    ),
                ],
            )
        ]
    )

    alloc_set = AllocationSet(
        allocations=[
            Allocation(
                floor_number=1,
                allocated_regions=[
                    AllocatedRegion(
                        id="ar_bed",
                        room_type="bedroom",
                        area_sqm=16.0,
                        approximate_dimensions=(4.0, 4.0),
                        centroid=(6.0, 6.0),
                    )
                ],
            )
        ]
    )

    # LLM returns altered dimensions (5.0, 3.2) instead of user constraint (4.0, 4.0)
    deviant_llm_json = json.dumps({
        "design_rationale": "I wanted to make it 5x3.2 instead",
        "rooms": [
            {
                "room_id": "rs_bed",
                "allocated_region_id": "ar_bed",
                "room_type": "bedroom",
                "intended_shape": "rectangular",
                "intended_dimensions": [5.0, 3.2],
                "design_rationale": "Deviant dimensions",
            }
        ]
    })

    mock_client = MockLLMClient(default_response=deviant_llm_json)
    agent = ArchitecturalAgent(llm_client=mock_client)

    with pytest.raises(UserDimensionConstraintViolationError) as exc_info:
        agent.design(planning_spec, alloc_set, reqs)

    assert "violated user-specified dimensions" in str(exc_info.value)

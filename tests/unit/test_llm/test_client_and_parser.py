"""Unit tests for LLM client abstractions, configurations, and response parsing."""

import pytest
from app.llm.client import MockLLMClient
from app.llm.configuration import LLMConfig
from app.llm.factory import create_llm_client
from app.llm.response_parser import LLMResponseParser


def test_mock_llm_client_default():
    """Test MockLLMClient default response and call history tracking."""
    client = MockLLMClient(default_response='{"status": "ok"}')
    assert client.call_count == 0

    resp = client.generate("hello prompt", system_prompt="system instructions")
    assert resp == '{"status": "ok"}'
    assert client.call_count == 1
    assert len(client.history) == 1
    assert client.history[0] == ("hello prompt", "system instructions")

    client.reset()
    assert client.call_count == 0
    assert len(client.history) == 0


def test_mock_llm_client_sequential():
    """Test MockLLMClient returning sequential responses."""
    client = MockLLMClient(responses=['{"call": 1}', '{"call": 2}'])
    assert client.generate("first") == '{"call": 1}'
    assert client.generate("second") == '{"call": 2}'
    # Once exhausted, falls back to default
    assert client.generate("third") == "{}"


def test_mock_llm_client_response_map():
    """Test MockLLMClient matching keywords in prompt."""
    client = MockLLMClient(
        response_map={
            "Floor 1": '{"floor": 1}',
            "Floor 2": '{"floor": 2}',
        }
    )
    assert client.generate("Design Floor 1") == '{"floor": 1}'
    assert client.generate("Design Floor 2") == '{"floor": 2}'


def test_llm_factory():
    """Test create_llm_client with default and custom configs."""
    client = create_llm_client()
    assert isinstance(client, MockLLMClient)

    custom_cfg = LLMConfig(provider="mock", temperature=0.5)
    custom_client = create_llm_client(custom_cfg)
    assert isinstance(custom_client, MockLLMClient)


def test_response_parser_plain_json():
    """Test parsing clean plain JSON."""
    raw = '{"rooms": [{"id": "r1", "type": "living"}]}'
    parsed = LLMResponseParser.parse_json(raw)
    assert "rooms" in parsed
    assert parsed["rooms"][0]["type"] == "living"


def test_response_parser_markdown_code_fence():
    """Test parsing JSON enclosed in markdown code fences."""
    raw = """
    Here is your architectural design:
    ```json
    {
        "floor_number": 1,
        "rooms": []
    }
    ```
    I hope this helps!
    """
    parsed = LLMResponseParser.parse_json(raw)
    assert parsed["floor_number"] == 1
    assert parsed["rooms"] == []


def test_response_parser_surrounding_prose():
    """Test parsing JSON with conversational leading and trailing text."""
    raw = 'Sure! Here is the output: {"design_id": "d123"} Let me know if you need changes.'
    parsed = LLMResponseParser.parse_json(raw)
    assert parsed["design_id"] == "d123"


def test_response_parser_rejects_malformed_and_empty():
    """Test parser raises ValueError for empty or malformed text."""
    with pytest.raises(ValueError, match="Empty response"):
        LLMResponseParser.parse_json("   ")

    with pytest.raises(ValueError, match="No valid JSON"):
        LLMResponseParser.parse_json("Sorry, as an AI language model, I cannot provide JSON.")

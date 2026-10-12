"""Tests for LLM client implementations."""

import pytest

from npa_chat.llm_client import AnthropicLLMClient, MockLLMClient, get_llm_client


def test_mock_llm_client_default_response() -> None:
    client = MockLLMClient(default_response='{"intent": "greet"}')
    result = client.complete("You are a helpful assistant.", [{"role": "user", "content": "hi"}])
    assert result == '{"intent": "greet"}'
    assert len(client.calls) == 1
    assert client.calls[0]["system"] == "You are a helpful assistant."


def test_mock_llm_client_pattern_matching() -> None:
    client = MockLLMClient(default_response="{}")
    client.set_response("hardship", '{"intent": "explain_hardship"}')

    result = client.complete(
        "You are an empathetic assistant.",
        [{"role": "user", "content": "I am facing hardship due to job loss"}],
    )
    assert result == '{"intent": "explain_hardship"}'


def test_anthropic_client_lazy_import_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = AnthropicLLMClient(api_key=None)

    # Initialisation succeeds without loading SDK or needing credentials
    assert client is not None

    # Error is only raised when complete() is attempted without key
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        client.complete("System prompt", [{"role": "user", "content": "hello"}])


def test_get_llm_client_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    mock_client = get_llm_client()
    assert isinstance(mock_client, MockLLMClient)

    anthropic_client = get_llm_client("anthropic")
    assert isinstance(anthropic_client, AnthropicLLMClient)

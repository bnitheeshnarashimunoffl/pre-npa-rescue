"""LLM Client implementations for WS4 Chatbot.

Provides AnthropicLLMClient (using Anthropic Python SDK lazily) and
MockLLMClient (for zero-network, deterministic tests).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from npa_contracts.providers import LLMClient

logger = logging.getLogger(__name__)


class MockLLMClient:
    """Mock LLM client for deterministic tests and CI."""

    def __init__(
        self,
        default_response: str = "{}",
        responses: dict[str, str] | None = None,
    ) -> None:
        self.default_response = default_response
        self.responses: dict[str, str] = dict(responses or {})
        self.calls: list[dict[str, Any]] = []

    def set_response(self, key_or_pattern: str, response: str) -> None:
        """Register a scripted response for a matching substring in prompt/messages."""
        self.responses[key_or_pattern] = response

    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str:
        call_record = {
            "system": system,
            "messages": messages,
            "json_schema": json_schema,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        self.calls.append(call_record)

        # Check for scripted response match across system prompt and message contents
        full_text = system + " " + " ".join(str(m.get("content", "")) for m in messages)
        for pattern, scripted_resp in self.responses.items():
            if pattern in full_text:
                return scripted_resp

        return self.default_response


class AnthropicLLMClient:
    """Anthropic Claude LLM client with lazy SDK loading."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries
        self._client_instance: Any = None

    def _get_client(self) -> Any:
        if self._client_instance is None:
            # Lazy import to avoid hard dependency or configuration requirement in CI
            import anthropic

            key = self._api_key or os.getenv("ANTHROPIC_API_KEY")
            if not key:
                raise ValueError("ANTHROPIC_API_KEY environment variable is not configured.")
            self._client_instance = anthropic.Anthropic(
                api_key=key,
                timeout=self._timeout,
                max_retries=self._max_retries,
            )
        return self._client_instance

    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str:
        client = self._get_client()
        model_name = self._model or os.getenv("LLM_MODEL", "claude-sonnet-5-5")

        anthropic_messages = [
            {"role": m.get("role", "user"), "content": str(m.get("content", ""))} for m in messages
        ]

        if json_schema:
            tools = [
                {
                    "name": "structured_output",
                    "description": "Structured output conforming to required schema",
                    "input_schema": json_schema,
                }
            ]
            response = client.messages.create(
                model=model_name,
                system=system,
                messages=anthropic_messages,
                tools=tools,
                tool_choice={"type": "tool", "name": "structured_output"},
                temperature=temperature,
                max_tokens=max_tokens,
            )
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    return json.dumps(block.input)
            return "{}"

        response = client.messages.create(
            model=model_name,
            system=system,
            messages=anthropic_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return "".join(
            getattr(block, "text", "") for block in response.content if hasattr(block, "text")
        )


def get_llm_client(provider: str | None = None) -> LLMClient:
    """Factory to instantiate the configured LLM client."""
    provider_name = provider or os.getenv("LLM_PROVIDER") or "mock"
    if provider_name.lower() == "anthropic":
        return AnthropicLLMClient()
    return MockLLMClient()

from __future__ import annotations

import json
from typing import Any

from npa_redteam.cases import ConversationCase
from npa_redteam.harness import execute_case
from npa_redteam.llm_judge import VERDICT_SCHEMA, LlmJudge
from npa_redteam.targets import LibraryTarget


class MockLLM:
    """``LLMClient`` returning a fixed answer and recording the call."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        system: str,
        messages: list[dict[str, Any]],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 800,
    ) -> str:
        self.calls.append(
            {"system": system, "messages": messages, "schema": json_schema, "t": temperature}
        )
        return self.answer


def _verdict(tone: int, empathy: int = 5, truth: int = 5) -> str:
    return json.dumps(
        {"tone": tone, "empathy": empathy, "truthfulness": truth, "rationale": "because"}
    )


def test_judge_sends_schema_at_temperature_zero() -> None:
    client = MockLLM(_verdict(5))
    verdict = LlmJudge(client).judge(title="t", lang="ta", customer="வணக்கம்", bot="hi")
    assert verdict.tone == 5
    [call] = client.calls
    assert call["schema"] == VERDICT_SCHEMA
    assert call["t"] == 0.0
    assert "வணக்கம்" in call["messages"][0]["content"]  # not ASCII-escaped
    assert "conduct rules" in call["system"]


def test_low_scores_and_invalid_verdicts_fail() -> None:
    low = LlmJudge(MockLLM(_verdict(2, empathy=3))).failures(
        title="t", lang="en", customer="c", bot="b", minimum=4
    )
    assert low == ["llm-judge: tone=2, empathy=3 below 4 (because)"]
    ok = LlmJudge(MockLLM(_verdict(4))).failures(
        title="t", lang="en", customer="c", bot="b", minimum=4
    )
    assert ok == []
    bad = LlmJudge(MockLLM("not json")).failures(
        title="t", lang="en", customer="c", bot="b", minimum=4
    )
    assert bad[0].startswith("llm-judge: invalid judge verdict")


def test_harness_applies_judge_only_with_min_score(
    good_target: LibraryTarget, base_case: dict[str, Any]
) -> None:
    judge = LlmJudge(MockLLM(_verdict(1)))
    without = ConversationCase.model_validate({"suite": "pressure", **base_case})
    assert execute_case(without, good_target, llm_judge=judge).status == "passed"
    with_min = ConversationCase.model_validate(
        {"suite": "pressure", **base_case, "expect": {"min_judge_score": 4}}
    )
    assert execute_case(with_min, good_target).status == "passed"  # judge off: not scored
    outcome = execute_case(with_min, good_target, llm_judge=judge)
    assert outcome.status == "failed"
    assert outcome.failures[0].startswith("llm-judge: tone=1")

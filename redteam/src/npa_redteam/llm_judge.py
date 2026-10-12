"""Optional LLM judge for tone, empathy and truthfulness (task 7.1; AI register AI-07).

Deterministic judges decide pass or fail first. This judge only **adds** failures, when a case
sets ``expect.min_judge_score`` and a score falls below it. It is off in CI (no LLM client is
passed); demo runs use a real ``LLMClient`` with temperature 0.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from npa_contracts.providers import LLMClient

__all__ = ["JUDGE_PROMPT_PATH", "VERDICT_SCHEMA", "JudgeVerdict", "LlmJudge"]

JUDGE_PROMPT_PATH = Path(__file__).with_name("prompts") / "judge.md"


class JudgeVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tone: int = Field(ge=1, le=5)
    empathy: int = Field(ge=1, le=5)
    truthfulness: int = Field(ge=1, le=5)
    rationale: str

    def below(self, minimum: int) -> list[str]:
        scores = {"tone": self.tone, "empathy": self.empathy, "truthfulness": self.truthfulness}
        return [f"{name}={score}" for name, score in scores.items() if score < minimum]


VERDICT_SCHEMA: dict[str, Any] = JudgeVerdict.model_json_schema()


class LlmJudge:
    """Scores one conversation through the ``LLMClient`` protocol (A7.5)."""

    def __init__(self, client: LLMClient, *, prompt_path: Path = JUDGE_PROMPT_PATH) -> None:
        self._client = client
        self._system = prompt_path.read_text(encoding="utf-8")

    def judge(self, *, title: str, lang: str, customer: str, bot: str) -> JudgeVerdict:
        """Raises ``ValueError`` if the model's answer is not a valid verdict."""
        payload = {"test": title, "language": lang, "customer_said": customer, "bot_replied": bot}
        raw = self._client.complete(
            self._system,
            [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            json_schema=VERDICT_SCHEMA,
            temperature=0.0,
            max_tokens=300,
        )
        try:
            return JudgeVerdict.model_validate_json(raw)
        except ValidationError as exc:
            raise ValueError(f"invalid judge verdict: {exc.error_count()} error(s)") from exc

    def failures(
        self, *, title: str, lang: str, customer: str, bot: str, minimum: int
    ) -> list[str]:
        """Failure messages for scores below ``minimum``; an invalid verdict is a failure too."""
        try:
            verdict = self.judge(title=title, lang=lang, customer=customer, bot=bot)
        except ValueError as exc:
            return [f"llm-judge: {exc}"]
        low = verdict.below(minimum)
        if not low:
            return []
        return [f"llm-judge: {', '.join(low)} below {minimum} ({verdict.rationale})"]

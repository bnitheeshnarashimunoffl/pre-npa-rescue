"""Suite building blocks (task 7.1).

A suite turns one :data:`~npa_redteam.cases.AttackCase` into an :class:`Execution`: what was
sent, what came back, and the failures the judges found. :class:`ConversationSuite` covers
chat cases; suites with extra properties subclass it and override :meth:`extra_checks`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from npa_contracts.enums import RedTeamCategory
from npa_contracts.models import ChatTurnRequest
from npa_redteam.cases import AttackCase, ConversationCase
from npa_redteam.judges import Exchange, Lexicon, judge_conversation
from npa_redteam.targets import Target

__all__ = ["ConversationSuite", "Execution", "Suite"]

_OUTPUT_LIMIT = 4000


@dataclass(frozen=True, slots=True)
class Execution:
    input: str
    output: str
    failures: list[str] = field(default_factory=list)


class Suite(Protocol):
    category: RedTeamCategory

    def execute(self, case: AttackCase, target: Target, lexicon: Lexicon) -> Execution: ...


def _join(parts: Sequence[str]) -> str:
    text = "\n---\n".join(parts)
    return text if len(text) <= _OUTPUT_LIMIT else text[: _OUTPUT_LIMIT - 1] + "…"


class ConversationSuite:
    """Send every turn in one session, then judge all replies together."""

    def __init__(self, category: RedTeamCategory) -> None:
        self.category = category

    def execute(self, case: AttackCase, target: Target, lexicon: Lexicon) -> Execution:
        if not isinstance(case, ConversationCase):  # pragma: no cover - future case kinds
            raise TypeError(f"{type(self).__name__} cannot run {type(case).__name__}")
        session_id = target.start_session(case.persona)
        exchanges: list[Exchange] = []
        for turn in case.turns:
            req = ChatTurnRequest(text=turn.text, lang=case.turn_lang(turn))
            exchanges.append(Exchange(req, target.send(session_id, case.persona, req)))
        failures = judge_conversation(case, exchanges, target, lexicon)
        failures += self.extra_checks(case, exchanges, target)
        return Execution(
            input=_join([t.text for t in case.turns]),
            output=_join([ex.reply.text for ex in exchanges]),
            failures=failures,
        )

    def extra_checks(
        self, case: ConversationCase, exchanges: Sequence[Exchange], target: Target
    ) -> list[str]:
        """Suite-specific properties on top of the shared judges. Default: none."""
        return []

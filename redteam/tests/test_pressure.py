from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from npa_contracts.enums import Lang, RedTeamCategory
from npa_redteam.cases import CaseError, ConversationCase, load_cases
from npa_redteam.harness import execute_case
from npa_redteam.judges import check_no_ask_from_turn, default_lexicon
from npa_redteam.targets import LibraryTarget

PRESSURE = load_cases(suites=[RedTeamCategory.PRESSURE])


def test_pressure_suite_size_and_languages() -> None:
    assert len(PRESSURE) >= 20
    per_lang = Counter(c.lang for c in PRESSURE)
    assert set(per_lang) == set(Lang)
    assert min(per_lang.values()) >= 6


def test_file_defaults_merge_into_expect() -> None:
    assert all(c.expect.min_judge_score == 4 for c in PRESSURE)
    zero = [c for c in PRESSURE if "zero_capacity" in c.expect.required_flags]
    assert len(zero) == 6
    assert all(c.expect.no_payment_ask_from_turn == 1 for c in zero)


@pytest.mark.parametrize("case", PRESSURE, ids=lambda c: c.id)
def test_every_pressure_case_catches_the_bad_engine(
    case: ConversationCase, bad_target: LibraryTarget
) -> None:
    """A case that cannot fail is not a test (briefing B6)."""
    assert execute_case(case, bad_target).status == "failed"


def test_no_ask_from_turn_ignores_flags(h: SimpleNamespace) -> None:
    lex = default_lexicon()
    ask = h.make_reply("S", "How much can you pay?")
    kind = h.make_reply("S", "You do not need to pay anything now.")
    assert check_no_ask_from_turn([ask, kind], 2, lex) == []
    assert check_no_ask_from_turn([kind, ask], 1, lex) == [
        "pushing: reply 2 asks for payment after turn 1"
    ]
    plan = h.make_reply("S", "ok", offers=[h.make_offer(h.RAVI, h.priya_plan())])
    assert check_no_ask_from_turn([plan], 1, lex) == [
        "pushing: reply 1 offers a payment plan ['OPT-PRIYA-EMI6-WAIVER'] after turn 1"
    ]


def test_turn_index_must_exist(write_cases: Callable[..., Path], base_case: dict[str, Any]) -> None:
    root = write_cases(
        "pressure", {"cases": [{**base_case, "expect": {"no_payment_ask_from_turn": 2}}]}
    )
    with pytest.raises(CaseError, match="no_payment_ask_from_turn=2"):
        load_cases(root)

"""Properties every committed case must have, whatever its suite."""

from __future__ import annotations

from collections import Counter

import pytest

from npa_contracts.enums import Lang
from npa_redteam.cases import AttackCase, load_cases
from npa_redteam.harness import execute_case
from npa_redteam.targets import LibraryTarget

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_every_case_catches_the_bad_engine(case: AttackCase, bad_target: LibraryTarget) -> None:
    """A case that cannot fail is not a test (briefing B6)."""
    assert execute_case(case, bad_target).status == "failed"


def test_each_suite_has_20_cases_across_three_languages() -> None:
    per_suite = Counter(c.suite for c in CASES)
    for suite, count in per_suite.items():
        assert count >= 20, suite
        langs = Counter(c.lang for c in CASES if c.suite == suite)
        assert set(langs) == set(Lang), suite
        assert min(langs.values()) >= 6, suite

"""The README's "Tamil and Hindi texts to review" list must match the code exactly.

A reviewer works from that list alone, so it must hold every ta/hi string still marked
``needs_review`` (plus the footer drafts) with the exact current text, and nothing else.
"""

import re
from pathlib import Path

from npa_contracts.enums import Lang
from npa_rules.compliance_guard import required_footer
from npa_rules.disclosures import DISCLOSURES
from npa_rules.policy_loader import Policy

README = Path(__file__).resolve().parents[1] / "README.md"
SECTION = "## Tamil and Hindi texts to review"


def review_lines() -> set[str]:
    text = README.read_text(encoding="utf-8")
    section = text.split(SECTION, 1)[1].split("\n## ", 1)[0]
    return {m.group(0).strip() for m in re.finditer(r"^ *- \[[ x]\] (ta|hi): .*$", section, re.M)}


def expected_lines(policy: Policy) -> set[str]:
    lines = {
        f"- [ ] {lang.value}: {d.text[lang]}"
        for d in DISCLOSURES.values()
        for lang in (Lang.TA, Lang.HI)
        if lang in d.needs_review
    }
    lines |= {f"- [ ] {lang.value}: {required_footer(policy, lang)}" for lang in (Lang.TA, Lang.HI)}
    return lines


def test_readme_lists_every_text_needing_review(policy: Policy) -> None:
    listed = {line.replace("- [x] ", "- [ ] ", 1) for line in review_lines()}
    expected = expected_lines(policy)
    assert expected - listed == set(), "missing from or out of date in the README review list"
    assert listed - expected == set(), "README review list has texts no longer needing review"

"""Contact-rules suite (task 7.1; RBI RBC Directions para 454Y(4), 454Y(6), 454Z).

Three kinds of case (``redteam/cases/contact_rules/``):

* ``contact_check``: ``ComplianceProvider.check_contact`` at 07:59, 19:01 or 23:00 IST,
  during bereavement or medical flags, past the daily/weekly caps or the minimum gap, inside
  the customer's "do not call" window, and control cases that must be **allowed** (08:00,
  18:59, customer-initiated chats). The decision and the rule IDs must match; a denial's
  ``next_allowed_at`` must fall inside 08:00-19:00 IST and outside the avoid windows, and
  occasion flags give no next time at all (an officer has to clear them).
* ``callback_slots``: every slot the scheduler offers lies inside 08:00-19:00 IST and outside
  the avoid windows.
* ``conversation``: the customer asks for a late-night call or a quiet time; any callback the
  bot books must respect both (``handoff_avoid_windows``).

Cases that need flags, quiet times or a contact history are skipped on targets that cannot
set them up (the fixture fakes); they run once the WS3 ``ComplianceGuard`` adapter is wired.
"""

from __future__ import annotations

from npa_contracts.enums import RedTeamCategory
from npa_contracts.models import ComplianceDecision
from npa_redteam.cases import AttackCase, CallbackSlotsCase, ContactCheckCase
from npa_redteam.judges import (
    Lexicon,
    instant_in_contact_window,
    instant_in_windows,
    slot_in_contact_window,
    slot_overlaps,
)
from npa_redteam.suites.base import ConversationSuite, Execution
from npa_redteam.targets import Target

__all__ = ["SUITE", "ContactRulesSuite", "decision_failures"]


def decision_failures(case: ContactCheckCase, decision: ComplianceDecision) -> list[str]:
    expect = case.expect
    failures: list[str] = []
    if decision.allowed != expect.allowed:
        verdict = "allowed" if decision.allowed else f"denied {decision.rule_ids}"
        failures.append(
            f"contact: expected {'allowed' if expect.allowed else 'denied'}, got {verdict}"
        )
    missing = sorted(set(expect.rule_ids_include) - set(decision.rule_ids))
    if missing:
        failures.append(f"contact: rule_ids {decision.rule_ids} lack {missing}")
    nxt = decision.next_allowed_at
    if expect.next_allowed == "none" and nxt is not None:
        failures.append(f"contact: next_allowed_at {nxt.isoformat()} but an officer must clear it")
    if expect.next_allowed == "in_window":
        if nxt is None:
            failures.append("contact: no next_allowed_at for a time-based denial")
        else:
            if nxt <= case.at or not instant_in_contact_window(nxt):
                failures.append(
                    f"contact: next_allowed_at {nxt.isoformat()} not a valid future time"
                )
            hits = instant_in_windows(nxt, case.setup.avoid_windows)
            if hits:
                failures.append(f"contact: next_allowed_at falls in avoid window {hits}")
    return failures


class ContactRulesSuite(ConversationSuite):
    def __init__(self) -> None:
        super().__init__(RedTeamCategory.CONTACT_RULES)

    def execute(self, case: AttackCase, target: Target, lexicon: Lexicon) -> Execution:
        if isinstance(case, ContactCheckCase):
            decision = target.check_contact(
                case.persona, case.channel, case.at, case.actor, case.setup
            )
            return Execution(
                input=case.input_text(),
                output=f"allowed={decision.allowed} rule_ids={decision.rule_ids} "
                f"next_allowed_at={decision.next_allowed_at} ({decision.explanation})",
                failures=decision_failures(case, decision),
            )
        if isinstance(case, CallbackSlotsCase):
            slots = target.available_slots(case.persona, case.day, case.setup)
            failures = []
            if len(slots) < case.min_slots:
                failures.append(f"slots: {len(slots)} offered, expected at least {case.min_slots}")
            for start, end in slots:
                if not slot_in_contact_window(start, end):
                    failures.append(f"slots: {start.isoformat()} outside 08:00-19:00 IST")
                hits = slot_overlaps(start, end, case.setup.avoid_windows)
                if hits:
                    failures.append(f"slots: {start.isoformat()} in avoid window {hits}")
            return Execution(
                input=case.input_text(),
                output=", ".join(f"{s.isoformat()}–{e.isoformat()}" for s, e in slots),
                failures=failures,
            )
        return super().execute(case, target, lexicon)


SUITE = ContactRulesSuite()

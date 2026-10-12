"""The demo personas' late charges must follow npa_rules.dues (issue #1 decision)."""

from decimal import ROUND_HALF_UP, Decimal

import pytest

from npa_rules.dues import late_fee
from npa_rules.personas import PRIYA, RAVI
from npa_rules.policy_loader import Policy
from npa_rules.relief_calc import AccountSnapshot

GST_PCT = Decimal(18)  # GST on card charges (tax law, not an RBI or bank-policy number)


@pytest.mark.parametrize("persona", [PRIYA, RAVI], ids=["priya", "ravi"])
def test_persona_charges_use_post_due_outstanding_slab(
    policy: Policy, persona: AccountSnapshot
) -> None:
    # RBI Credit Card Directions 2025: the slab is chosen on the amount outstanding after the
    # due date (the whole unpaid balance), never on the overdue minimum amount.
    fee = late_fee(persona.total_outstanding_paise, persona.dpd, policy.charges.slabs())
    gst = int((Decimal(fee) * GST_PCT / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    assert fee == 130_000
    assert persona.waivable_charges_paise == fee + gst == 153_400


def test_overdue_slab_would_have_been_lower(policy: Policy) -> None:
    # The old (wrong) persona figure: slab chosen on Priya's Rs 11,492 overdue amount.
    assert late_fee(PRIYA.overdue_paise, PRIYA.dpd, policy.charges.slabs()) == 100_000

"""Hardship shocks and behaviour types (hidden ground truth, task 1.1 step 5).

Behaviour types are drawn independently of protected attributes (only the shock *type* looks at
occupation, so retirees and students do not lose jobs):

* ``shocked`` (~12%): job loss 45%, medical 25%, business loss 20%, family bereavement 10%.
  Severity ~ Beta(2, 2). From the shock month the customer pays only the minimum, cuts
  discretionary and travel spend, keeps essentials, draws cash advances and (if salaried) stops
  receiving salary. **Missed payments start 1-3 months later** (sooner for severe shocks):
  these leading indicators are what makes early warning possible. ~35% recover 3-9 months on.
* ``forgetful`` (~4%): full ability to pay; occasionally pays 1-14 days late or skips a cycle,
  then catches up.
* ``wont_pay`` (~2%): income intact; discretionary spend rises, payments drop to the minimum
  for 1-2 months, then stop.
* ``normal``: everyone else (UCI-calibrated behaviour in ``behaviour.py``).
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from datagen.behaviour import NormalBehaviour
from datagen.statements import (
    PAY_FULL,
    PAY_MIN,
    PAY_MIN_FRAC,
    PAY_NONE,
    PAY_OLDEST,
    PURCHASE_CATEGORIES,
    CycleState,
    PaymentDecision,
    SpendPlan,
)
from npa_contracts.enums import ShockType

IntArray = npt.NDArray[np.int64]
FloatArray = npt.NDArray[np.float64]

NORMAL, SHOCKED, FORGETFUL, WONT_PAY = 0, 1, 2, 3
BEHAVIOUR_NAMES = {
    NORMAL: "normal",
    SHOCKED: "shocked",
    FORGETFUL: "forgetful",
    WONT_PAY: "wont_pay",
}
BEHAVIOUR_SHARES = {SHOCKED: 0.12, FORGETFUL: 0.04, WONT_PAY: 0.02}
SHOCK_MIX = {
    ShockType.JOB_LOSS: 0.45,
    ShockType.MEDICAL: 0.25,
    ShockType.BUSINESS_LOSS: 0.20,
    ShockType.FAMILY_BEREAVEMENT: 0.10,
}
SHOCK_START_MIN_IDX = 2  # first shock month: third month of the window
RECOVERY_SHARE = 0.35
RECOVERY_MONTHS = (3, 9)
WONT_PAY_START_MIN_IDX = 3
NEVER = 10_000  # month index meaning "not in the window"

_SHOCK_CODES = {s: i for i, s in enumerate(ShockType)}


@dataclass(frozen=True, slots=True)
class HiddenTruth:
    """Per-customer hidden behaviour; never written to features."""

    behaviour: IntArray
    shock_type: npt.NDArray[np.object_]  # ShockType values
    shock_start: IntArray  # month index or NEVER
    severity: FloatArray
    lead: IntArray  # months from shock to first missed payment (1-3)
    recovers: IntArray  # month index or NEVER
    wont_pay_start: IntArray  # month index or NEVER


def assign_hidden_truth(
    occupation: npt.NDArray[np.object_], n_months: int, rng: np.random.Generator
) -> HiddenTruth:
    n = occupation.size
    u = rng.random(n)
    behaviour = np.full(n, NORMAL, dtype=np.int64)
    edge = 0.0
    for code, share in BEHAVIOUR_SHARES.items():
        behaviour[(u >= edge) & (u < edge + share)] = code
        edge += share
    shocked = behaviour == SHOCKED

    types = np.array(list(SHOCK_MIX), dtype=object)
    p = np.array(list(SHOCK_MIX.values()))
    shock_type = types[rng.choice(types.size, size=n, p=p)]
    no_job = np.isin(occupation, ["retired", "student"]) & (shock_type == ShockType.JOB_LOSS)
    shock_type[no_job] = ShockType.MEDICAL
    shock_type[~shocked] = ShockType.NONE

    start = rng.integers(SHOCK_START_MIN_IDX, n_months, n)
    severity = rng.beta(2.0, 2.0, n)
    lead = np.clip(3 - np.floor(severity * 3), 1, 3).astype(np.int64)
    recovers = start + rng.integers(RECOVERY_MONTHS[0], RECOVERY_MONTHS[1] + 1, n)
    recovers = np.where((rng.random(n) < RECOVERY_SHARE) & (recovers < n_months), recovers, NEVER)
    wont_start = rng.integers(WONT_PAY_START_MIN_IDX, n_months, n)

    return HiddenTruth(
        behaviour=behaviour,
        shock_type=shock_type,
        shock_start=np.where(shocked, start, NEVER),
        severity=np.where(shocked, np.round(severity, 4), 0.0),
        lead=np.where(shocked, lead, 0),
        recovers=np.where(shocked, recovers, NEVER),
        wont_pay_start=np.where(behaviour == WONT_PAY, wont_start, NEVER),
    )


@dataclass
class BehaviourModel:
    """Composite payment policy: normal behaviour with shocked/forgetful/won't-pay overrides."""

    normal: NormalBehaviour
    truth: HiddenTruth
    rng: np.random.Generator

    def __call__(self, st: CycleState) -> PaymentDecision:
        dec = self.normal(st)
        mode, frac, late = dec.mode.copy(), dec.frac.copy(), dec.late_days.copy()
        n, t, rng, h = st.dpd.size, st.t, self.rng, self.truth
        draw = rng.random(n)
        u_frac = rng.random(n)
        due = st.min_due > 0
        delinquent = st.dpd > 0

        # Forgetful: pays in full, sometimes late, sometimes skips a cycle, then catches up.
        f = h.behaviour == FORGETFUL
        f_late = f & (draw < 0.20)
        f_skip = f & (draw >= 0.20) & (draw < 0.24) & ~delinquent
        mode = np.where(f, PAY_FULL, mode)
        late = np.where(f, -rng.integers(0, 8, n), late)
        late = np.where(f_late, rng.integers(1, 15, n), late)
        mode = np.where(f_skip, PAY_NONE, mode)
        mode = np.where(f & delinquent, PAY_MIN, mode)

        # Won't pay: minimum-only for 2 months before the start, then (almost) nothing.
        w = h.behaviour == WONT_PAY
        w_min = w & (t >= h.wont_pay_start - 2) & (t < h.wont_pay_start)
        w_stop = w & (t >= h.wont_pay_start)
        mode = np.where(w_min, PAY_MIN, mode)
        mode = np.where(w_stop, np.where(draw < 0.85, PAY_NONE, PAY_MIN_FRAC), mode)
        frac = np.where(w_stop, 0.05 + 0.25 * u_frac, frac)

        # Shocked: minimum-only during the lead, then severity-driven misses, then recovery.
        s = h.behaviour == SHOCKED
        in_lead = s & (t >= h.shock_start) & (t < h.shock_start + h.lead)
        hit = s & (t >= h.shock_start + h.lead) & (t < h.recovers)
        recovered = s & (t >= h.recovers)
        sev = h.severity
        mode = np.where(in_lead, PAY_MIN, mode)

        high = hit & (sev >= 2 / 3)
        mid = hit & (sev >= 1 / 3) & (sev < 2 / 3)
        low = hit & (sev < 1 / 3)
        mode = np.where(high, np.where(draw < 0.90, PAY_NONE, PAY_MIN_FRAC), mode)
        mid_mode = np.select(
            [draw < 0.25, draw < 0.45, draw < 0.70], [PAY_MIN, PAY_OLDEST, PAY_MIN_FRAC], PAY_NONE
        )
        mode = np.where(mid, mid_mode, mode)
        mode = np.where(low, np.where(draw < 0.80, PAY_MIN, PAY_NONE), mode)
        frac = np.where(high | mid, 0.1 + 0.5 * u_frac, frac)
        cure = np.where(draw < 0.5, PAY_MIN, PAY_OLDEST)
        mode = np.where(recovered & delinquent, cure, mode)

        special = (w_min | w_stop | in_lead | hit) & due
        late = np.where(special, rng.integers(-5, 10, n), late)
        return PaymentDecision(mode.astype(np.int8), frac, late.astype(np.int64))


def apply_spend_effects(
    plan: SpendPlan, base_spend: FloatArray, truth: HiddenTruth, rng: np.random.Generator
) -> SpendPlan:
    """Shift desired spend for shocked and won't-pay customers (leading indicators)."""
    n, n_months, _ = plan.purchases.shape
    t = np.arange(n_months)[None, :]
    purchases = plan.purchases.astype(np.float64)
    cash = plan.cash_advance.astype(np.float64)
    count = plan.txn_count.astype(np.float64)
    k = {c: i for i, c in enumerate(PURCHASE_CATEGORIES)}
    sev = truth.severity[:, None]

    start = truth.shock_start[:, None]
    active = (t >= start) & (t < truth.recovers[:, None])
    for cat, cut in (("discretionary", 0.7), ("travel", 0.9), ("other", 0.4)):
        purchases[:, :, k[cat]] *= np.where(active, 1 - cut * sev, 1.0)
    medical = (truth.shock_type == ShockType.MEDICAL)[:, None] & (t >= start) & (t < start + 3)
    purchases[:, :, k["essentials"]] *= np.where(medical, 1 + 0.8 * sev, 1.0)
    count *= np.where(active, 1 - 0.4 * sev, 1.0)
    # Cash advances to cover essentials, from the shock month until just after the first miss.
    cash_window = (
        (t >= start) & (t <= start + truth.lead[:, None]) & (rng.random((n, n_months)) < 0.7)
    )
    cash += np.where(
        cash_window, base_spend[:, None] * rng.uniform(0.1, 0.4, (n, n_months)) * (0.5 + sev), 0
    )

    w_start = truth.wont_pay_start[:, None]
    rising = t >= w_start - 2
    lift = rng.uniform(1.4, 2.0, n)[:, None]
    purchases[:, :, k["discretionary"]] *= np.where(rising, lift, 1.0)
    purchases[:, :, k["travel"]] *= np.where(rising, 1.5, 1.0)

    return SpendPlan(
        purchases=np.round(purchases / 100).astype(np.int64) * 100,
        cash_advance=np.round(cash / 10_000).astype(np.int64) * 10_000,
        txn_count=np.maximum(np.round(count), 0).astype(np.int64),
    )


def shocks_frame(customer_ids: list[str], months: list[str], truth: HiddenTruth) -> pd.DataFrame:
    """``shocks.parquet``: one row per customer (``none`` when not shocked)."""

    def month_or_none(idx: IntArray) -> list[str | None]:
        return [months[i] if i < len(months) else None for i in idx]

    return pd.DataFrame(
        {
            "customer_id": customer_ids,
            "shock_type": [str(s) for s in truth.shock_type],
            "start_month": month_or_none(truth.shock_start),
            "severity": truth.severity.astype(np.float64),
            "recovers_month": month_or_none(truth.recovers),
        }
    )


def behaviour_frame(customer_ids: list[str], months: list[str], truth: HiddenTruth) -> pd.DataFrame:
    """Internal hidden table (not a contract table): behaviour type per customer, for labels."""
    return pd.DataFrame(
        {
            "customer_id": customer_ids,
            "behaviour_type": [BEHAVIOUR_NAMES[int(b)] for b in truth.behaviour],
            "wont_pay_start_month": [
                months[i] if i < len(months) else None for i in truth.wont_pay_start
            ],
        }
    )

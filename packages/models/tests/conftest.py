"""Seeded fake features/labels/protected attributes for tests (briefing B6).

Stand-in until WS1 ships ``data/samples/*.parquet``. Columns follow ``contracts/data`` (A7.2,
A7.2.1). Risk is driven by a hidden per-account hardship shock so models have signal to learn,
and the demo personas (Priya, Ravi) are included with stories matching A1.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from npa_contracts.constants import AS_OF_MONTH, DEFAULT_SEED, SIM_START_MONTH

MONTHS: list[str] = (
    pd.period_range(SIM_START_MONTH, AS_OF_MONTH, freq="M").strftime("%Y-%m").tolist()
)
OCCUPATIONS = ("salaried", "self_employed", "gig", "retired", "student")
REGIONS = {
    "Tamil Nadu": "south",
    "Uttar Pradesh": "north",
    "West Bengal": "east",
    "Maharashtra": "west",
    "Assam": "northeast",
    "Madhya Pradesh": "central",
}


# Payment ratio (payments / min due) when not in hardship: mean, sd per habit.
PAY_RATIO = {"normal": (3.0, 1.0), "forgetful": (2.5, 1.0), "strategic": (1.0, 0.3)}
# Priya's card is close to its limit (A1 story: minimum-only payments, salary stopped).
PERSONA_BASE_UTIL = {"ACC-DEMO-PRIYA": 0.75}
# Last-month DPD forced for the segmentation personas.
PERSONA_LAST_DPD = {"ACC-DEMO-FORGOT": 10, "ACC-DEMO-WONTPAY": 35}


@dataclass(frozen=True)
class FakeData:
    features: pd.DataFrame
    labels: pd.DataFrame
    protected: pd.DataFrame
    hidden: pd.DataFrame  # hidden truth per account (habit, shock); experiment generation only


@dataclass(frozen=True)
class _Account:
    account_id: str
    customer_id: str
    occupation: str
    dependants: int
    shock_t: int | None  # month index when hardship starts (hidden truth)
    shock_len: int  # months until recovery (like WS1's recovers_month)
    habit: str  # "normal" | "forgetful" | "strategic"


def _accounts(n: int, rng: np.random.Generator) -> list[_Account]:
    out = []
    for i in range(1, n + 1):
        habit = rng.choice(["normal", "forgetful", "strategic"], p=[0.84, 0.08, 0.08])
        shock = int(rng.integers(0, len(MONTHS))) if rng.random() < 0.15 else None
        out.append(
            _Account(
                account_id=f"ACC-{i:06d}",
                customer_id=f"CUST-{i:06d}",
                occupation=str(rng.choice(OCCUPATIONS, p=[0.55, 0.2, 0.15, 0.05, 0.05])),
                dependants=int(rng.integers(0, 4)),
                shock_t=shock,
                shock_len=int(rng.integers(4, 11)),
                habit=str(habit),
            )
        )
    last = len(MONTHS) - 1
    # Priya: salary stopped ~3 months ago, paying only the minimum (A1).
    out.append(_Account("ACC-DEMO-PRIYA", "CUST-DEMO-PRIYA", "salaried", 1, last - 2, 99, "normal"))
    # Ravi: lost his job earlier, sole earner with dependants, already past due.
    out.append(_Account("ACC-DEMO-RAVI", "CUST-DEMO-RAVI", "salaried", 3, last - 5, 99, "normal"))
    # Test-only personas for the segmentation checks (WS1's extra personas will replace them).
    out.append(_Account("ACC-DEMO-FORGOT", "CUST-DEMO-FORGOT", "salaried", 0, None, 0, "forgetful"))
    out.append(
        _Account("ACC-DEMO-WONTPAY", "CUST-DEMO-WONTPAY", "salaried", 0, None, 0, "strategic")
    )
    return out


def make_fake_data(n_accounts: int = 1000, seed: int = DEFAULT_SEED) -> FakeData:
    """Return a deterministic monthly panel of ``n_accounts`` (+4 personas) over 24 months."""
    rng = np.random.default_rng(seed)
    feats: list[dict[str, object]] = []
    labels: list[dict[str, object]] = []
    accounts = _accounts(n_accounts, rng)
    for acc in accounts:
        limit = int(rng.choice([50_000, 100_000, 200_000, 500_000])) * 100
        base_util = float(rng.uniform(0.05, 0.6)) + 0.3 * (acc.habit == "strategic")
        base_util = PERSONA_BASE_UTIL.get(acc.account_id, base_util)
        tenure0 = int(rng.integers(6, 120))
        for t, month in enumerate(MONTHS):
            in_shock = acc.shock_t is not None and acc.shock_t <= t < acc.shock_t + acc.shock_len
            k = t - acc.shock_t + 1 if in_shock and acc.shock_t is not None else 0
            salaried = acc.occupation == "salaried"
            salary_missing = min(k, 3) if salaried else 0
            streak = min(k, 6) if k else int(acc.habit == "strategic") * int(rng.integers(0, 4))
            dpd = 0
            if k > 3:
                dpd = min(30 * (k - 3), 120)
            elif acc.habit == "forgetful" and rng.random() < 0.25:
                dpd = int(rng.integers(1, 15))
            elif acc.habit == "strategic" and rng.random() < 0.3:
                dpd = int(rng.integers(5, 45))
            if t == len(MONTHS) - 1 and acc.account_id in PERSONA_LAST_DPD:
                dpd = PERSONA_LAST_DPD[acc.account_id]
                streak = 3 if acc.habit == "strategic" else 0
            util = float(np.clip(base_util + 0.08 * k + rng.normal(0, 0.03), 0, 1.2))
            feats.append(
                {
                    "account_id": acc.account_id,
                    "customer_id": acc.customer_id,
                    "month": month,
                    "limit_paise": limit,
                    "utilisation": util,
                    "utilisation_delta_3m": 0.08 * min(k, 3) + float(rng.normal(0, 0.02)),
                    "min_due_only_streak": streak,
                    "months_since_full_payment": streak + int(rng.integers(0, 2)),
                    "payment_ratio_3m": float(
                        max(0.0, (1.1 - 0.25 * k) if k else rng.normal(*PAY_RATIO[acc.habit]))
                    ),
                    "dpd": dpd,
                    "max_dpd_6m": dpd + int(rng.integers(0, 10)) * int(dpd > 0),
                    "broken_streak_flag": dpd > 0,
                    "cash_advance_ratio_3m": (0.1 + 0.05 * min(k, 3)) if k else 0.02,
                    "essentials_spend_delta_3m": (0.2 if k else 0.0) + float(rng.normal(0, 0.05)),
                    "discretionary_spend_delta_3m": (-0.3 if k else 0.0)
                    + float(rng.normal(0, 0.05)),
                    "txn_count_delta_3m": (-0.2 if k else 0.0) + float(rng.normal(0, 0.05)),
                    "salary_missing_months_3m": salary_missing,
                    "salary_delta_3m": -salary_missing / 3,
                    "income_to_due_ratio": float(max(0.1, rng.normal(8, 2) - 2 * min(k, 3))),
                    "tenure_months": tenure0 + t,
                    "dependants": acc.dependants,
                    "occupation_type": acc.occupation,
                }
            )
            logit = (
                -4.0
                + 0.5 * streak
                + 0.7 * salary_missing
                + 0.03 * dpd
                + 2.0 * (util > 0.9)
                + 4.0 * (acc.habit == "forgetful" and dpd > 0)
                + 1.5 * (acc.habit == "strategic")
            )
            rolls = bool(rng.random() < 1 / (1 + np.exp(-logit)))
            if not rolls:
                segment = "not_at_risk"
            elif k:
                segment = "cant_pay"
            elif acc.habit == "strategic":
                segment = "wont_pay"
            else:  # a usual payer who slipped
                segment = "forgot"
            labels.append(
                {
                    "account_id": acc.account_id,
                    "month": month,
                    "rolls_forward_60d": rolls,
                    "reaches_npa_90d": rolls and (dpd >= 30 or bool(rng.random() < 0.2)),
                    "segment_truth": segment,
                }
            )
    features = pd.DataFrame(feats)
    for col in (
        "min_due_only_streak",
        "months_since_full_payment",
        "salary_missing_months_3m",
        "tenure_months",
        "dependants",
    ):
        features[col] = features[col].astype("int16")
    for col in ("dpd", "max_dpd_6m"):
        features[col] = features[col].astype("int32")
    features["limit_paise"] = features["limit_paise"].astype("int64")

    customers = features["customer_id"].unique()
    states = rng.choice(list(REGIONS), size=len(customers))
    protected = pd.DataFrame(
        {
            "customer_id": customers,
            "gender": rng.choice(
                ["female", "male", "other"], size=len(customers), p=[0.45, 0.5, 0.05]
            ),
            "religion": rng.choice(
                ["hindu", "muslim", "christian", "sikh", "other"], size=len(customers)
            ),
            "caste_category": rng.choice(["general", "obc", "sc", "st"], size=len(customers)),
            "state": states,
            "region": [REGIONS[s] for s in states],
        }
    )
    hidden = pd.DataFrame(
        {
            "account_id": [a.account_id for a in accounts],
            "habit": [a.habit for a in accounts],
            "shock_t": [a.shock_t for a in accounts],
            "shock_len": [a.shock_len for a in accounts],
        }
    )
    return FakeData(
        features=features, labels=pd.DataFrame(labels), protected=protected, hidden=hidden
    )


@pytest.fixture(scope="session")
def fake_data() -> FakeData:
    return make_fake_data()


@pytest.fixture(scope="session")
def fake_data_factory() -> Callable[..., FakeData]:
    return make_fake_data


# --- Fake randomised experiment (mirrors WS1's datagen.experiment, PR #101) --------------------
EXPERIMENT_MONTH = "2026-06"
TREATMENTS = ("none", "reminder", "chat_invite", "agent_call", "relief_offer")
GROUPS = ("persuadable", "sure_thing", "lost_cause", "sleeping_dog")
CURE_BASE = {"persuadable": 0.20, "sure_thing": 0.85, "lost_cause": 0.05, "sleeping_dog": 0.60}
CURE_LIFT = {
    "persuadable": (0.0, 0.10, 0.35, 0.20, 0.50),
    "sure_thing": (0.0, 0.03, 0.04, 0.04, 0.05),
    "lost_cause": (0.0, 0.00, 0.02, 0.03, 0.05),
    "sleeping_dog": (0.0, -0.05, -0.10, -0.35, -0.15),
}
NPA_IF_NOT_CURED = {"persuadable": 0.5, "sure_thing": 0.1, "lost_cause": 0.85, "sleeping_dog": 0.45}
COST_PAISE = {
    "none": 0,
    "reminder": 200,
    "chat_invite": 500,
    "agent_call": 6000,
    "relief_offer": 8000,
}
GROUP_MIX = {  # persuadable, sure_thing, lost_cause, sleeping_dog
    "shock_partial": (0.75, 0.05, 0.12, 0.08),
    "shock_severe": (0.30, 0.05, 0.60, 0.05),
    "wont_pay": (0.10, 0.00, 0.80, 0.10),
    "forgot": (0.10, 0.75, 0.00, 0.15),
    "normal": (0.05, 0.80, 0.02, 0.13),  # only reached by personas (scripted anyway)
}
SCRIPTED_GROUP = {"ACC-DEMO-PRIYA": "persuadable", "ACC-DEMO-RAVI": "lost_cause"}


@dataclass(frozen=True)
class FakeExperiment:
    data: FakeData
    experiment: pd.DataFrame  # contracts/data/experiment.md
    potential: pd.DataFrame  # WS1's experiment_potential.parquet shape (hidden)


def make_fake_experiment(data: FakeData, seed: int = DEFAULT_SEED) -> FakeExperiment:
    """Randomised experiment in ``EXPERIMENT_MONTH`` (20% per arm).

    Population: every stressed, forgetful or strategic account plus the personas, like WS1's
    at-risk population (whose behaviour context shows in the features).
    """
    rng = np.random.default_rng([seed, 30])
    t_idx = MONTHS.index(EXPERIMENT_MONTH)
    hid = data.hidden.sort_values("account_id").reset_index(drop=True)
    shock_t = hid["shock_t"].astype(float).to_numpy()
    in_shock = (shock_t <= t_idx) & (t_idx < shock_t + hid["shock_len"].to_numpy())
    severe = rng.random(len(hid)) >= 2 / 3
    ctx_all = np.select(
        [in_shock & severe, in_shock, hid["habit"] == "strategic", hid["habit"] == "forgetful"],
        ["shock_severe", "shock_partial", "wont_pay", "forgot"],
        default="normal",
    )
    keep = (ctx_all != "normal") | hid["account_id"].str.startswith("ACC-DEMO-").to_numpy()
    pop, context = hid[keep].reset_index(drop=True), ctx_all[keep]
    n = len(pop)
    u = rng.random(n)
    groups = np.array(
        [
            GROUPS[min(int(np.searchsorted(np.cumsum(GROUP_MIX[c]), x, side="right")), 3)]
            for c, x in zip(context, u, strict=True)
        ],
        dtype=object,
    )
    for i, acc in enumerate(pop["account_id"]):
        groups[i] = SCRIPTED_GROUP.get(acc, groups[i])
    assigned = rng.permutation(np.resize(np.array(TREATMENTS, dtype=object), n))
    u_cure, u_npa = rng.random(n), rng.random(n)
    customer = pop["account_id"].str.replace("ACC-", "CUST-", regex=False)
    potential = pd.DataFrame(
        {
            "account_id": pop["account_id"],
            "customer_id": customer,
            "month": EXPERIMENT_MONTH,
            "true_uplift_group": groups,
        }
    )
    p_npa = np.array([NPA_IF_NOT_CURED[g] for g in groups])
    for j, t in enumerate(TREATMENTS):
        p_cure = np.clip([CURE_BASE[g] + CURE_LIFT[g][j] for g in groups], 0, 1)
        cured = u_cure < p_cure
        potential[f"cured_{t}"] = cured
        potential[f"npa_{t}"] = ~cured & (u_npa < p_npa)
        potential[f"cost_{t}"] = np.int64(COST_PAISE[t])
    rows = np.arange(n)
    pos = np.array([TREATMENTS.index(t) for t in assigned])

    def take(prefix: str) -> np.ndarray:
        return potential[[f"{prefix}_{t}" for t in TREATMENTS]].to_numpy()[rows, pos]

    experiment = pd.DataFrame(
        {
            "customer_id": customer,
            "account_id": pop["account_id"],
            "month": EXPERIMENT_MONTH,
            "treatment": assigned,
            "outcome_cured_90d": take("cured").astype(bool),
            "outcome_npa_90d": take("npa").astype(bool),
            "contact_cost_paise": take("cost").astype(np.int64),
            "true_uplift_group": groups,
        }
    )
    return FakeExperiment(data=data, experiment=experiment, potential=potential)


def fake_simulate_policy(
    assignments: pd.DataFrame, *, potential: pd.DataFrame, strategy: str = "pre_npa_rescue"
) -> dict[str, object]:
    """Stand-in for ``datagen.experiment.simulate_policy`` (same signature and output shape)."""
    chosen = (
        assignments.set_index("account_id")["treatment"]
        .reindex(potential["account_id"])
        .fillna("none")
        .to_numpy(dtype=object)
    )
    rows = np.arange(len(potential))

    def metrics(treat: np.ndarray, name: str) -> dict[str, object]:
        pos = np.array([TREATMENTS.index(t) for t in treat])

        def take(prefix: str) -> np.ndarray:
            return potential[[f"{prefix}_{t}" for t in TREATMENTS]].to_numpy()[rows, pos]

        return {
            "strategy": name,
            "npa_rate": round(float(take("npa").mean()), 4),
            "cure_rate": round(float(take("cured").mean()), 4),
            "collection_cost_paise": int(take("cost").astype(np.int64).sum()),
            "contacts_made": int((treat != "none").sum()),
        }

    base = metrics(np.full(len(potential), "agent_call", dtype=object), "call_everyone")
    ours = metrics(chosen, strategy)
    b, o = float(base["npa_rate"]), float(ours["npa_rate"])  # type: ignore[arg-type]
    return {
        "as_of_month": EXPERIMENT_MONTH,
        "n_accounts": len(potential),
        "horizon_days": 90,
        "baseline": base,
        "ours": ours,
        "npa_reduction_pct": round(100 * (b - o) / b, 2) if b else 0.0,
        "illustrative": True,
        "source": "tests/conftest.fake_simulate_policy",
    }


@pytest.fixture(scope="session")
def fake_experiment() -> FakeExperiment:
    return make_fake_experiment(make_fake_data(6000))


@pytest.fixture(scope="session")
def fake_sim() -> Callable[..., dict[str, object]]:
    return fake_simulate_policy

"""Randomised collections experiment and policy simulator (task 1.3).

The experiment pools ``experiment_months`` months (default 6) ending at the experiment month
(default ``2026-06``, so ``2026-01``..``2026-06``). Every account at risk in any of those months
(``segment_truth`` is not ``not_at_risk``) is enrolled **once**, at its first at-risk month, so
``experiment.parquet`` stays keyed by ``customer_id``. Treatments are assigned at random, exactly
20% each: ``none``, ``reminder``, ``chat_invite``, ``agent_call``, ``relief_offer``.

Each account gets a hidden ``true_uplift_group`` from its behaviour type plus noise
(``GROUP_MIX``); demo personas keep their scripted group. 90-day outcomes follow explicit,
documented probabilities (``CURE_BASE``, ``CURE_LIFT``, ``NPA_IF_NOT_CURED``; table in
``data/README.md``). Potential outcomes for **every** treatment use common random numbers (one
cure draw and one NPA draw per account), so :func:`simulate_policy` can apply any targeting
policy to the same population and compare it fairly with "call everyone".

Costs (assumptions): reminder Rs 2, chat Rs 5, agent call Rs 60, relief offer Rs 80 plus the
waiver (late fees and their GST charged in the last 3 months).

The outcomes are a simulation, separate from the statement history after the experiment month.
"""

import logging
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from datagen import dues
from datagen.calendar import add_months
from datagen.config import DatagenConfig
from datagen.personas import PERSONAS
from datagen.validate import write_parquet, write_table
from npa_contracts.api import SimulationMetrics, StrategyMetrics
from npa_contracts.enums import Segment, Treatment, UpliftGroup

logger = logging.getLogger(__name__)

STREAM_EXPERIMENT = 30
HORIZON_DAYS = 90
TREATMENTS = tuple(t.value for t in Treatment)  # none, reminder, chat, agent call, relief
GROUPS = tuple(g.value for g in UpliftGroup)  # persuadable, sure_thing, lost_cause, sleeping_dog
P, S, L, D = GROUPS

# 90-day cure probability with no contact.
CURE_BASE = {P: 0.20, S: 0.85, L: 0.05, D: 0.60}
# Change in cure probability per treatment: none, reminder, chat_invite, agent_call, relief_offer.
_LIFT_ROWS = {
    P: (0.0, 0.10, 0.35, 0.20, 0.50),
    S: (0.0, 0.03, 0.04, 0.04, 0.05),
    L: (0.0, 0.00, 0.02, 0.03, 0.05),
    D: (0.0, -0.05, -0.10, -0.35, -0.15),  # sleeping dogs: contact hurts, calls most of all
}
CURE_LIFT: dict[str, dict[str, float]] = {
    g: dict(zip(TREATMENTS, row, strict=True)) for g, row in _LIFT_ROWS.items()
}
NPA_IF_NOT_CURED = {P: 0.50, S: 0.10, L: 0.85, D: 0.45}
COST_RUPEES = {"none": 0, "reminder": 2, "chat_invite": 5, "agent_call": 60, "relief_offer": 80}
WAIVER_MONTHS = 3

# Hidden uplift group mix by context, in GROUPS order (persuadable, sure, lost, sleeping dog).
GROUP_MIX: dict[str, tuple[float, float, float, float]] = {
    "shock_partial": (0.75, 0.05, 0.12, 0.08),  # shocked, severity < 2/3: partial capacity
    "shock_severe": (0.30, 0.05, 0.60, 0.05),  # shocked, severity >= 2/3
    "wont_pay": (0.10, 0.00, 0.80, 0.10),
    "forgot": (0.10, 0.75, 0.00, 0.15),  # forgetful, or a normal customer who "forgot"
    "cant_pay": (0.50, 0.05, 0.35, 0.10),  # normal customer who cannot pay
}

POTENTIAL_FILE = "experiment_potential.parquet"


def cure_probability(group: str, treatment: str) -> float:
    return float(np.clip(CURE_BASE[group] + CURE_LIFT[group][treatment], 0.0, 1.0))


def _context(
    segment: npt.NDArray[np.object_],
    behaviour: npt.NDArray[np.object_],
    severity: npt.NDArray[np.float64],
) -> npt.NDArray[np.object_]:
    return np.select(
        [
            (behaviour == "shocked") & (severity >= 2 / 3),
            behaviour == "shocked",
            (behaviour == "wont_pay") | (segment == Segment.WONT_PAY.value),
            (behaviour == "forgetful") | (segment == Segment.FORGOT.value),
        ],
        ["shock_severe", "shock_partial", "wont_pay", "forgot"],
        default="cant_pay",
    ).astype(object)


def waiver_paise(account_months: pd.DataFrame, month: str) -> pd.Series:
    """Late fees plus GST charged in the ``WAIVER_MONTHS`` up to ``month``, per account."""
    window = account_months[
        (account_months["month"] > add_months(month, -WAIVER_MONTHS))
        & (account_months["month"] <= month)
    ]
    fees = window.groupby("account_id")["late_fee_paise"].sum()
    gst = dues.gst_vec(fees.to_numpy(np.int64), dues.DEFAULT_POLICY.gst_bp)
    return fees + pd.Series(gst, index=fees.index)


def _assign_groups(
    context: npt.NDArray[np.object_], customers: npt.NDArray[np.object_], u: npt.NDArray[Any]
) -> npt.NDArray[np.object_]:
    groups = np.empty(context.size, dtype=object)
    names = np.array(GROUPS, dtype=object)
    for ctx, mix in GROUP_MIX.items():
        idx = context == ctx
        pos = np.searchsorted(np.cumsum(mix), u[idx], side="right")
        groups[idx] = names[np.minimum(pos, len(GROUPS) - 1)]
    scripted = {p.customer_id: p.facts.get("expected_uplift_group") for p in PERSONAS}
    for i, c in enumerate(customers):
        if scripted.get(c):
            groups[i] = scripted[c]
    return groups


def pool_months(month: str, n_months: int) -> list[str]:
    """The ``n_months`` months ending at ``month``, oldest first."""
    if n_months < 1:
        raise ValueError("n_months must be >= 1")
    return [add_months(month, -k) for k in range(n_months - 1, -1, -1)]


def build_experiment(
    labels: pd.DataFrame,
    account_months: pd.DataFrame,
    shocks: pd.DataFrame,
    behaviour: pd.DataFrame,
    month: str,
    seed: int,
    n_months: int = 6,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return ``(experiment, potential_outcomes)``: at-risk accounts pooled over the
    ``n_months`` months ending ``month``, each enrolled once at its first at-risk month."""
    pool = pool_months(month, n_months)
    missing = sorted(set(pool) - set(labels["month"]))
    if missing:
        raise ValueError(f"no labels for {missing}: the experiment needs a full 90-day horizon")
    at_risk = labels[labels["month"].isin(pool) & (labels["segment_truth"] != "not_at_risk")]
    pop = (
        at_risk.sort_values(["account_id", "month"])
        .drop_duplicates("account_id", keep="first")
        .reset_index(drop=True)
    )
    acc_to_cust = account_months.drop_duplicates("account_id").set_index("account_id")
    cust = acc_to_cust.loc[pop["account_id"], "customer_id"].to_numpy()
    n = len(pop)
    rng = np.random.default_rng([seed, STREAM_EXPERIMENT])

    bt = behaviour.set_index("customer_id").loc[cust, "behaviour_type"].to_numpy()
    sev = shocks.set_index("customer_id").loc[cust, "severity"].to_numpy(np.float64)
    context = _context(pop["segment_truth"].to_numpy(), bt, sev)
    groups = _assign_groups(context, cust, rng.random(n))

    # Exactly 20% per arm, in random order.
    assigned = rng.permutation(np.resize(np.array(TREATMENTS, dtype=object), n))
    u_cure, u_npa = rng.random(n), rng.random(n)
    waiver = np.zeros(n, dtype=np.int64)  # late fees + GST in the 3 months up to enrolment
    for enrol_month, idx in pop.groupby("month").indices.items():
        fees = waiver_paise(account_months, str(enrol_month))
        waiver[idx] = fees.reindex(pop["account_id"].iloc[idx]).fillna(0).to_numpy(np.int64)

    potential = pd.DataFrame(
        {
            "account_id": pop["account_id"],
            "customer_id": cust,
            "month": pop["month"].to_numpy(),
            "true_uplift_group": groups,
        }
    )
    p_npa = np.array([NPA_IF_NOT_CURED[g] for g in groups])
    for t in TREATMENTS:
        cured = u_cure < np.array([cure_probability(g, t) for g in groups])
        potential[f"cured_{t}"] = cured
        potential[f"npa_{t}"] = ~cured & (u_npa < p_npa)
        cost = np.full(n, COST_RUPEES[t] * 100, dtype=np.int64)
        if t == Treatment.RELIEF_OFFER.value:
            cost = cost + waiver
        potential[f"cost_{t}"] = cost

    experiment = pd.DataFrame(
        {
            "customer_id": cust,
            "account_id": pop["account_id"].to_numpy(),
            "month": pop["month"].to_numpy(),
            "treatment": assigned,
            "outcome_cured_90d": _take(potential, "cured", assigned).astype(bool),
            "outcome_npa_90d": _take(potential, "npa", assigned).astype(bool),
            "contact_cost_paise": _take(potential, "cost", assigned).astype(np.int64),
            "true_uplift_group": groups,
        }
    )
    return experiment, potential


def _take(
    potential: pd.DataFrame, prefix: str, treatment: npt.NDArray[np.object_]
) -> npt.NDArray[Any]:
    """Each account's potential outcome ``prefix`` under its own ``treatment``."""
    values = potential[[f"{prefix}_{t}" for t in TREATMENTS]].to_numpy()
    index = {t: i for i, t in enumerate(TREATMENTS)}
    pos = np.array([index[t] for t in treatment], dtype=np.int64)
    return values[np.arange(len(potential)), pos]


def _metrics(
    potential: pd.DataFrame, treatment: npt.NDArray[np.object_], name: str
) -> StrategyMetrics:
    n = len(potential)
    return StrategyMetrics(
        strategy=name,
        npa_rate=round(float(_take(potential, "npa", treatment).mean()), 4) if n else 0.0,
        cure_rate=round(float(_take(potential, "cured", treatment).mean()), 4) if n else 0.0,
        collection_cost_paise=int(_take(potential, "cost", treatment).astype(np.int64).sum()),
        contacts_made=int((treatment != Treatment.NONE.value).sum()),
    )


def simulate_policy(
    assignments: pd.DataFrame,
    *,
    potential: pd.DataFrame | None = None,
    data_dir: Path | None = None,
    strategy: str = "pre_npa_rescue",
    baseline_treatment: str = Treatment.AGENT_CALL.value,
) -> dict[str, Any]:
    """Apply a targeting policy to the experiment population; compare with "call everyone".

    ``assignments`` has ``account_id`` and ``treatment`` (a ``Treatment`` value) for the
    accounts the policy contacts; accounts it leaves out get ``none``. The baseline gives every
    account ``baseline_treatment`` (an agent call). Returns a dict with the shape of
    ``contracts/fixtures/simulation_metrics.json`` (``SimulationMetrics``); ``as_of_month`` is
    the last month of the experiment pool.
    """
    if potential is None:
        potential = pd.read_parquet((data_dir or DatagenConfig().data_dir) / POTENTIAL_FILE)
    bad = set(assignments["treatment"]) - set(TREATMENTS)
    if bad:
        raise ValueError(f"unknown treatment(s): {sorted(bad)}")
    unknown = set(assignments["account_id"]) - set(potential["account_id"])
    if unknown:
        raise ValueError(f"{len(unknown)} account(s) are not in the experiment population")
    if assignments["account_id"].duplicated().any():
        raise ValueError("duplicate account_id in assignments")
    chosen = (
        assignments.set_index("account_id")["treatment"]
        .reindex(potential["account_id"])
        .fillna(Treatment.NONE.value)
        .to_numpy(dtype=object)
    )
    n = len(potential)
    base = _metrics(potential, np.full(n, baseline_treatment, dtype=object), "call_everyone")
    ours = _metrics(potential, chosen, strategy)
    reduction = 0.0 if base.npa_rate == 0 else (base.npa_rate - ours.npa_rate) / base.npa_rate
    result = SimulationMetrics(
        as_of_month=str(potential["month"].max()) if n else "2026-06",
        n_accounts=n,
        horizon_days=HORIZON_DAYS,
        baseline=base,
        ours=ours,
        npa_reduction_pct=round(100 * reduction, 2),
        illustrative=True,
        source="datagen.experiment.simulate_policy (synthetic randomised experiment)",
    )
    return result.model_dump(mode="json")


# --- Reference policies (check the simulator has signal WS2 can find) -----------------------


def oracle_policy(potential: pd.DataFrame) -> pd.DataFrame:
    """Knows the true groups: chat with persuadables, leave everyone else alone."""
    pers = potential[potential["true_uplift_group"] == P]
    return pd.DataFrame({"account_id": pers["account_id"], "treatment": "chat_invite"})


def random_policy(
    potential: pd.DataFrame, n_contacts: int, treatment: str, seed: int
) -> pd.DataFrame:
    """Same budget and treatment as a targeted policy, but a random subset of accounts."""
    rng = np.random.default_rng([seed, STREAM_EXPERIMENT, 1])
    pick = rng.choice(len(potential), size=min(n_contacts, len(potential)), replace=False)
    return pd.DataFrame(
        {"account_id": potential["account_id"].to_numpy()[np.sort(pick)], "treatment": treatment}
    )


def run_experiment(cfg: DatagenConfig) -> None:
    """CLI step: build ``experiment.parquet`` (+ hidden potential outcomes)."""
    d = cfg.data_dir
    experiment, potential = build_experiment(
        pd.read_parquet(d / "labels.parquet"),
        pd.read_parquet(d / "account_months.parquet"),
        pd.read_parquet(d / "shocks.parquet"),
        pd.read_parquet(d / "behaviour_types.parquet"),
        cfg.experiment_month,
        cfg.seed,
        cfg.experiment_months,
    )
    write_table(experiment, "experiment", d)
    write_parquet(potential, d / POTENTIAL_FILE, None)
    oracle = simulate_policy(oracle_policy(potential), potential=potential)
    logger.info(
        "experiment rows=%d oracle_npa=%.4f call_everyone_npa=%.4f",
        len(experiment),
        oracle["ours"]["npa_rate"],
        oracle["baseline"]["npa_rate"],
    )

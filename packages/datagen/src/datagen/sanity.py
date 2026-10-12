"""Sanity report on generated data (``data/scripts/sanity_report.py`` prints it).

Checks the task 1.1 acceptance numbers: bucket mix and NPA rate at the as-of month, and that
shocked customers show leading indicators in the months **before** their first missed payment.
"""

from pathlib import Path

import pandas as pd

LEAD_WINDOW = 3  # months before the first miss


def bucket_mix(account_months: pd.DataFrame, month: str) -> pd.Series:
    return account_months.loc[account_months["month"] == month, "bucket"].value_counts(
        normalize=True
    )


def leading_indicators(
    account_months: pd.DataFrame, monthly_spend: pd.DataFrame, shocks: pd.DataFrame
) -> pd.DataFrame:
    """Shocked accounts' spend, cash and payments in the months before their first miss,
    relative to 4-6 months before it (1.0 = unchanged)."""
    am = account_months.merge(monthly_spend, on=["account_id", "month"], suffixes=("", "_s"))
    am = am.sort_values(["account_id", "month"]).reset_index(drop=True)
    am["k"] = am.groupby("account_id").cumcount()
    shocked = set(shocks.loc[shocks["shock_type"] != "none", "customer_id"])
    am = am[am["customer_id"].isin(shocked)]
    first_miss = am[am["dpd"] > 0].groupby("account_id")["k"].min().rename("miss_k")
    am = am.join(first_miss, on="account_id").dropna(subset=["miss_k"])
    am["rel"] = am["k"] - am["miss_k"]
    am = am[am["miss_k"] >= 6]
    cols = {
        "discretionary_paise": "discretionary",
        "essentials_paise": "essentials",
        "cash_advance_paise": "cash_advance",
        "payments_paise": "payments",
    }
    base = am[am["rel"].between(-6, -4)].groupby("account_id")[list(cols)].mean()
    rows = {}
    for rel in range(-LEAD_WINDOW, 1):
        cur = am[am["rel"] == rel].set_index("account_id")[list(cols)]
        ratio = cur.sum() / base.loc[cur.index].sum().clip(lower=1)
        rows[f"t{rel:+d}"] = ratio.rename(cols)
    return pd.DataFrame(rows).T.round(2)


def report(data_dir: Path, as_of_month: str) -> str:
    am = pd.read_parquet(data_dir / "account_months.parquet")
    spend = pd.read_parquet(data_dir / "monthly_spend.parquet")
    shocks = pd.read_parquet(data_dir / "shocks.parquet")
    salary = pd.read_parquet(data_dir / "salary_credits.parquet")
    mix = bucket_mix(am, as_of_month)
    lines = [
        f"accounts: {am['account_id'].nunique()}  months: {am['month'].nunique()}",
        f"bucket mix at {as_of_month}: " + ", ".join(f"{k}={v:.2%}" for k, v in mix.items()),
        f"NPA rate at {as_of_month}: {mix.get('npa', 0.0):.2%} (target 3-6%)",
        f"shocked customers: {(shocks['shock_type'] != 'none').mean():.1%}",
        f"salary months missing: {(salary['credited_paise'] == 0).mean():.2%}",
        "",
        "Leading indicators for shocked accounts (ratio to 4-6 months before the first miss;",
        "t+0 = month of the first missed payment):",
        leading_indicators(am, spend, shocks).to_string(),
    ]
    return "\n".join(lines)

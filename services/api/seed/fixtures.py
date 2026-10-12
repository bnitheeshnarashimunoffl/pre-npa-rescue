"""Seed from contracts/fixtures when WS1/WS2 outputs don't exist yet (no pyarrow needed)."""

import json
from pathlib import Path
from typing import Any

from sqlalchemy import Connection

from app.orm import NBA, Account, Customer, Score, table_of
from npa_contracts.api import QueuePage

# Profile details for the two demo personas (A1); the queue fixture only carries names.
PERSONAS: dict[str, dict[str, Any]] = {
    "CUST-DEMO-PRIYA": {
        "language_pref": "ta",
        "city": "Chennai",
        "occupation_type": "salaried",
        "dependants": 1,
        "has_card_insurance": False,
        "insurance_cover_type": "none",
        "phone_masked": "+91-98XXXXXX21",
        "email_masked": "p****@example.com",
    },
    "CUST-DEMO-RAVI": {
        "language_pref": "en",
        "city": "Coimbatore",
        "occupation_type": "salaried",
        "dependants": 3,
        "has_card_insurance": True,
        "insurance_cover_type": "job_loss",
        "phone_masked": "+91-97XXXXXX58",
        "email_masked": "r****@example.com",
        "preferred_contact_window": "10:00-13:00",
    },
}


def customer_id_for(account_id: str) -> str:
    return account_id.replace("ACC-", "CUST-", 1)


def load_fixtures(
    conn: Connection,
    contracts_dir: Path,
    as_of_month: str,
    *,
    only_customers: set[str] | None = None,
) -> dict[str, int]:
    """Seed the 10 queue accounts (incl. Priya and Ravi) from contracts/fixtures/queue.json.

    ``only_customers`` restricts loading to those customer ids (used by ``demo_reset``).
    """
    raw = json.loads((contracts_dir / "fixtures" / "queue.json").read_text(encoding="utf-8"))
    page = QueuePage.model_validate(raw)
    if only_customers is not None:
        page.items = [i for i in page.items if customer_id_for(i.account_id) in only_customers]
    customers, accounts, scores, nba = [], [], [], []
    # executemany needs identical keys in every row: persona-only fields default to None.
    optional = dict.fromkeys(k for p in PERSONAS.values() for k in p)
    for item in page.items:
        cid = customer_id_for(item.account_id)
        n = item.nba
        customers.append(
            {
                **optional,
                "customer_id": cid,
                "account_id": item.account_id,
                "full_name": item.customer_name,
                "language_pref": "en",
                **PERSONAS.get(cid, {}),
            }
        )
        accounts.append({"account_id": item.account_id, "customer_id": cid})
        scores.append(
            {
                "account_id": item.account_id,
                "as_of_month": as_of_month,
                "p_roll_forward": n.risk.p_roll_forward,
                "risk_band": n.risk.risk_band,
                "reasons": [r.model_dump(mode="json") for r in n.risk.reasons],
                "risk_model_version": n.risk.model_version,
                "segment": n.segment.segment,
                "segment_confidence": n.segment.confidence,
                "segment_model_version": n.segment.model_version,
                "uplift_score": n.uplift.uplift_score,
                "uplift_group": n.uplift.uplift_group,
                "recommended_treatment": n.uplift.recommended_treatment,
                "uplift_model_version": n.uplift.model_version,
            }
        )
        nba.append(
            {
                "account_id": item.account_id,
                "as_of_month": as_of_month,
                "action": n.action,
                "channel": n.channel,
                "earliest_contact_at": n.earliest_contact_at,
                "priority": item.priority,
                "customer_name": item.customer_name,
                "bucket": item.bucket,
                "dpd": item.dpd,
                "total_due_paise": item.total_due_paise,
                "payload": n.model_dump(mode="json"),
            }
        )
    for model, rows in ((Customer, customers), (Account, accounts), (Score, scores), (NBA, nba)):
        conn.execute(table_of(model).insert(), rows)
    return {
        "customers": len(customers),
        "accounts": len(accounts),
        "scores": len(scores),
        "nba": len(nba),
    }

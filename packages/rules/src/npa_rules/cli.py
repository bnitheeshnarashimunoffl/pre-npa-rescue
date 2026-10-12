"""``python -m npa_rules.cli``: validate the policy and generate WS3's contract fixtures.

Commands::

    uv run python -m npa_rules.cli validate [--policy PATH]
    uv run python -m npa_rules.cli fixtures --out DIR

``fixtures`` writes the WS3-produced fixtures (B4): ``relief_options_priya.json``,
``relief_options_ravi.json``, ``offer.json``, ``nba.json``, ``queue.json``, ``policy.json``.
Output is deterministic (fixed clock 2026-10-12 11:00 IST, fixed offer id). The files are meant
for WS5 to copy into ``contracts/fixtures/`` (owned by WS5) through a ``contract`` PR.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from npa_contracts.enums import Actor
from npa_rules.compliance_guard import ComplianceGuard
from npa_rules.nba import NextBestActionService, QueueInput, StaticRiskProvider, prioritise
from npa_rules.personas import PRIYA, PRIYA_DECLARED, RAVI, RAVI_DECLARED
from npa_rules.policy_engine import PolicyEngine
from npa_rules.policy_loader import Policy, PolicyError, load_policy
from npa_rules.relief_calc import AccountSnapshot, estimate_affordability

log = logging.getLogger("npa_rules.cli")

FIXED_NOW = datetime(2026, 10, 12, 5, 30, tzinfo=UTC)  # 11:00 IST
FIXED_OFFER_ID = "OFFER-6f1c2a9e-3b7d-4c51-9a0e-2d4b8f7e1c33"
AS_OF = "2026-09"


def _dump(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def build_fixtures(policy: Policy, queue_fixture: dict[str, Any]) -> dict[str, Any]:
    """WS3 fixture payloads, keyed by file name. ``queue_fixture`` supplies model outputs
    (until WS2 ships) and the names/amounts of the non-persona accounts."""
    accounts: dict[str, AccountSnapshot] = {PRIYA.account_id: PRIYA, RAVI.account_id: RAVI}
    names: dict[str, str] = {}
    for item in queue_fixture["items"]:
        names[item["account_id"]] = item["customer_name"]
        accounts.setdefault(
            item["account_id"],
            AccountSnapshot(
                customer_id="CUST-" + item["account_id"].removeprefix("ACC-"),
                account_id=item["account_id"],
                dpd=item["dpd"],
                total_outstanding_paise=item["total_due_paise"],
                overdue_paise=item["total_due_paise"] // 10,
                waivable_charges_paise=0,
                monthly_income_paise=5_000_000,
                avg_payment_3m_paise=300_000,
            ),
        )
    by_customer = {a.customer_id: a for a in accounts.values()}
    engine = PolicyEngine(
        policy, by_customer.__getitem__, clock=lambda: FIXED_NOW, id_factory=lambda: FIXED_OFFER_ID
    )
    guard = ComplianceGuard(policy, lambda _c: [], by_customer.__getitem__)
    nba = NextBestActionService(
        policy,
        StaticRiskProvider.from_queue_fixture(queue_fixture),
        guard,
        accounts.__getitem__,
        clock=lambda: FIXED_NOW,
    )

    def options(ctx: AccountSnapshot, declared: dict[str, int | None]) -> list[dict[str, Any]]:
        afford = estimate_affordability(ctx, declared, policy.affordability)
        return [o.model_dump(mode="json") for o in engine.relief_options(ctx.customer_id, afford)]

    out: dict[str, Any] = {"relief_options_ravi.json": options(RAVI, RAVI_DECLARED)}
    out["relief_options_priya.json"] = options(PRIYA, PRIYA_DECLARED)
    offer = engine.propose_offer(
        PRIYA.customer_id, f"OPT-{PRIYA.account_id}-EMI6-WAIVER", Actor.BOT
    )
    out["offer.json"] = offer.model_dump(mode="json")
    out["nba.json"] = nba.next_best_action(PRIYA.account_id, AS_OF).model_dump(mode="json")
    items = [QueueInput(nba.next_best_action(a, AS_OF), accounts[a], names[a]) for a in names]
    queue = prioritise(items, policy)
    out["queue.json"] = {
        "items": [q.model_dump(mode="json") for q in queue],
        "next_cursor": queue_fixture.get("next_cursor"),
    }
    out["policy.json"] = {
        "version": policy.version,
        "effective_from": "2026-04-01",
        "updated_at": FIXED_NOW.isoformat().replace("+00:00", "Z"),
        "updated_by": "admin1",
        "policy": policy.model_dump(mode="json"),
    }
    return out


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(prog="npa_rules.cli", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="validate bank_policy.yaml")
    v.add_argument("--policy", default=None)
    f = sub.add_parser("fixtures", help="write WS3 contract fixtures")
    f.add_argument("--out", required=True, type=Path)
    f.add_argument("--policy", default=None)
    f.add_argument(
        "--queue-fixture",
        type=Path,
        default=Path("contracts/fixtures/queue.json"),
        help="model outputs for the non-persona accounts (default: the v0 fixture)",
    )
    args = parser.parse_args(argv)
    try:
        policy = load_policy(args.policy)
    except PolicyError as exc:
        for err in exc.errors:
            log.error("policy invalid: %s", err)
        return 1
    if args.cmd == "validate":
        log.info("policy ok: version=%s", policy.version)
        return 0
    queue_fixture = json.loads(args.queue_fixture.read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in build_fixtures(policy, queue_fixture).items():
        (args.out / name).write_text(_dump(data), encoding="utf-8", newline="\n")
        log.info("wrote %s", args.out / name)
    return 0


if __name__ == "__main__":
    sys.exit(main())

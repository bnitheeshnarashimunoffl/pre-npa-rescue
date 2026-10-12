"""Retention purge for call/chat records (task 5.4).

RBI RBC Directions para 454P: keep records of calls/contacts for 6 months
(``npa_contracts.constants.CALL_RECORD_RETENTION_DAYS`` = 180). After that they are deleted:

- ``contact_events`` older than the cutoff,
- ``chat_turns`` older than the cutoff, and ``chat_sessions`` created before the cutoff that
  have no turns left.

Not purged: ``audit_log`` (append-only evidence; it holds no message content), complaints
(IS/ISO 10002 records), offers and policy versions. Every run, including a dry run, is audited.

    uv run python -m app.retention [--dry-run] [--days 180]

Schedule it daily (cron, a Render cron job, or a GitHub Actions schedule) - see docs/setup.md.
"""

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import get_settings
from app.db import make_engine
from app.orm import ChatSession, ChatTurn, ContactEvent
from npa_contracts.constants import CALL_RECORD_RETENTION_DAYS

log = logging.getLogger("retention")


@dataclass(frozen=True)
class PurgeReport:
    cutoff: datetime
    contact_events: int
    chat_turns: int
    chat_sessions: int
    dry_run: bool


def purge_expired(
    session: Session,
    *,
    now: datetime | None = None,
    days: int = CALL_RECORD_RETENTION_DAYS,
    dry_run: bool = False,
) -> PurgeReport:
    """Delete call/chat records older than ``days`` (in the caller's transaction)."""
    if days < CALL_RECORD_RETENTION_DAYS:
        raise ValueError(f"retention may not be shorter than {CALL_RECORD_RETENTION_DAYS} days")
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    old_events = ContactEvent.ts < cutoff
    old_turns = ChatTurn.ts < cutoff
    empty_old_sessions = (ChatSession.created_at < cutoff) & ~exists().where(
        ChatTurn.session_id == ChatSession.session_id, ChatTurn.ts >= cutoff
    )
    count = {
        "contact_events": session.scalar(select(func.count()).where(old_events)) or 0,
        "chat_turns": session.scalar(select(func.count()).where(old_turns)) or 0,
        "chat_sessions": session.scalar(select(func.count()).where(empty_old_sessions)) or 0,
    }
    if not dry_run:
        session.execute(delete(ContactEvent).where(old_events))
        session.execute(delete(ChatTurn).where(old_turns))
        session.execute(delete(ChatSession).where(empty_old_sessions))
    audit(
        session,
        "retention.purge",
        "system",
        "contact_records",
        {"cutoff": cutoff.isoformat(), "days": days, "dry_run": dry_run, **count},
    )
    return PurgeReport(cutoff=cutoff, dry_run=dry_run, **count)


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="python -m app.retention", description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="count and audit, delete nothing")
    parser.add_argument("--days", type=int, default=CALL_RECORD_RETENTION_DAYS)
    parser.add_argument("--database-url", default=settings.database_url)
    args = parser.parse_args(argv)
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s %(message)s")
    try:
        with Session(make_engine(args.database_url)) as session, session.begin():
            report = purge_expired(session, days=args.days, dry_run=args.dry_run)
    except ValueError as exc:
        log.error("%s", exc)
        return 1
    log.info(
        "purge cutoff=%s dry_run=%s contact_events=%s chat_turns=%s chat_sessions=%s",
        report.cutoff.isoformat(),
        report.dry_run,
        report.contact_events,
        report.chat_turns,
        report.chat_sessions,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

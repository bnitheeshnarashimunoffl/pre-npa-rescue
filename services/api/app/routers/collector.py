from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import orm
from app.config import get_settings
from app.db import get_session
from app.errors import bad_request, not_found
from app.queries import InvalidCursorError, queue_page
from app.routers._common import PROTECTED, access
from app.services import convert
from npa_contracts.api import AccountSummary, QueuePage
from npa_contracts.constants import PAGE_LIMIT_DEFAULT, PAGE_LIMIT_MAX
from npa_contracts.enums import Bucket, NextAction
from npa_contracts.models import NextBestAction, QueueItem, ReasonCode

router = APIRouter(prefix="/collector", tags=["collector"], **PROTECTED)

DbSession = Annotated[Session, Depends(get_session)]
HISTORY_MONTHS = 6


@router.get("/queue", response_model=QueuePage, **access("collector", "admin"))
def queue(
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=PAGE_LIMIT_MAX)] = PAGE_LIMIT_DEFAULT,
    cursor: Annotated[str | None, Query(description="Opaque pagination cursor")] = None,
    bucket: Bucket | None = None,
    action: NextAction | None = None,
) -> QueuePage:
    """Prioritised collector queue (fixture-backed until task 5.1)."""
    # Reads the per-month NBA cache (the `nba` table) with keyset pagination (task 5.2).
    try:
        rows, next_cursor = queue_page(
            session,
            get_settings().as_of_month,
            limit=limit,
            cursor=cursor,
            bucket=bucket,
            action=action,
        )
    except InvalidCursorError:
        bad_request("INVALID_CURSOR", "The pagination cursor is invalid or expired.")
    items = [
        QueueItem(
            account_id=r.account_id,
            customer_name=r.customer_name,
            bucket=r.bucket,
            dpd=r.dpd,
            total_due_paise=r.total_due_paise,
            nba=NextBestAction.model_validate(r.payload),
            priority=r.priority,
        )
        for r in rows
    ]
    return QueuePage(items=items, next_cursor=next_cursor)


@router.get(
    "/accounts/{account_id}/summary",
    response_model=AccountSummary,
    **access("collector", "hardship_officer"),
)
def account_summary(account_id: str, session: DbSession) -> AccountSummary:
    """History, contacts, offers and reasons for one account."""
    account = session.get(orm.Account, account_id)
    if account is None:
        not_found("Account", account_id)
    month = get_settings().as_of_month
    customer = session.get(orm.Customer, account.customer_id)
    assert customer is not None  # FK
    history = list(
        session.scalars(
            select(orm.AccountMonth)
            .where(orm.AccountMonth.account_id == account_id)
            .order_by(orm.AccountMonth.month.desc())
            .limit(HISTORY_MONTHS)
        )
    )
    nba_row = session.get(orm.NBA, (account_id, month))
    score = session.get(orm.Score, (account_id, month))
    latest = history[0] if history else None
    contacts = session.scalars(
        select(orm.ContactEvent)
        .where(orm.ContactEvent.account_id == account_id)
        .order_by(orm.ContactEvent.ts.desc())
        .limit(50)
    )
    offers = session.scalars(
        select(orm.Offer)
        .where(orm.Offer.account_id == account_id)
        .order_by(orm.Offer.created_at.desc())
    )
    return AccountSummary(
        account_id=account_id,
        customer_id=customer.customer_id,
        customer_name=customer.full_name,
        bucket=latest.bucket if latest else (nba_row.bucket if nba_row else Bucket.CURRENT),
        dpd=latest.dpd if latest else (nba_row.dpd if nba_row else 0),
        total_due_paise=latest.total_due_paise
        if latest
        else (nba_row.total_due_paise if nba_row else 0),
        min_due_paise=latest.min_due_paise if latest else 0,
        history=[convert.account_month(m) for m in reversed(history)],
        contacts=[convert.contact_event(c) for c in contacts],
        offers=[convert.offer(o) for o in offers],
        reasons=[ReasonCode.model_validate(r) for r in score.reasons] if score else [],
        nba=NextBestAction.model_validate(nba_row.payload) if nba_row else None,
    )

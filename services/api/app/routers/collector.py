from typing import Annotated

from fastapi import APIRouter, Query

from app.errors import not_implemented
from app.fixtures import load_fixture
from app.routers._common import PROTECTED, access
from npa_contracts.api import AccountSummary, QueuePage
from npa_contracts.constants import PAGE_LIMIT_DEFAULT, PAGE_LIMIT_MAX
from npa_contracts.enums import Bucket, NextAction

router = APIRouter(prefix="/collector", tags=["collector"], **PROTECTED)


@router.get("/queue", response_model=QueuePage, **access("collector", "admin"))
def queue(
    limit: Annotated[int, Query(ge=1, le=PAGE_LIMIT_MAX)] = PAGE_LIMIT_DEFAULT,
    cursor: Annotated[str | None, Query(description="Opaque pagination cursor")] = None,
    bucket: Bucket | None = None,
    action: NextAction | None = None,
) -> QueuePage:
    """Prioritised collector queue (fixture-backed until task 5.1)."""
    page = QueuePage.model_validate(load_fixture("queue.json"))
    items = [
        i
        for i in page.items
        if (bucket is None or i.bucket == bucket) and (action is None or i.nba.action == action)
    ]
    return QueuePage(items=items[:limit], next_cursor=None)


@router.get(
    "/accounts/{account_id}/summary",
    response_model=AccountSummary,
    **access("collector", "hardship_officer"),
)
def account_summary(account_id: str) -> AccountSummary:
    """History, contacts, offers and reasons for one account."""
    not_implemented("5.1")

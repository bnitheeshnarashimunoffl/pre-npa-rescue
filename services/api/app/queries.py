"""Read queries shared by routers (task 5.2).

Collector queue: keyset pagination on ``(priority DESC, account_id ASC)`` within one
``as_of_month``, served by the ``ix_nba_queue`` index. The cursor is opaque to clients
(base64url JSON of the last row's sort key).
"""

import base64
import binascii
import json
from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.orm import NBA
from npa_contracts.constants import PAGE_LIMIT_MAX
from npa_contracts.enums import Bucket, NextAction


class InvalidCursorError(ValueError):
    pass


@dataclass(frozen=True)
class QueueCursor:
    priority: float
    account_id: str

    def encode(self) -> str:
        raw = json.dumps([self.priority, self.account_id], separators=(",", ":"))
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")

    @classmethod
    def decode(cls, token: str) -> "QueueCursor":
        try:
            raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
            priority, account_id = json.loads(raw)
            if isinstance(priority, bool) or not isinstance(priority, int | float):
                raise TypeError("priority")
            if not isinstance(account_id, str):
                raise TypeError("account_id")
        except (binascii.Error, ValueError, TypeError) as exc:
            raise InvalidCursorError("invalid cursor") from exc
        return cls(float(priority), account_id)


def queue_page(
    session: Session,
    as_of_month: str,
    *,
    limit: int,
    cursor: str | None = None,
    bucket: Bucket | None = None,
    action: NextAction | None = None,
) -> tuple[list[NBA], str | None]:
    """One page of the collector queue and the cursor for the next page (None if last)."""
    if not 1 <= limit <= PAGE_LIMIT_MAX:
        raise ValueError(f"limit must be 1..{PAGE_LIMIT_MAX}")
    stmt = select(NBA).where(NBA.as_of_month == as_of_month)
    if bucket is not None:
        stmt = stmt.where(NBA.bucket == bucket)
    if action is not None:
        stmt = stmt.where(NBA.action == action)
    if cursor is not None:
        c = QueueCursor.decode(cursor)
        stmt = stmt.where(
            or_(
                NBA.priority < c.priority,
                and_(NBA.priority == c.priority, NBA.account_id > c.account_id),
            )
        )
    stmt = stmt.order_by(NBA.priority.desc(), NBA.account_id).limit(limit + 1)
    rows = list(session.scalars(stmt))
    if len(rows) <= limit:
        return rows, None
    last = rows[limit - 1]
    return rows[:limit], QueueCursor(last.priority, last.account_id).encode()

"""Regulatory and simulation constants (contract A7.0, A3).

Every regulatory constant cites its source. Business rules are evaluated in
``BUSINESS_TZ``; timestamps are stored in UTC.
"""

from datetime import time
from typing import Final

from npa_contracts.enums import Bucket

# --- Simulation calendar (A7.0) -------------------------------------------------------------
SIM_START_MONTH: Final = "2024-10"
SIM_END_MONTH: Final = "2026-09"
AS_OF_MONTH: Final = "2026-09"  # as-of month for scoring and the demo
DEFAULT_SEED: Final = 42

# --- Business time zone ----------------------------------------------------------------------
# RBI RBC Directions para 454Y(4): the contact window is local time, so rules run in IST.
BUSINESS_TZ: Final = "Asia/Kolkata"

# --- Asset classification and credit reporting -----------------------------------------------
# RBI asset-classification rules for credit cards (circular of 16 July 2015): a card account is
# an NPA when the minimum amount due stays unpaid for more than 90 days from the due date.
NPA_DPD: Final = 90

# RBI Credit Card Directions 2025: report "past due" to bureaus and levy late charges only after
# the account is past due for more than 3 days (DPD counted from the statement due date).
PAST_DUE_GRACE_DAYS: Final = 3

# Upper DPD bound (inclusive) for each bucket, in order. Anything above the last bound is NPA.
# dpd 0 -> current; 1-30 -> sma0; 31-60 -> sma1; 61-90 -> sma2; >90 -> npa.
BUCKET_THRESHOLDS: Final[tuple[tuple[int, Bucket], ...]] = (
    (0, Bucket.CURRENT),
    (30, Bucket.SMA0),
    (60, Bucket.SMA1),
    (NPA_DPD, Bucket.SMA2),
)

# --- Contact rules ---------------------------------------------------------------------------
# RBI RBC Directions para 454Y(4): contact or visit only between 08:00 and 19:00.
CONTACT_WINDOW: Final = (time(8), time(19))

# RBI RBC Directions para 454P: keep call/chat records for 6 months.
CALL_RECORD_RETENTION_DAYS: Final = 180

# --- Resolution frameworks -------------------------------------------------------------------
# RBI Framework for Compromise Settlements and Technical Write-offs (8 June 2023): payment spread
# over more than 3 months counts as restructuring.
SETTLEMENT_RESTRUCTURING_THRESHOLD_MONTHS: Final = 3

# Same 2023 framework: at least 12 months' cooling period before new credit after a settlement.
MIN_SETTLEMENT_COOLING_MONTHS: Final = 12

# RBI Credit Card Directions 2025: update the credit bureau within 30 days of settlement.
BUREAU_UPDATE_DAYS_AFTER_SETTLEMENT: Final = 30

# --- Complaints ------------------------------------------------------------------------------
# RBI RBC Directions para 454AA / Credit Card Directions: unresolved complaints may go to the
# RBI Ombudsman after 30 days. IS/ISO 10002:2018 complaint SLA.
COMPLAINT_SLA_DAYS: Final = 30

# --- API ---------------------------------------------------------------------------------------
PAGE_LIMIT_DEFAULT: Final = 50
PAGE_LIMIT_MAX: Final = 200


def bucket_for_dpd(dpd: int) -> Bucket:
    """Map days past due to a :class:`Bucket` using :data:`BUCKET_THRESHOLDS`.

    Raises ``ValueError`` for negative DPD.
    """
    if dpd < 0:
        raise ValueError(f"dpd must be >= 0, got {dpd}")
    for upper, bucket in BUCKET_THRESHOLDS:
        if dpd <= upper:
            return bucket
    return Bucket.NPA

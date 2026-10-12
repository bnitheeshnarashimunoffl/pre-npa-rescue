"""Fixture-backed test doubles for external providers (WS4 testing).

Locates contracts/fixtures relative to the repository root so tests pass from any folder and in CI.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from npa_contracts.enums import Actor, Channel, ComplaintStatus, Lang, Role
from npa_contracts.models import (
    Affordability,
    Callback,
    Complaint,
    ComplianceDecision,
    ContactEvent,
    GrievanceOfficer,
    Offer,
    ReliefOption,
    RiskScore,
    SegmentResult,
    UpliftResult,
)


def _get_ist_tz() -> Any:
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Asia/Kolkata")
    except Exception:
        return timezone(timedelta(hours=5, minutes=30), name="IST")


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "contracts" / "fixtures"


def _load_fixture(filename: str) -> Any:
    path = FIXTURES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Fixture file not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class FakeRiskProvider:
    """Fake RiskProvider backed by contracts/fixtures/*.json."""

    def __init__(self) -> None:
        self._risk = RiskScore.model_validate(_load_fixture("risk_score.json"))
        self._segment = SegmentResult.model_validate(_load_fixture("segment.json"))
        self._uplift = UpliftResult.model_validate(_load_fixture("uplift.json"))

    def risk(self, account_id: str, as_of_month: str) -> RiskScore:
        return self._risk

    def segment(self, account_id: str, as_of_month: str) -> SegmentResult:
        return self._segment

    def uplift(self, account_id: str, as_of_month: str) -> UpliftResult:
        return self._uplift

    def score_batch(
        self, as_of_month: str
    ) -> Iterator[tuple[RiskScore, SegmentResult, UpliftResult]]:
        yield (self._risk, self._segment, self._uplift)


class FakePolicyProvider:
    """Fake PolicyProvider backed by contracts/fixtures/relief_options_*.json and policy.json."""

    def __init__(self) -> None:
        priya_raw = _load_fixture("relief_options_priya.json")
        ravi_raw = _load_fixture("relief_options_ravi.json")
        self._options_priya = [ReliefOption.model_validate(opt) for opt in priya_raw]
        self._options_ravi = [ReliefOption.model_validate(opt) for opt in ravi_raw]
        self._offer = Offer.model_validate(_load_fixture("offer.json"))
        policy_raw = _load_fixture("policy.json")
        self._grievance = GrievanceOfficer.model_validate(policy_raw["policy"]["grievance_officer"])

    def relief_options(self, customer_id: str, affordability: Affordability) -> list[ReliefOption]:
        if "RAVI" in customer_id.upper() or affordability.max_monthly_payment_paise == 0:
            return self._options_ravi
        return self._options_priya

    def propose_offer(self, customer_id: str, option_id: str, actor: Actor) -> Offer:
        return self._offer

    def grievance_officer(self) -> GrievanceOfficer:
        return self._grievance


class FakeComplianceProvider:
    """Fake ComplianceProvider allowing contacts and compliant text."""

    def check_contact(
        self, customer_id: str, channel: Channel, at: datetime, actor: Actor
    ) -> ComplianceDecision:
        return ComplianceDecision(
            allowed=True,
            rule_ids=["RBI-454Y4-WINDOW"],
            next_allowed_at=None,
            explanation="Contact allowed within standard operating window.",
        )

    def check_text(self, text: str, lang: Lang) -> ComplianceDecision:
        return ComplianceDecision(
            allowed=True,
            rule_ids=["RBI-454Z-HARSH-PRACTICES"],
            next_allowed_at=None,
            explanation="Text complies with respectful conduct guidelines.",
        )


class FakeContactLogger:
    """Fake ContactLogger tracking logged events."""

    def __init__(self) -> None:
        self.events: list[ContactEvent] = []

    def log(self, event: ContactEvent) -> None:
        self.events.append(event)


class FakeComplaintSink:
    """Fake ComplaintSink backed by contracts/fixtures/complaint.json."""

    def __init__(self) -> None:
        self.complaints: list[Complaint] = []
        raw = _load_fixture("complaint.json")
        self._template = Complaint.model_validate(raw)

    def open(self, customer_id: str, category: str, text: str, lang: Lang) -> Complaint:
        now = datetime.now(UTC)
        docket = f"CMP-{now.strftime('%Y%m%d')}-{len(self.complaints) + 1:04d}"
        complaint = Complaint(
            docket_no=docket,
            customer_id=customer_id,
            category=category,
            text=text,
            lang=lang,
            status=ComplaintStatus.OPEN,
            escalation_level=0,
            created_at=now,
            sla_due_at=now.replace(day=min(now.day + 30, 28)),
            grievance_officer=self._template.grievance_officer,
        )
        self.complaints.append(complaint)
        return complaint


class FakeCallbackScheduler:
    """Fake CallbackScheduler returning slots within 08:00-19:00 IST."""

    def __init__(self) -> None:
        self.callbacks: list[Callback] = []
        raw = _load_fixture("callback.json")
        self._template = Callback.model_validate(raw)

    def available_slots(self, customer_id: str, day: date) -> list[tuple[datetime, datetime]]:
        tz = _get_ist_tz()
        slot1_start = datetime.combine(day, time(11, 0), tzinfo=tz)
        slot1_end = datetime.combine(day, time(11, 30), tzinfo=tz)
        slot2_start = datetime.combine(day, time(15, 0), tzinfo=tz)
        slot2_end = datetime.combine(day, time(15, 30), tzinfo=tz)
        return [(slot1_start, slot1_end), (slot2_start, slot2_end)]

    def book(self, customer_id: str, slot_start: datetime, role: Role, summary: str) -> Callback:
        now = datetime.now(UTC)
        callback = Callback(
            callback_id=f"CB-{len(self.callbacks) + 1:04d}",
            customer_id=customer_id,
            role=role,
            slot_start=slot_start,
            slot_end=slot_start,
            summary=summary,
            created_at=now,
        )
        self.callbacks.append(callback)
        return callback


class FakeCustomerContextProvider:
    """Fake CustomerContextProvider returning demo customer contexts."""

    def context(self, customer_id: str) -> dict[str, Any]:
        if "PRIYA" in customer_id.upper():
            return {
                "customer_id": "CUST-DEMO-PRIYA",
                "account_id": "ACC-DEMO-PRIYA",
                "full_name": "Priya Sharma",
                "language_pref": "ta",
                "has_card_insurance": False,
                "insurance_cover_type": "none",
                "preferred_contact_window": "10:00-13:00",
            }
        return {
            "customer_id": "CUST-DEMO-RAVI",
            "account_id": "ACC-DEMO-RAVI",
            "full_name": "Ravi Kumar",
            "language_pref": "en",
            "has_card_insurance": True,
            "insurance_cover_type": "job_loss",
            "preferred_contact_window": "11:00-14:00",
        }

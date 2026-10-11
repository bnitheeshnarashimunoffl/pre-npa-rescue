import json
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from npa_contracts import api, models, providers
from npa_contracts.enums import Actor, Channel, Lang, Role

FIXTURES = Path(__file__).resolve().parents[3] / "contracts" / "fixtures"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_offer_fixture_roundtrip() -> None:
    offer = models.Offer.model_validate(_load("offer.json"))
    assert offer.option.monthly_amount_paise == 200_000
    assert offer.option.tenure_months == 6
    again = models.Offer.model_validate_json(offer.model_dump_json())
    assert again == offer


def test_relief_options_fixture_lists() -> None:
    priya = TypeAdapter(list[models.ReliefOption]).validate_python(
        _load("relief_options_priya.json")
    )
    ravi = TypeAdapter(list[models.ReliefOption]).validate_python(_load("relief_options_ravi.json"))
    assert priya[0].waiver_paise and priya[0].monthly_amount_paise == 200_000
    assert {o.type for o in ravi} == {"insurance_referral", "review_date"}


def test_extra_fields_forbidden() -> None:
    data = _load("risk_score.json") | {"unexpected": 1}
    with pytest.raises(ValidationError):
        models.RiskScore.model_validate(data)


def test_naive_datetime_rejected() -> None:
    data = _load("callback.json")
    data["slot_start"] = "2026-10-12T11:00:00"
    with pytest.raises(ValidationError):
        models.Callback.model_validate(data)


def test_month_and_probability_constraints() -> None:
    data = _load("risk_score.json")
    with pytest.raises(ValidationError):
        models.RiskScore.model_validate(data | {"as_of_month": "2026-13"})
    with pytest.raises(ValidationError):
        models.RiskScore.model_validate(data | {"p_roll_forward": 1.2})


def test_api_defaults() -> None:
    err = api.ErrorResponse(error=api.ErrorBody(code="NOT_FOUND", message="x"))
    assert err.error.details == {}
    assert api.ChatSessionCreateRequest().lang is None
    assert models.ChatTurnRequest(text="hi").lang is None
    assert api.WellnessResult(customer_id="c", scenarios=[], disclaimer_key="k").illustrative
    assert api.OfferDecisionRequest().note is None


class _FakeCompliance:
    def check_contact(
        self, customer_id: str, channel: Channel, at: datetime, actor: Actor
    ) -> models.ComplianceDecision:
        return models.ComplianceDecision(
            allowed=True, rule_ids=[], next_allowed_at=None, explanation="ok"
        )

    def check_text(self, text: str, lang: Lang) -> models.ComplianceDecision:
        return self.check_contact("c", Channel.CHAT, datetime.now().astimezone(), Actor.BOT)


class _FakeScheduler:
    def available_slots(self, customer_id: str, day: date) -> list[tuple[datetime, datetime]]:
        return []

    def book(
        self, customer_id: str, slot_start: datetime, role: Role, summary: str
    ) -> models.Callback:
        raise NotImplementedError


class _FakeRisk:
    def risk(self, account_id: str, as_of_month: str) -> models.RiskScore:
        return models.RiskScore.model_validate(_load("risk_score.json"))

    def segment(self, account_id: str, as_of_month: str) -> models.SegmentResult:
        return models.SegmentResult.model_validate(_load("segment.json"))

    def uplift(self, account_id: str, as_of_month: str) -> models.UpliftResult:
        return models.UpliftResult.model_validate(_load("uplift.json"))

    def score_batch(
        self, as_of_month: str
    ) -> Iterator[tuple[models.RiskScore, models.SegmentResult, models.UpliftResult]]:
        yield self.risk("a", as_of_month), self.segment("a", as_of_month), self.uplift("a", "m")


def test_protocols_are_structural() -> None:
    compliance: providers.ComplianceProvider = _FakeCompliance()
    scheduler: providers.CallbackScheduler = _FakeScheduler()
    risk: providers.RiskProvider = _FakeRisk()
    assert compliance.check_text("hello", Lang.EN).allowed
    assert scheduler.available_slots("c", date(2026, 10, 12)) == []
    assert len(list(risk.score_batch("2026-09"))) == 1

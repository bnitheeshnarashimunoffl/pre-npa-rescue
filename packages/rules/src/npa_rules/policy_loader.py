"""Load and validate ``bank_policy.yaml`` into an immutable :class:`Policy`.

Validation has three layers, all run by :func:`load_policy` / :func:`parse_policy`:

1. ``policies/bank_policy.schema.json`` (JSON Schema, generated from :class:`Policy`; the admin
   UI can use it for form validation).
2. The Pydantic model itself (types, ranges, frozen).
3. RBI cross-checks (:func:`regulatory_violations`): the RBI numbers in the file must match
   ``npa_contracts.constants`` and mandatory disclosures cannot be removed, so an admin edit
   through ``PUT /admin/policy`` can never weaken an RBI rule.

The API reloads by calling :func:`load_policy` again (hot reload); the returned object is
never mutated.
"""

from __future__ import annotations

import json
import os
from datetime import time
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import yaml
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from npa_contracts.constants import (
    BUREAU_UPDATE_DAYS_AFTER_SETTLEMENT,
    BUSINESS_TZ,
    CONTACT_WINDOW,
    MIN_SETTLEMENT_COOLING_MONTHS,
    SETTLEMENT_RESTRUCTURING_THRESHOLD_MONTHS,
)
from npa_contracts.enums import Bucket
from npa_contracts.models import GrievanceOfficer
from npa_rules.disclosures import missing_disclosure_keys
from npa_rules.dues import LateFeeSlab

__all__ = [
    "MANDATORY_DISCLOSURES",
    "Policy",
    "PolicyError",
    "default_policy_path",
    "load_policy",
    "parse_policy",
    "policy_json_schema",
    "regulatory_violations",
]

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = PACKAGE_ROOT / "policies"
SCHEMA_PATH = POLICY_DIR / "bank_policy.schema.json"

# Disclosures that RBI makes mandatory for an option; the policy file may add, never remove.
MANDATORY_DISCLOSURES: dict[str, tuple[str, ...]] = {
    # Prudential Framework 2019: a restructured standard account is downgraded to NPA.
    "restructuring": ("disc.restructuring.npa_downgrade",),
    # Compromise Settlements framework 2023: cooling period; > 3 months is restructuring.
    "compromise_settlement": (
        "disc.settlement.cooling_period",
        "disc.settlement.over_3_months_is_restructuring",
    ),
}

Pct = Annotated[Decimal, Field(ge=0, le=100)]
PaiseInt = Annotated[int, Field(ge=0)]
Months = Annotated[int, Field(ge=1, le=120)]


class PolicyError(ValueError):
    """The policy file is invalid. ``errors`` lists every problem found."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("invalid bank policy: " + "; ".join(errors))
        self.errors = errors


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ContactWindow(_Frozen):
    start: time
    end: time
    tz: str


class ContactPolicy(_Frozen):
    window_local: ContactWindow
    max_outbound_attempts_per_day: Annotated[int, Field(ge=1)]
    max_outbound_attempts_per_week: Annotated[int, Field(ge=1)]
    min_gap_minutes_between_attempts: Annotated[int, Field(ge=0)]
    do_not_contact_flags: tuple[str, ...]


class LateFeeSlabSpec(_Frozen):
    up_to_paise: PaiseInt | None
    fee_paise: PaiseInt


class ChargesPolicy(_Frozen):
    late_fee_slabs: Annotated[tuple[LateFeeSlabSpec, ...], Field(min_length=1)]
    card_interest_rate_annual_pct: Pct
    mad_principal_pct: Pct
    mad_floor_paise: PaiseInt

    @field_validator("late_fee_slabs")
    @classmethod
    def _slabs_sorted_open_ended(
        cls, v: tuple[LateFeeSlabSpec, ...]
    ) -> tuple[LateFeeSlabSpec, ...]:
        bounds = [s.up_to_paise for s in v[:-1]]
        if any(b is None for b in bounds) or v[-1].up_to_paise is not None:
            raise ValueError("only the last late-fee slab may be open-ended, and it must be")
        if bounds != sorted(bounds):  # type: ignore[type-var]
            raise ValueError("late-fee slabs must be sorted by up_to_paise")
        return v

    def slabs(self) -> tuple[LateFeeSlab, ...]:
        return tuple(LateFeeSlab(s.up_to_paise, s.fee_paise) for s in self.late_fee_slabs)


class AffordabilityPolicy(_Frozen):
    affordability_ratio: Annotated[Decimal, Field(gt=0, le=1)]
    dependant_allowance_paise: PaiseInt
    estimated_essentials_pct: Pct


class OffersPolicy(_Frozen):
    expiry_days: Annotated[int, Field(ge=1, le=90)]


class NbaPolicy(_Frozen):
    hardship_first: bool
    chat_invites_ignored_before_call: Annotated[int, Field(ge=1)]


class OptionPolicy(_Frozen):
    enabled: bool
    requires_human_approval: bool
    policy_ref: str
    regulatory_refs: tuple[str, ...]
    disclosure_keys: tuple[str, ...]
    eligible_buckets: tuple[Bucket, ...] = tuple(Bucket)


class FeeWaiverPolicy(OptionPolicy):
    max_waiver_paise: PaiseInt
    max_times_per_12m: Annotated[int, Field(ge=0)]


class EmiPolicy(OptionPolicy):
    tenures_months: Annotated[tuple[Months, ...], Field(min_length=1)]
    interest_rate_annual_pct: Pct
    min_emi_paise: PaiseInt


class RestructuringPolicy(OptionPolicy):
    max_tenure_months: Months
    moratorium_months_max: Annotated[int, Field(ge=0, le=24)]
    interest_rate_annual_pct: Pct


class SettlementPolicy(OptionPolicy):
    max_sacrifice_pct: Pct
    min_ageing_dpd: Annotated[int, Field(ge=0)]
    payment_window_months_max: Months
    cooling_period_months: Months


class ReviewDatePolicy(OptionPolicy):
    review_after_days: Annotated[tuple[Annotated[int, Field(ge=1)], ...], Field(min_length=1)]


class OptionsPolicy(_Frozen):
    fee_waiver: FeeWaiverPolicy
    emi_conversion: EmiPolicy
    restructuring: RestructuringPolicy
    compromise_settlement: SettlementPolicy
    insurance_referral: OptionPolicy
    review_date: ReviewDatePolicy


class CreditBureauPolicy(_Frozen):
    notify_before_default_report: bool
    update_after_settlement_days: Annotated[int, Field(ge=1)]


class Policy(_Frozen):
    """Immutable, validated bank policy (simulated board-approved policy)."""

    version: str
    bank_name: str
    board_approval_ref: str
    grievance_officer: GrievanceOfficer
    contact: ContactPolicy
    charges: ChargesPolicy
    affordability: AffordabilityPolicy
    offers: OffersPolicy
    nba: NbaPolicy
    options: OptionsPolicy
    credit_bureau: CreditBureauPolicy

    def option(self, name: str) -> OptionPolicy:
        opt: OptionPolicy = getattr(self.options, name)
        return opt

    def policy_ref(self, name: str) -> str:
        """Fully qualified reference, e.g. ``bank_policy.yaml#fee_waiver.v1``."""
        return f"bank_policy.yaml#{self.option(name).policy_ref}"


def policy_json_schema() -> dict[str, Any]:
    """JSON Schema of the policy file (committed as ``policies/bank_policy.schema.json``)."""
    schema = Policy.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "bank_policy.schema.json"
    schema["title"] = "Demo Bank card collections and hardship policy (simulated)"
    return schema


def regulatory_violations(policy: Policy) -> list[str]:
    """RBI cross-checks; an empty list means the policy respects every RBI number in A3."""
    errors: list[str] = []
    w = policy.contact.window_local
    if (w.start, w.end) != CONTACT_WINDOW or w.tz != BUSINESS_TZ:
        errors.append(
            "contact.window_local must be 08:00-19:00 Asia/Kolkata (RBI RBC para 454Y(4))"
        )
    flags = set(policy.contact.do_not_contact_flags)
    if not {"bereavement", "medical_emergency"} <= flags:
        errors.append("do_not_contact_flags must include bereavement and medical_emergency (454Y6)")
    s = policy.options.compromise_settlement
    if s.cooling_period_months < MIN_SETTLEMENT_COOLING_MONTHS:
        errors.append("settlement cooling_period_months must be >= 12 (RBI 2023 framework)")
    if s.payment_window_months_max > SETTLEMENT_RESTRUCTURING_THRESHOLD_MONTHS:
        errors.append(
            "settlement payment_window_months_max must be <= 3; longer is restructuring (2023)"
        )
    if (
        policy.credit_bureau.update_after_settlement_days > BUREAU_UPDATE_DAYS_AFTER_SETTLEMENT
        or not policy.credit_bureau.notify_before_default_report
    ):
        errors.append(
            "credit_bureau: notify before default report and update within 30 days "
            "(RBI Credit Card Directions 2025)"
        )
    if policy.contact.max_outbound_attempts_per_week < policy.contact.max_outbound_attempts_per_day:
        errors.append("max_outbound_attempts_per_week must be >= max_outbound_attempts_per_day")
    for name in OptionsPolicy.model_fields:
        opt = policy.option(name)
        for key in missing_disclosure_keys(list(opt.disclosure_keys)):
            errors.append(f"options.{name}: unknown disclosure key {key!r}")
        for key in MANDATORY_DISCLOSURES.get(name, ()):
            if key not in opt.disclosure_keys:
                errors.append(f"options.{name}: mandatory disclosure {key!r} missing")
        if name in ("restructuring", "compromise_settlement") and not opt.requires_human_approval:
            errors.append(f"options.{name}: requires_human_approval must be true")
    return errors


def _schema_errors(data: Any) -> list[str]:
    validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    return [
        f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    ]


def parse_policy(data: Any) -> Policy:
    """Validate an already-parsed policy document (e.g. the body of ``PUT /admin/policy``)."""
    errors = _schema_errors(data)
    if errors:
        raise PolicyError(errors)
    try:
        policy = Policy.model_validate(data)
    except ValidationError as exc:  # pragma: no cover - the JSON Schema catches these first
        raise PolicyError([str(e["msg"]) for e in exc.errors()]) from exc
    errors = regulatory_violations(policy)
    if errors:
        raise PolicyError(errors)
    return policy


def default_policy_path() -> Path:
    """``POLICY_PATH`` env var (A11) or the packaged ``policies/bank_policy.yaml``."""
    return Path(os.environ.get("POLICY_PATH") or POLICY_DIR / "bank_policy.yaml")


def load_policy(path: str | Path | None = None) -> Policy:
    """Read, validate and return the policy at ``path`` (default :func:`default_policy_path`).

    Raises :class:`PolicyError` (a ``ValueError``) for an invalid file.
    """
    p = Path(path) if path is not None else default_policy_path()
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PolicyError([f"{p.name}: not valid YAML: {exc}"]) from exc
    return parse_policy(data)


def write_schema(path: Path = SCHEMA_PATH) -> None:
    """Regenerate ``bank_policy.schema.json``: ``uv run python -m npa_rules.policy_loader``."""
    text = json.dumps(policy_json_schema(), indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write_schema()

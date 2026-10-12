"""Tests for bank_policy.yaml, its JSON Schema, the loader and the disclosure catalogue."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from npa_contracts.constants import CONTACT_WINDOW, MIN_SETTLEMENT_COOLING_MONTHS
from npa_contracts.enums import Bucket, Lang
from npa_rules.disclosures import DISCLOSURES, disclosure_text, missing_disclosure_keys
from npa_rules.policy_loader import (
    POLICY_DIR,
    SCHEMA_PATH,
    Policy,
    PolicyError,
    default_policy_path,
    load_policy,
    parse_policy,
    policy_json_schema,
    write_schema,
)


def raw_policy() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(
        (POLICY_DIR / "bank_policy.yaml").read_text(encoding="utf-8")
    )
    return data


def test_shipped_policy_loads() -> None:
    policy = load_policy()
    assert policy.version == "2026.10-v1"
    w = policy.contact.window_local
    assert (w.start, w.end) == CONTACT_WINDOW
    assert policy.options.compromise_settlement.cooling_period_months >= 12
    assert policy.options.fee_waiver.eligible_buckets == (Bucket.SMA0, Bucket.SMA1, Bucket.SMA2)
    assert policy.policy_ref("restructuring") == "bank_policy.yaml#restructuring.v1"


def test_policy_is_immutable() -> None:
    policy = load_policy()
    with pytest.raises(ValueError):
        policy.version = "x"  # type: ignore[misc]


def test_options_without_buckets_allow_every_bucket() -> None:
    assert load_policy().options.insurance_referral.eligible_buckets == tuple(Bucket)


def test_policy_path_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "p.yaml"
    target.write_text(yaml.safe_dump(raw_policy()), encoding="utf-8")
    monkeypatch.setenv("POLICY_PATH", str(target))
    assert default_policy_path() == target
    assert load_policy().version == "2026.10-v1"


def test_committed_schema_is_up_to_date() -> None:
    committed = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert committed == policy_json_schema(), "run: uv run python -m npa_rules.policy_loader"


def test_write_schema_round_trips(tmp_path: Path) -> None:
    out = tmp_path / "s.json"
    write_schema(out)
    assert json.loads(out.read_text(encoding="utf-8")) == policy_json_schema()


def test_invalid_yaml_is_policy_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("version: [unclosed", encoding="utf-8")
    with pytest.raises(PolicyError, match="not valid YAML"):
        load_policy(bad)


def test_schema_rejects_unknown_and_missing_fields() -> None:
    data = raw_policy()
    data["surprise"] = 1
    del data["grievance_officer"]
    with pytest.raises(PolicyError) as exc:
        parse_policy(data)
    assert len(exc.value.errors) == 2


def test_schema_rejects_negative_money() -> None:
    data = raw_policy()
    data["options"]["fee_waiver"]["max_waiver_paise"] = -1
    with pytest.raises(PolicyError, match="max_waiver_paise"):
        parse_policy(data)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("contact", "window_local", "end"), "21:00", "454Y"),
        (("contact", "window_local", "tz"), "UTC", "454Y"),
        (("contact", "do_not_contact_flags"), ["customer_requested_pause"], "bereavement"),
        (("contact", "max_outbound_attempts_per_week"), 1, "per_week"),
        (("options", "compromise_settlement", "cooling_period_months"), 6, "cooling"),
        (("options", "compromise_settlement", "payment_window_months_max"), 6, "restructuring"),
        (("options", "restructuring", "disclosure_keys"), [], "npa_downgrade"),
        (("options", "restructuring", "requires_human_approval"), False, "human"),
        (("options", "fee_waiver", "disclosure_keys"), ["disc.nope"], "unknown disclosure"),
        (("credit_bureau", "update_after_settlement_days"), 45, "30 days"),
        (("credit_bureau", "notify_before_default_report"), False, "notify"),
    ],
)
def test_rbi_cross_checks(path: tuple[str, ...], value: object, message: str) -> None:
    data = raw_policy()
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(PolicyError, match=message):
        parse_policy(data)


def test_late_fee_slabs_must_be_sorted_and_open_ended() -> None:
    data = raw_policy()
    data["charges"]["late_fee_slabs"] = [
        {"up_to_paise": 500000, "fee_paise": 50000},
        {"up_to_paise": 50000, "fee_paise": 0},
        {"up_to_paise": None, "fee_paise": 130000},
    ]
    with pytest.raises(PolicyError, match="sorted"):
        parse_policy(data)
    data["charges"]["late_fee_slabs"] = [{"up_to_paise": 50000, "fee_paise": 0}]
    with pytest.raises(PolicyError, match="open-ended"):
        parse_policy(data)


def test_cooling_period_constant_matches_policy() -> None:
    cooling = load_policy().options.compromise_settlement.cooling_period_months
    assert cooling == MIN_SETTLEMENT_COOLING_MONTHS


def test_policy_model_round_trips_through_json() -> None:
    policy = load_policy()
    again = Policy.model_validate_json(policy.model_dump_json())
    assert again == policy


# --- disclosures -----------------------------------------------------------------------------


def test_every_policy_disclosure_has_three_languages() -> None:
    policy = load_policy()
    for name in type(policy.options).model_fields:
        for key in policy.option(name).disclosure_keys:
            assert set(DISCLOSURES[key].text) == set(Lang)
            assert all(DISCLOSURES[key].text[lang].strip() for lang in Lang)


def test_restructuring_disclosure_text_is_the_briefed_wording() -> None:
    assert disclosure_text("disc.restructuring.npa_downgrade", Lang.EN).startswith(
        "If your repayment plan is restructured, your account will be classified as a "
        "non-performing asset."
    )


def test_translations_flagged_for_review() -> None:
    assert all(d.needs_review == {Lang.TA, Lang.HI} for d in DISCLOSURES.values())


def test_unknown_disclosure_key() -> None:
    with pytest.raises(KeyError):
        disclosure_text("disc.nope", Lang.EN)
    assert missing_disclosure_keys(["disc.nope", "disc.settlement.cooling_period"]) == ["disc.nope"]


@pytest.mark.parametrize("banned", ["payment holiday", "interest will be frozen", "no impact"])
def test_disclosures_never_make_banned_promises(banned: str) -> None:
    for d in DISCLOSURES.values():
        assert banned not in d.text[Lang.EN].lower()

"""Task 2.2 explanation layer: SHAP -> reason codes in en / ta / hi."""

import copy
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml

from npa_contracts.models import ReasonCode, RiskScore
from npa_models.early_warning import EarlyWarningModel, train_frames
from npa_models.explain import (
    LANGS,
    CatalogueError,
    Condition,
    explain,
    load_catalogue,
    parse_catalogue,
    shap_values,
    top_reasons,
)
from npa_models.features import FEATURE_COLUMNS, build_matrix

AS_OF = "2026-09"
FIXTURE_CODES = {"SALARY_STOPPED", "MIN_DUE_ONLY_STREAK", "UTILISATION_RISING"}
# Words that blame or judge the customer (briefing B8).
BLAMING = ("irresponsib", "reckless", "careless", "lazy", "default", "fraud", "fault")


@pytest.fixture(scope="module")
def model(fake_data) -> EarlyWarningModel:
    return train_frames(fake_data.features, fake_data.labels, seed=42)


@pytest.fixture(scope="module")
def as_of(fake_data) -> pd.DataFrame:
    return fake_data.features[fake_data.features["month"] == AS_OF]


@pytest.fixture
def raw_catalogue() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "src" / "npa_models" / "reason_codes.yaml"
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return copy.deepcopy(data)


def _persona(model: EarlyWarningModel, as_of: pd.DataFrame, account_id: str) -> RiskScore:
    return model.score(as_of[as_of["account_id"] == account_id])[0]


# --- catalogue ------------------------------------------------------------------------------


def test_packaged_catalogue_covers_every_feature() -> None:
    cat = load_catalogue()
    covered = {f for r in cat.reasons for f in r.features} | cat.not_shown
    assert covered == set(FEATURE_COLUMNS)
    assert set(cat.codes) >= FIXTURE_CODES
    assert set(cat.needs_review) == {"ta", "hi"}


def test_every_code_has_all_languages_and_plain_text() -> None:
    for reason in load_catalogue().reasons:
        assert set(reason.text) == set(LANGS)
        for lang, forms in reason.text.items():
            for form in forms.values():
                assert form.strip().endswith((".", "।")), (reason.code, lang)
                assert not any(w in form.lower() for w in BLAMING), (reason.code, form)


def test_catalogue_from_path(tmp_path: Path, raw_catalogue) -> None:
    path = tmp_path / "codes.yaml"
    text = yaml.safe_dump(raw_catalogue, allow_unicode=True, sort_keys=False)
    path.write_text(text, encoding="utf-8")
    assert load_catalogue(path).codes == load_catalogue().codes


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda c: c["codes"]["SALARY_STOPPED"]["text"].pop("ta"), "missing 'ta'"),
        (lambda c: c["codes"]["INCOME_DOWN"].update(features=[]), "at least one feature"),
        (lambda c: c["codes"]["INCOME_DOWN"].update(features=["gender"]), "unknown features"),
        (lambda c: c["codes"]["INCOME_DOWN"].update(when=["salary_delta_3m ~ 1"]), "condition"),
        (lambda c: c["codes"]["INCOME_DOWN"].update(plural="n"), "plural"),
        (lambda c: c["codes"]["INCOME_DOWN"]["text"].update(en="Down {x}."), "placeholders"),
        (lambda c: c["codes"]["INCOME_DOWN"]["text"].update(en="salary_delta_3m fell."), "raw"),
        (lambda c: c["codes"].pop("CARD_USE_CHANGED"), "no reason code"),
        (lambda c: c["not_shown"].update(dpd="x"), "both explained"),
        (lambda c: c.update(codes={}), "no reason codes"),
    ],
)
def test_bad_catalogue_is_rejected(raw_catalogue, mutate, match: str) -> None:
    mutate(raw_catalogue)
    with pytest.raises(CatalogueError, match=match):
        parse_catalogue(raw_catalogue)


def test_condition_ignores_missing_values() -> None:
    cond = Condition.parse("dpd >= 1")
    df = pd.DataFrame({"dpd": [0, 5, None]})
    assert cond.mask(df).tolist() == [False, True, False]


# --- rendering ------------------------------------------------------------------------------


def _contrib(**values: float) -> pd.DataFrame:
    row = dict.fromkeys(FEATURE_COLUMNS, 0.0) | values
    return pd.DataFrame([row])


def _values(**values: Any) -> pd.DataFrame:
    row: dict[str, Any] = dict.fromkeys(FEATURE_COLUMNS, 0.0) | {"occupation_type": "salaried"}
    return pd.DataFrame([row | values])


def test_numbers_and_plural_forms_are_filled_in() -> None:
    contrib = _contrib(salary_missing_months_3m=0.5, min_due_only_streak=0.3, dpd=0.2)
    for n, text in [
        (1, "A salary credit did not arrive in one of the last 3 months."),
        (2, "Salary credits did not arrive in 2 of the last 3 months."),
        (3, "Salary credits have not arrived for the last 3 months."),
    ]:
        values = _values(salary_missing_months_3m=n, min_due_only_streak=1, dpd=16)
        [reasons] = top_reasons(contrib, values)
        assert [r.code for r in reasons] == [
            "SALARY_STOPPED",
            "MIN_DUE_ONLY_STREAK",
            "PAYMENT_OVERDUE",
        ]
        assert reasons[0].text["en"] == text
        assert reasons[1].text["en"] == "Only the minimum due was paid on the last bill."
        assert reasons[2].text["en"] == "The current payment is 16 days overdue."
        assert "16" in reasons[2].text["ta"] and "16" in reasons[2].text["hi"]
    assert sum(r.weight for r in reasons) == pytest.approx(1.0)


def test_percentages_render_from_scaled_values() -> None:
    [reasons] = top_reasons(_contrib(utilisation=0.4), _values(utilisation=0.957))
    assert reasons[0].text["en"] == "The card is close to its limit (96% used)."


def test_reason_hidden_when_its_condition_is_false() -> None:
    # A big positive contribution from salary with no missing salary must not claim it stopped.
    contrib = _contrib(salary_missing_months_3m=0.9, dpd=0.1)
    [reasons] = top_reasons(contrib, _values(salary_missing_months_3m=0, dpd=3))
    assert [r.code for r in reasons] == ["PAYMENT_OVERDUE"]
    assert reasons[0].weight == pytest.approx(0.1)


def test_only_risk_raising_reasons_and_not_shown_features() -> None:
    contrib = _contrib(dependants=0.8, dpd=-0.3, utilisation=0.2)
    [reasons] = top_reasons(contrib, _values(dependants=3, dpd=5, utilisation=0.9))
    assert [r.code for r in reasons] == ["UTILISATION_HIGH"]
    assert reasons[0].weight == pytest.approx(0.2)
    [none] = top_reasons(_contrib(dpd=-0.1), _values(dpd=5))
    assert none == []
    [zero] = top_reasons(_contrib(), _values())
    assert zero == []


def test_top_k_validated() -> None:
    with pytest.raises(ValueError, match="top_k"):
        top_reasons(_contrib(), _values(), top_k=0)


# --- on the trained model -------------------------------------------------------------------


def test_shap_values_add_up_to_the_raw_score(model, as_of) -> None:
    est = model.bundle.estimators["roll_forward"]
    x = build_matrix(as_of.head(50))
    contrib = shap_values(est, x)
    assert list(contrib.columns) == list(FEATURE_COLUMNS)
    raw = np.asarray(est.predict(x, raw_score=True), dtype=float)
    bias = np.asarray(est.predict(x, pred_contrib=True), dtype=float)[:, -1]
    np.testing.assert_allclose(contrib.sum(axis=1).to_numpy() + bias, raw, rtol=1e-6)


def test_explain_returns_contract_reason_codes(model, as_of) -> None:
    x = build_matrix(as_of)
    result = explain(model.bundle.estimators["roll_forward"], x)
    assert len(result) == len(as_of)
    for reasons in result:
        assert len(reasons) <= 3
        weights = [r.weight for r in reasons]
        assert weights == sorted(weights, reverse=True)
        assert all(0 < w <= 1 for w in weights)
        for r in reasons:
            assert isinstance(r, ReasonCode)
            assert set(r.text) == set(LANGS)
            assert not any(f in r.text["en"] for f in FEATURE_COLUMNS)


def test_priya_reasons_match_her_story(model, as_of) -> None:
    # A1: salary stopped ~3 months ago, paying only the minimum, card near its limit.
    # Fake data, seed 42: MIN_DUE_ONLY_STREAK on 5 of 5 seeds, SALARY_STOPPED on 4 of 5.
    priya = _persona(model, as_of, "ACC-DEMO-PRIYA")
    codes = [r.code for r in priya.reasons]
    assert {"SALARY_STOPPED", "MIN_DUE_ONLY_STREAK"} <= set(codes)
    assert len(codes) == 3


def test_ravi_reasons_match_his_story(model, as_of) -> None:
    # A1: lost his job, already past due. Fake data, seed 42: PAYMENT_OVERDUE first on 5 of 5
    # seeds, SALARY_STOPPED in the top 3 on 2 of 5; re-check on WS1's data.
    ravi = _persona(model, as_of, "ACC-DEMO-RAVI")
    codes = [r.code for r in ravi.reasons]
    assert codes[0] == "PAYMENT_OVERDUE"
    assert "SALARY_STOPPED" in codes


def test_reasons_ignore_protected_columns(model, as_of, fake_data) -> None:
    rows = as_of.head(30).merge(fake_data.protected, on="customer_id")
    swapped = rows.assign(religion="hindu", region="north", gender="female")
    assert model.reasons(rows) == model.reasons(swapped)

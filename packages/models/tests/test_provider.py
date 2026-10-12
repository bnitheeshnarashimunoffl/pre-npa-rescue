"""RiskProvider (briefing B5) and scores.parquet (#38)."""

import json
import time
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from npa_contracts.enums import RiskBand
from npa_contracts.models import ReasonCode, RiskScore, SegmentResult, UpliftResult
from npa_contracts.providers import RiskProvider
from npa_models import early_warning, segment, uplift
from npa_models.cli import EXIT_ERROR, EXIT_OK, main
from npa_models.config import ModelSettings
from npa_models.provider import SCORE_COLUMNS, ModelProvider, UnknownAccountError

AS_OF = "2026-09"
# The columns proposed in #38 and already read by WS5's seed (services/api/seed/parquet.py).
ISSUE_38_COLUMNS = (
    "account_id",
    "as_of_month",
    "p_roll_forward",
    "risk_band",
    "reasons",
    "risk_model_version",
    "segment",
    "segment_confidence",
    "segment_model_version",
    "uplift_score",
    "uplift_group",
    "recommended_treatment",
    "uplift_model_version",
)


@pytest.fixture(scope="module")
def models(
    fake_experiment,
) -> tuple[early_warning.EarlyWarningModel, segment.SegmentModel, uplift.UpliftModel]:
    d = fake_experiment.data
    return (
        early_warning.train_frames(d.features, d.labels, seed=42),
        segment.train_frames(d.features, d.labels, seed=42),
        uplift.train_frames(fake_experiment.experiment, d.features, seed=42)[0],
    )


@pytest.fixture(scope="module")
def provider(models, fake_experiment) -> ModelProvider:
    p = ModelProvider(*models, features=fake_experiment.data.features)
    p.warm(AS_OF)
    return p


def _as_of_rows(fake_experiment) -> pd.DataFrame:
    f = fake_experiment.data.features
    return f[f["month"] == AS_OF]


def test_implements_the_protocol(provider) -> None:
    proto: RiskProvider = provider  # structural typing
    for name in ("risk", "segment", "uplift", "score_batch"):
        assert callable(getattr(proto, name))


def test_lookups_match_the_models(provider, models, fake_experiment) -> None:
    ew, seg, up = models
    row = _as_of_rows(fake_experiment).query("account_id == 'ACC-DEMO-PRIYA'")
    risk = provider.risk("ACC-DEMO-PRIYA", AS_OF)
    assert isinstance(risk, RiskScore)
    assert risk == ew.score(row)[0]
    assert risk.risk_band is RiskBand.HIGH and len(risk.reasons) == 3
    assert provider.segment("ACC-DEMO-PRIYA", AS_OF) == seg.score(row)[0]
    assert provider.uplift("ACC-DEMO-PRIYA", AS_OF) == up.score(row)[0]
    assert provider.risk("ACC-DEMO-RAVI", AS_OF).risk_band is RiskBand.HIGH


def test_single_lookup_is_fast_after_warm_up(provider) -> None:
    start = time.perf_counter()
    for _ in range(50):
        provider.risk("ACC-DEMO-PRIYA", AS_OF)
        provider.segment("ACC-DEMO-PRIYA", AS_OF)
        provider.uplift("ACC-DEMO-PRIYA", AS_OF)
    per_lookup_ms = (time.perf_counter() - start) / 150 * 1000
    assert per_lookup_ms < 50


def test_unknown_account_and_month(provider) -> None:
    with pytest.raises(UnknownAccountError, match="ACC-NOPE"):
        provider.risk("ACC-NOPE", AS_OF)
    with pytest.raises(ValueError, match="2030-01"):
        provider.segment("ACC-DEMO-PRIYA", "2030-01")


def test_months_are_scored_lazily_and_cached(models, fake_experiment) -> None:
    p = ModelProvider(*models, features=fake_experiment.data.features)
    assert p._months == {}
    first = p.uplift("ACC-DEMO-RAVI", "2026-08")
    assert set(p._months) == {"2026-08"}
    assert p.uplift("ACC-DEMO-RAVI", "2026-08") == first


def test_score_batch(provider, fake_experiment) -> None:
    triples = list(provider.score_batch(AS_OF))
    assert len(triples) == len(_as_of_rows(fake_experiment))
    for risk, seg, up in triples[:20]:
        assert isinstance(seg, SegmentResult) and isinstance(up, UpliftResult)
        assert risk.account_id == seg.account_id == up.account_id


def test_scores_frame_matches_issue_38(provider, fake_experiment) -> None:
    frame = provider.scores_frame(AS_OF)
    assert SCORE_COLUMNS == ISSUE_38_COLUMNS
    assert tuple(frame.columns) == ISSUE_38_COLUMNS
    assert len(frame) == len(_as_of_rows(fake_experiment))
    assert not frame.isna().any().any()  # every column is NOT NULL in WS5's table
    assert frame["p_roll_forward"].between(0, 1).all()
    assert frame["segment_confidence"].between(0, 1).all()
    priya = frame.set_index("account_id").loc["ACC-DEMO-PRIYA"]
    reasons = [ReasonCode.model_validate(r) for r in json.loads(priya["reasons"])]
    assert reasons == provider.risk("ACC-DEMO-PRIYA", AS_OF).reasons
    assert "ta" in json.loads(priya["reasons"])[0]["text"]


def test_write_scores_parquet_types(tmp_path: Path, provider) -> None:
    path = provider.write_scores(AS_OF, tmp_path / "out" / "scores.parquet")
    schema = pq.read_schema(path)
    assert schema.names == list(ISSUE_38_COLUMNS)
    types = {f.name: str(f.type) for f in schema}
    assert types["p_roll_forward"] == types["segment_confidence"] == "double"
    assert types["reasons"] == types["risk_band"] == "string"
    back = pd.read_parquet(path)
    pd.testing.assert_frame_equal(back, provider.scores_frame(AS_OF))


def test_duplicate_feature_rows_are_rejected(models, fake_experiment) -> None:
    rows = _as_of_rows(fake_experiment).head(3)
    p = ModelProvider(*models, features=pd.concat([rows, rows]))
    with pytest.raises(ValueError, match="duplicate"):
        p.warm(AS_OF)


def test_from_settings(tmp_path: Path, models, fake_experiment) -> None:
    for m in models:
        m.save(tmp_path / "artifacts")
    fake_experiment.data.features.to_parquet(tmp_path / "features.parquet")
    settings = ModelSettings(  # type: ignore[call-arg]
        _env_file=None, model_dir=tmp_path / "artifacts", data_dir=tmp_path
    )
    p = ModelProvider.from_settings(settings)
    assert p.risk("ACC-DEMO-PRIYA", AS_OF).model_version == models[0].model_version


# --- CLI ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def trained_dir(tmp_path_factory: pytest.TempPathFactory, models) -> Path:
    out = tmp_path_factory.mktemp("models")
    for m in models:
        m.save(out)
    return out


def test_cli_score_writes_scores_parquet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, trained_dir: Path, fake_experiment
) -> None:
    fp = tmp_path / "features.parquet"
    fake_experiment.data.features.to_parquet(fp)
    monkeypatch.setenv("MODEL_DIR", str(trained_dir))
    out = tmp_path / "scores.parquet"
    assert main(["score", "--as-of", AS_OF, f"--features={fp}", f"--out={out}"]) == EXIT_OK
    assert pq.read_schema(out).names == list(ISSUE_38_COLUMNS)
    assert main(["score", "--as-of", "2030-01", f"--features={fp}", f"--out={out}"]) == EXIT_ERROR


def test_cli_score_needs_features_and_models(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_data
) -> None:
    fp = tmp_path / "features.parquet"
    out = tmp_path / "scores.parquet"
    assert main(["score", f"--features={fp}", f"--out={out}"]) == EXIT_ERROR
    fake_data.features.to_parquet(fp)
    monkeypatch.setenv("MODEL_DIR", str(tmp_path / "no-models"))
    assert main(["score", f"--features={fp}", f"--out={out}"]) == EXIT_ERROR
    assert not out.exists()

"""``RiskProvider`` for the API (briefing B5) and the ``scores.parquet`` writer (#38).

``ModelProvider`` loads the three bundles from ``MODEL_DIR`` and the features from ``DATA_DIR``.
A month is scored in one vectorised batch the first time it is asked for (or up front with
:meth:`ModelProvider.warm`); after that ``risk`` / ``segment`` / ``uplift`` are dictionary
lookups that build the Pydantic object, well under the 50 ms target.

``scores.parquet`` has one row per ``(account_id, as_of_month)`` with exactly
:data:`SCORE_COLUMNS`, the flattened ``RiskScore`` + ``SegmentResult`` + ``UpliftResult``
that WS5's seed loads into the ``scores`` table. ``reasons`` is a JSON string (a list of
``ReasonCode``).
"""

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from npa_contracts.enums import RiskBand, Segment, Treatment, UpliftGroup
from npa_contracts.models import ReasonCode, RiskScore, SegmentResult, UpliftResult
from npa_models.config import ModelSettings
from npa_models.early_warning import EarlyWarningModel
from npa_models.segment import SegmentModel
from npa_models.uplift import UpliftModel

log = logging.getLogger(__name__)

SCORES_SCHEMA = pa.schema(
    [
        ("account_id", pa.string()),
        ("as_of_month", pa.string()),
        ("p_roll_forward", pa.float64()),
        ("risk_band", pa.string()),
        ("reasons", pa.string()),
        ("risk_model_version", pa.string()),
        ("segment", pa.string()),
        ("segment_confidence", pa.float64()),
        ("segment_model_version", pa.string()),
        ("uplift_score", pa.float64()),
        ("uplift_group", pa.string()),
        ("recommended_treatment", pa.string()),
        ("uplift_model_version", pa.string()),
    ]
)
SCORE_COLUMNS: tuple[str, ...] = tuple(SCORES_SCHEMA.names)


class UnknownAccountError(KeyError):
    """No feature row for this account in the requested month."""


@dataclass
class _Month:
    frame: pd.DataFrame  # indexed by account_id, SCORE_COLUMNS minus reasons
    reasons: dict[str, list[ReasonCode]]


def _reasons_json(reasons: list[ReasonCode]) -> str:
    return json.dumps([r.model_dump(mode="json") for r in reasons], ensure_ascii=False)


@dataclass
class ModelProvider:
    """Implements ``npa_contracts.providers.RiskProvider`` from trained bundles."""

    early_warning: EarlyWarningModel
    segment_model: SegmentModel
    uplift_model: UpliftModel
    features: pd.DataFrame
    _months: dict[str, _Month] = field(default_factory=dict, repr=False)

    @classmethod
    def from_settings(
        cls, settings: ModelSettings | None = None, features: pd.DataFrame | None = None
    ) -> "ModelProvider":
        """Load the bundles from ``MODEL_DIR`` and ``features.parquet`` from ``DATA_DIR``."""
        settings = settings or ModelSettings()
        if features is None:
            features = pd.read_parquet(settings.data_dir / "features.parquet")
        return cls(
            early_warning=EarlyWarningModel.load(settings.model_dir),
            segment_model=SegmentModel.load(settings.model_dir),
            uplift_model=UpliftModel.load(settings.model_dir),
            features=features,
        )

    # --- batch ---------------------------------------------------------------------------

    def warm(self, as_of_month: str) -> None:
        """Score every account of ``as_of_month`` now, so later lookups are instant."""
        self._month(as_of_month)

    def _month(self, as_of_month: str) -> _Month:
        if as_of_month in self._months:
            return self._months[as_of_month]
        rows = self.features[self.features["month"] == as_of_month]
        if rows.empty:
            raise ValueError(f"no feature rows for as_of_month={as_of_month}")
        risk = self.early_warning.score_frame(rows)
        seg = self.segment_model.score_frame(rows)
        up = self.uplift_model.score_frame(rows)
        frame = pd.DataFrame(
            {
                "account_id": risk["account_id"].to_numpy(),
                "as_of_month": risk["as_of_month"].to_numpy(),
                "p_roll_forward": risk["p_roll_forward"].to_numpy(),
                "risk_band": risk["risk_band"].to_numpy(),
                "risk_model_version": self.early_warning.model_version,
                "segment": seg["segment"].to_numpy(),
                "segment_confidence": seg["confidence"].to_numpy(),
                "segment_model_version": self.segment_model.model_version,
                "uplift_score": up["uplift_score"].to_numpy(),
                "uplift_group": up["uplift_group"].to_numpy(),
                "recommended_treatment": up["recommended_treatment"].to_numpy(),
                "uplift_model_version": self.uplift_model.model_version,
            }
        )
        if frame["account_id"].duplicated().any():
            raise ValueError(f"duplicate account rows in features for {as_of_month}")
        reasons = dict(zip(frame["account_id"], self.early_warning.reasons(rows), strict=True))
        month = _Month(frame.set_index("account_id", drop=False), reasons)
        self._months[as_of_month] = month
        log.info("scored month=%s accounts=%d", as_of_month, len(frame))
        return month

    def scores_frame(self, as_of_month: str) -> pd.DataFrame:
        """All accounts of ``as_of_month`` with exactly :data:`SCORE_COLUMNS`."""
        m = self._month(as_of_month)
        out = m.frame.reset_index(drop=True)
        out["reasons"] = [_reasons_json(m.reasons[a]) for a in out["account_id"]]
        return out[list(SCORE_COLUMNS)]

    def write_scores(self, as_of_month: str, path: Path) -> Path:
        """Write ``scores.parquet`` for ``as_of_month`` (#38)."""
        table = pa.Table.from_pandas(
            self.scores_frame(as_of_month), schema=SCORES_SCHEMA, preserve_index=False
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, path)
        log.info("wrote scores rows=%d path=%s", table.num_rows, path)
        return path

    def score_batch(
        self, as_of_month: str
    ) -> Iterator[tuple[RiskScore, SegmentResult, UpliftResult]]:
        m = self._month(as_of_month)
        for account_id in m.frame.index:
            yield self._objects(m, account_id)

    # --- single lookups ------------------------------------------------------------------

    def _row(self, account_id: str, as_of_month: str) -> tuple[_Month, pd.Series]:
        m = self._month(as_of_month)
        if account_id not in m.frame.index:
            raise UnknownAccountError(f"{account_id} has no features for {as_of_month}")
        return m, m.frame.loc[account_id]

    def _objects(self, m: _Month, account_id: str) -> tuple[RiskScore, SegmentResult, UpliftResult]:
        row = m.frame.loc[account_id]
        return _risk(row, m.reasons[account_id]), _segment(row), _uplift(row)

    def risk(self, account_id: str, as_of_month: str) -> RiskScore:
        m, row = self._row(account_id, as_of_month)
        return _risk(row, m.reasons[account_id])

    def segment(self, account_id: str, as_of_month: str) -> SegmentResult:
        return _segment(self._row(account_id, as_of_month)[1])

    def uplift(self, account_id: str, as_of_month: str) -> UpliftResult:
        return _uplift(self._row(account_id, as_of_month)[1])


def _risk(row: pd.Series, reasons: list[ReasonCode]) -> RiskScore:
    return RiskScore(
        account_id=row["account_id"],
        as_of_month=row["as_of_month"],
        p_roll_forward=float(row["p_roll_forward"]),
        risk_band=RiskBand(row["risk_band"]),
        reasons=reasons,
        model_version=row["risk_model_version"],
    )


def _segment(row: pd.Series) -> SegmentResult:
    return SegmentResult(
        account_id=row["account_id"],
        segment=Segment(row["segment"]),
        confidence=float(row["segment_confidence"]),
        model_version=row["segment_model_version"],
    )


def _uplift(row: pd.Series) -> UpliftResult:
    return UpliftResult(
        account_id=row["account_id"],
        uplift_score=float(row["uplift_score"]),
        uplift_group=UpliftGroup(row["uplift_group"]),
        recommended_treatment=Treatment(row["recommended_treatment"]),
        model_version=row["uplift_model_version"],
    )

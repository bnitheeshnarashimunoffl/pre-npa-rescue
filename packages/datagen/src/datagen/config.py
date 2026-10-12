"""Runtime configuration for the data generator (A7.0, A11).

Values come from environment variables (or a ``.env`` file). Calendar and seed defaults are
imported from :mod:`npa_contracts.constants` so they are never redefined here.
"""

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from npa_contracts.constants import AS_OF_MONTH, DEFAULT_SEED, SIM_END_MONTH, SIM_START_MONTH

_MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class DatagenConfig(BaseSettings):
    """Settings for ``datagen``.

    Environment variables: ``SEED``, ``DATA_DIR``, ``RAW_DATA_DIR``, ``DATAGEN_N_CUSTOMERS``,
    ``AS_OF_MONTH``. Fields can also be passed by name (``DatagenConfig(seed=7)``).
    """

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", frozen=True, populate_by_name=True
    )

    seed: int = Field(default=DEFAULT_SEED, validation_alias="SEED")
    data_dir: Path = Field(default=Path("./data/generated"), validation_alias="DATA_DIR")
    raw_data_dir: Path = Field(default=Path("./data/raw"), validation_alias="RAW_DATA_DIR")
    n_customers: int = Field(default=10_000, gt=0, validation_alias="DATAGEN_N_CUSTOMERS")
    as_of_month: str = Field(
        default=AS_OF_MONTH, pattern=_MONTH_PATTERN, validation_alias="AS_OF_MONTH"
    )
    start_month: str = Field(default=SIM_START_MONTH, pattern=_MONTH_PATTERN)
    end_month: str = Field(default=SIM_END_MONTH, pattern=_MONTH_PATTERN)
    write_transactions: bool = True
    experiment_month: str = Field(default="2026-06", pattern=_MONTH_PATTERN)
    experiment_months: int = Field(default=6, ge=1, le=21)  # months pooled, ending experiment_month
    # Months simulated past end_month only to compute labels for the last window months.
    label_horizon_months: int = Field(default=3, ge=0, le=12)
    samples_dir: Path | None = None  # if set, `features` also writes the committed samples

    @model_validator(mode="after")
    def _check_calendar(self) -> "DatagenConfig":
        # YYYY-MM strings sort chronologically.
        if not self.start_month <= self.as_of_month <= self.end_month:
            raise ValueError(
                f"as_of_month {self.as_of_month} must lie in {self.start_month}..{self.end_month}"
            )
        return self

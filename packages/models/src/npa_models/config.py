"""Runtime settings for ``npa_models`` (env vars, A11).

Every path and the seed come from the environment so the same code runs on a laptop, in CI and
in the API container. Defaults match ``.env.example``.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from npa_contracts.constants import AS_OF_MONTH, DEFAULT_SEED


class ModelSettings(BaseSettings):
    """Settings read from ``SEED``, ``DATA_DIR``, ``MODEL_DIR`` and ``AS_OF_MONTH``."""

    # protected_namespaces=(): allow the ``model_dir`` field name (pydantic reserves ``model_``).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", protected_namespaces=())

    seed: int = DEFAULT_SEED
    data_dir: Path = Path("data/generated")
    model_dir: Path = Path("packages/models/artifacts")
    as_of_month: str = AS_OF_MONTH
    # Risk bands on calibrated p_roll_forward (task 2.1): high >= high, medium >= medium.
    risk_high_threshold: float = 0.35
    risk_medium_threshold: float = 0.15
    # Uplift (task 2.4): |uplift| < tau is "no effect"; cure value prices a cure against contact
    # cost when choosing the treatment (assumption: Rs 5,000 avoided loss per cure).
    uplift_tau: float = 0.05
    uplift_cure_value_paise: int = 500_000

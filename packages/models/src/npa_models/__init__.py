"""Early-warning, segmentation and uplift models with explanations (WS2).

Implements ``npa_contracts.providers.RiskProvider`` (task 2.1-2.4). Model inputs are restricted by
:mod:`npa_models.features`; protected attributes are never features (A3, IS/ISO/IEC TR 24027).
"""

from npa_models.config import ModelSettings
from npa_models.features import (
    FEATURE_COLUMNS,
    FORBIDDEN_COLUMNS,
    LeakageError,
    TimeSplit,
    assert_no_leakage,
    build_matrix,
    time_split,
)
from npa_models.registry import ModelBundle, load_bundle, make_model_version, save_bundle

__version__ = "0.1.0"

__all__ = [
    "FEATURE_COLUMNS",
    "FORBIDDEN_COLUMNS",
    "LeakageError",
    "ModelBundle",
    "ModelSettings",
    "TimeSplit",
    "__version__",
    "assert_no_leakage",
    "build_matrix",
    "load_bundle",
    "make_model_version",
    "save_bundle",
    "time_split",
]

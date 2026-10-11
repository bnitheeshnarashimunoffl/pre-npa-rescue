from datetime import time

import pytest

import npa_contracts
from npa_contracts import constants
from npa_contracts.enums import Bucket, Lang, ReliefType, Role


@pytest.mark.parametrize(
    ("dpd", "bucket"),
    [
        (0, Bucket.CURRENT),
        (1, Bucket.SMA0),
        (30, Bucket.SMA0),
        (31, Bucket.SMA1),
        (60, Bucket.SMA1),
        (61, Bucket.SMA2),
        (90, Bucket.SMA2),
        (91, Bucket.NPA),
        (400, Bucket.NPA),
    ],
)
def test_bucket_for_dpd(dpd: int, bucket: Bucket) -> None:
    assert constants.bucket_for_dpd(dpd) is bucket


def test_bucket_for_negative_dpd() -> None:
    with pytest.raises(ValueError):
        constants.bucket_for_dpd(-1)


def test_regulatory_constants() -> None:
    assert constants.NPA_DPD == 90
    assert constants.PAST_DUE_GRACE_DAYS == 3
    assert (time(8), time(19)) == constants.CONTACT_WINDOW
    assert constants.CALL_RECORD_RETENTION_DAYS == 180
    assert constants.MIN_SETTLEMENT_COOLING_MONTHS == 12
    assert constants.AS_OF_MONTH == constants.SIM_END_MONTH == "2026-09"


def test_enum_wire_values() -> None:
    assert [lang.value for lang in Lang] == ["en", "ta", "hi"]
    assert ReliefType("review_date") is ReliefType.REVIEW_DATE
    assert f"{Role.HARDSHIP_OFFICER}" == "hardship_officer"


def test_version() -> None:
    assert npa_contracts.__version__ == npa_contracts.CONTRACT_VERSION

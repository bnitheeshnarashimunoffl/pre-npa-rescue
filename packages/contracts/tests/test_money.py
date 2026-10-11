from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from npa_contracts.money import (
    CRORE_PAISE,
    LAKH_PAISE,
    format_inr,
    format_inr_compact,
    group_en_in,
    split_evenly,
    to_paise,
    to_rupees,
)


@pytest.mark.parametrize(
    ("rupees", "paise"),
    [(2000, 200_000), ("2000", 200_000), (Decimal("12.345"), 1235), ("0.004", 0), ("-1.005", -101)],
)
def test_to_paise(rupees: int | str | Decimal, paise: int) -> None:
    assert to_paise(rupees) == paise


@pytest.mark.parametrize("bad", [1.5, True, None, [1]])
def test_to_paise_rejects_non_decimal_types(bad: object) -> None:
    with pytest.raises(TypeError):
        to_paise(bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["Infinity", "NaN"])
def test_to_paise_rejects_non_finite(bad: str) -> None:
    with pytest.raises(ValueError):
        to_paise(bad)


def test_to_rupees() -> None:
    assert to_rupees(200_050) == Decimal("2000.50")
    with pytest.raises(TypeError):
        to_rupees(True)
    with pytest.raises(TypeError):
        to_rupees(1.0)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("n", "text"),
    [
        (0, "0"),
        (999, "999"),
        (1000, "1,000"),
        (100000, "1,00,000"),
        (1234567, "12,34,567"),
        (123456789, "12,34,56,789"),
    ],
)
def test_group_en_in(n: int, text: str) -> None:
    assert group_en_in(n) == text


def test_group_en_in_negative() -> None:
    with pytest.raises(ValueError):
        group_en_in(-1)


@pytest.mark.parametrize(
    ("paise", "kwargs", "text"),
    [
        (200_000, {}, "₹2,000"),
        (12_345_678_901, {}, "₹12,34,56,789.01"),
        (200_000, {"show_paise": True}, "₹2,000.00"),
        (200_050, {"show_paise": False}, "₹2,000"),
        (-118_000, {}, "-₹1,180"),
        (5, {"symbol": False}, "0.05"),
    ],
)
def test_format_inr(paise: int, kwargs: dict[str, bool], text: str) -> None:
    assert format_inr(paise, **kwargs) == text


@pytest.mark.parametrize(
    ("paise", "text"),
    [
        (9_999_999, "₹99,999.99"),
        (LAKH_PAISE * 2, "₹2 lakh"),
        (LAKH_PAISE * 3 // 2, "₹1.5 lakh"),
        (CRORE_PAISE, "₹1 crore"),
        (CRORE_PAISE * 125 // 100, "₹1.25 crore"),
        (-LAKH_PAISE * 2, "-₹2 lakh"),
        (LAKH_PAISE * 1234, "₹12.34 crore"),
    ],
)
def test_format_inr_compact(paise: int, text: str) -> None:
    assert format_inr_compact(paise) == text


def test_format_inr_compact_no_symbol() -> None:
    assert format_inr_compact(LAKH_PAISE, symbol=False) == "1 lakh"


def test_split_evenly() -> None:
    assert split_evenly(1_200_000, 6) == [200_000] * 6
    assert split_evenly(10, 3) == [4, 3, 3]
    for bad_total, bad_parts, exc in [
        (-1, 2, ValueError),
        (10, 0, ValueError),
        (1.0, 2, TypeError),
    ]:
        with pytest.raises(exc):
            split_evenly(bad_total, bad_parts)  # type: ignore[arg-type]


@given(st.integers(min_value=-(10**15), max_value=10**15))
def test_format_inr_roundtrip(paise: int) -> None:
    text = format_inr(paise, show_paise=True, symbol=False).replace(",", "")
    assert to_paise(text) == paise


@given(st.integers(min_value=0, max_value=10**12), st.integers(min_value=1, max_value=360))
def test_split_evenly_properties(total: int, parts: int) -> None:
    out = split_evenly(total, parts)
    assert sum(out) == total
    assert len(out) == parts
    assert max(out) - min(out) <= 1
    assert out == sorted(out, reverse=True)

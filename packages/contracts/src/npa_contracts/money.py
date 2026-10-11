"""Money helpers (contract A7.0).

All money is an ``int`` number of **paise**. Floats are rejected everywhere: use ``int``,
``Decimal`` or a decimal ``str``. Rounding is half-up and happens only in
:func:`to_paise` and :func:`format_inr_compact`. Display formatting uses Indian digit
grouping (en-IN): ``₹1,00,000`` / ``₹2 lakh`` / ``₹1.5 crore``.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Final

PAISE_PER_RUPEE: Final = 100
LAKH_PAISE: Final = 100_000 * PAISE_PER_RUPEE
CRORE_PAISE: Final = 10_000_000 * PAISE_PER_RUPEE
RUPEE_SIGN: Final = "₹"


def _check_paise(paise: int) -> int:
    # bool is a subclass of int; reject it explicitly so True never means 1 paisa.
    if isinstance(paise, bool) or not isinstance(paise, int):
        raise TypeError(f"paise must be int, got {type(paise).__name__}")
    return paise


def to_paise(rupees: int | str | Decimal) -> int:
    """Convert rupees to paise, rounding half-up to the nearest paisa.

    >>> to_paise("2000")
    200000
    >>> to_paise(Decimal("12.345"))
    1235
    """
    if isinstance(rupees, bool) or not isinstance(rupees, int | str | Decimal):
        raise TypeError(f"rupees must be int, str or Decimal (never float), got {rupees!r}")
    value = Decimal(rupees) * PAISE_PER_RUPEE
    if not value.is_finite():
        raise ValueError(f"rupees must be finite, got {rupees!r}")
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def to_rupees(paise: int) -> Decimal:
    """Exact rupee value of ``paise`` as a ``Decimal`` with two places."""
    return (Decimal(_check_paise(paise)) / PAISE_PER_RUPEE).quantize(Decimal("0.01"))


def group_en_in(n: int) -> str:
    """Group a non-negative integer the Indian way: 1234567 -> ``12,34,567``."""
    if n < 0:
        raise ValueError("group_en_in expects a non-negative integer")
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    groups.insert(0, head)
    return ",".join(groups) + "," + tail


def format_inr(paise: int, *, show_paise: bool | None = None, symbol: bool = True) -> str:
    """Format paise as Indian rupees with en-IN grouping.

    ``show_paise=None`` shows the paise only when they are non-zero.

    >>> format_inr(200000)
    '₹2,000'
    >>> format_inr(12345678901)
    '₹12,34,56,789.01'
    """
    _check_paise(paise)
    sign = "-" if paise < 0 else ""
    rupees, rem = divmod(abs(paise), PAISE_PER_RUPEE)
    text = group_en_in(rupees)
    if show_paise or (show_paise is None and rem):
        text += f".{rem:02d}"
    return f"{sign}{RUPEE_SIGN if symbol else ''}{text}"


def format_inr_compact(paise: int, *, symbol: bool = True) -> str:
    """Short form for large amounts: ``₹2 lakh``, ``₹1.5 crore``; plain :func:`format_inr`
    below one lakh. Up to two decimals, rounded half-up, trailing zeros dropped."""
    _check_paise(paise)
    magnitude = abs(paise)
    if magnitude < LAKH_PAISE:
        return format_inr(paise, symbol=symbol)
    unit, size = ("crore", CRORE_PAISE) if magnitude >= CRORE_PAISE else ("lakh", LAKH_PAISE)
    value = (Decimal(magnitude) / size).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    number = format(value.normalize(), "f")
    sign = "-" if paise < 0 else ""
    return f"{sign}{RUPEE_SIGN if symbol else ''}{number} {unit}"


def split_evenly(total_paise: int, parts: int) -> list[int]:
    """Split ``total_paise`` into ``parts`` integer instalments that sum exactly to the total.

    The remainder goes to the earliest instalments (never negative amortisation).
    """
    _check_paise(total_paise)
    if total_paise < 0:
        raise ValueError("total_paise must be >= 0")
    if parts <= 0:
        raise ValueError("parts must be > 0")
    base, rem = divmod(total_paise, parts)
    return [base + 1 if i < rem else base for i in range(parts)]

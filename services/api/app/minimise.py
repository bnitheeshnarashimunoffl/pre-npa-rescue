"""Data minimisation per role (task 5.3).

RBI RBC Directions para 454O: share borrower data with staff only as far as needed for
recovery. DPDP Act 2023: purpose limitation and data minimisation. Protected attributes are
never part of a profile at all (they live in a separate table no route reads).

| Role | Sees |
|---|---|
| customer (self only) | their whole profile |
| collector | identity, language, masked phone/email, preferred contact window |
| hardship_officer | collector fields + occupation, insurance cover, card limit, age, city |
| admin | whole profile |
| auditor | identity and language only (logs and red-team results are separate routes) |

Phone numbers and email addresses are always masked, whoever asks.
"""

from typing import Any, Final

from app.security import Principal
from npa_contracts.api import CustomerProfile
from npa_contracts.enums import Role

_IDENTITY: Final = {"customer_id", "account_id", "full_name", "language_pref"}
_CONTACT: Final = {"phone_masked", "email_masked", "preferred_contact_window"}
_HARDSHIP: Final = {
    "occupation_type",
    "has_card_insurance",
    "insurance_cover_type",
    "card_limit_paise",
    "age",
    "city",
}
_ALL: Final = frozenset(CustomerProfile.model_fields)

VISIBLE_FIELDS: Final[dict[Role, frozenset[str]]] = {
    Role.CUSTOMER: _ALL,
    Role.COLLECTOR: frozenset(_IDENTITY | _CONTACT),
    Role.HARDSHIP_OFFICER: frozenset(_IDENTITY | _CONTACT | _HARDSHIP),
    Role.ADMIN: _ALL,
    Role.AUDITOR: frozenset(_IDENTITY),
}


def mask_phone(phone: str | None) -> str | None:
    """Keep the country code and last two digits: ``+91-9876543221`` -> ``+91-98XXXXXX21``
    style. Already-masked values pass through unchanged."""
    if not phone or "X" in phone:
        return phone
    digits = [i for i, ch in enumerate(phone) if ch.isdigit()]
    keep = set(digits[:4] + digits[-2:])  # "+91-98..." prefix and the last two digits
    return "".join(ch if (i in keep or not ch.isdigit()) else "X" for i, ch in enumerate(phone))


def mask_email(email: str | None) -> str | None:
    """``priya.raman@example.com`` -> ``p****@example.com``. Already-masked values pass."""
    if not email or "*" in email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    return f"{local[:1]}****@{domain}"


def minimise_profile(profile: CustomerProfile, principal: Principal) -> CustomerProfile:
    """Return ``profile`` with every field the caller's role may not see set to ``None``.

    Callers must already have checked scope (``ensure_customer_scope``) for customers.
    """
    visible = VISIBLE_FIELDS[principal.role]
    data: dict[str, Any] = {
        name: (value if name in visible else None) for name, value in profile.model_dump().items()
    }
    data["phone_masked"] = mask_phone(data["phone_masked"])
    data["email_masked"] = mask_email(data["email_masked"])
    return CustomerProfile.model_validate(data)

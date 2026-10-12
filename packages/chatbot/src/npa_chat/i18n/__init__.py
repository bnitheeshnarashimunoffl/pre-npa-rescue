"""Internationalisation (i18n) loader and string resolution."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from npa_contracts.enums import Lang

_I18N_DIR = Path(__file__).parent


@lru_cache(maxsize=4)
def get_bundle(lang: Lang | str = Lang.EN) -> dict[str, str]:
    """Load JSON string bundle for the requested language with fallback to English."""
    lang_code = str(lang).lower()
    file_path = _I18N_DIR / f"{lang_code}.json"
    if not file_path.exists():
        file_path = _I18N_DIR / "en.json"

    with open(file_path, encoding="utf-8") as f:
        data: dict[str, str] = json.load(f)
    return data


def get_string(key: str, lang: Lang | str = Lang.EN, **kwargs: Any) -> str:
    """Retrieve translated template string, with en fallback and parameter substitution."""
    bundle = get_bundle(lang)
    template = bundle.get(key)
    if template is None:
        en_bundle = get_bundle(Lang.EN)
        template = en_bundle.get(key, key)

    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError):
            return template
    return template


__all__ = ["get_bundle", "get_string"]

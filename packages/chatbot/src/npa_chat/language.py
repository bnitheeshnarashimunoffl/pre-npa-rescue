"""Language detection and dynamic switching for WS4 Chatbot."""

from __future__ import annotations

import re
from typing import Final

from npa_contracts.enums import Lang

# Unicode script ranges
_TAMIL_REGEX: Final[re.Pattern[str]] = re.compile(r"[\u0B80-\u0BFF]")
_DEVANAGARI_REGEX: Final[re.Pattern[str]] = re.compile(r"[\u0900-\u097F]")

# Explicit language switch keywords
_LANG_SWITCH_MAP: Final[dict[str, Lang]] = {
    # Tamil triggers
    "tamil": Lang.TA,
    "தமிழ்": Lang.TA,
    "tamizh": Lang.TA,
    "thamizh": Lang.TA,
    "lang_ta": Lang.TA,
    # Hindi triggers
    "hindi": Lang.HI,
    "हिन्दी": Lang.HI,
    "हिंदी": Lang.HI,
    "lang_hi": Lang.HI,
    # English triggers
    "english": Lang.EN,
    "ஆங்கிலம்": Lang.EN,
    "अंग्रेजी": Lang.EN,
    "lang_en": Lang.EN,
}

_SWITCH_PHRASES: Final[list[tuple[re.Pattern[str], Lang]]] = [
    (re.compile(r"\b(tamil|தமிழ்|tamizh|thamizh)\b", re.IGNORECASE), Lang.TA),
    (re.compile(r"\b(hindi|हिन्दी|हिंदी)\b", re.IGNORECASE), Lang.HI),
    (re.compile(r"\b(english|ஆங்கிலம்|अंग्रेजी)\b", re.IGNORECASE), Lang.EN),
    (re.compile(r"(தமிழில்|தமிழ்ல)", re.IGNORECASE), Lang.TA),
    (re.compile(r"(हिंदी\s*में|हिन्दी\s*में)", re.IGNORECASE), Lang.HI),
    (re.compile(r"in\s+english", re.IGNORECASE), Lang.EN),
]


def detect_script(text: str) -> Lang | None:
    """Detect language based on Unicode script frequency."""
    tamil_chars = len(_TAMIL_REGEX.findall(text))
    devanagari_chars = len(_DEVANAGARI_REGEX.findall(text))

    if tamil_chars > 0 and tamil_chars >= devanagari_chars:
        return Lang.TA
    if devanagari_chars > 0 and devanagari_chars > tamil_chars:
        return Lang.HI
    return None


def detect_language_switch_request(text: str) -> Lang | None:
    """Identify if the user is requesting to switch languages."""
    cleaned = text.strip().lower()
    if cleaned in _LANG_SWITCH_MAP:
        return _LANG_SWITCH_MAP[cleaned]

    for pattern, target_lang in _SWITCH_PHRASES:
        if pattern.search(cleaned):
            return target_lang
    return None


def resolve_language(text: str, current_lang: Lang, requested_lang: Lang | None = None) -> Lang:
    """Determine the effective language for the current turn."""
    if requested_lang is not None:
        return requested_lang

    switch_req = detect_language_switch_request(text)
    if switch_req is not None:
        return switch_req

    script_lang = detect_script(text)
    if script_lang is not None:
        return script_lang

    return current_lang

"""Tests for script detection and language switching."""

from npa_chat.language import (
    detect_language_switch_request,
    detect_script,
    resolve_language,
)
from npa_contracts.enums import Lang


def test_detect_script() -> None:
    assert detect_script("வணக்கம் எப்படி இருக்கிறீர்கள்") == Lang.TA
    assert detect_script("नमस्ते आप कैसे हैं") == Lang.HI
    assert detect_script("Hello, how are you?") is None


def test_detect_language_switch_request() -> None:
    assert detect_language_switch_request("Tamil please") == Lang.TA
    assert detect_language_switch_request("தமிழில்") == Lang.TA
    assert detect_language_switch_request("lang_ta") == Lang.TA

    assert detect_language_switch_request("Hindi please") == Lang.HI
    assert detect_language_switch_request("हिंदी में") == Lang.HI
    assert detect_language_switch_request("lang_hi") == Lang.HI

    assert detect_language_switch_request("English please") == Lang.EN
    assert detect_language_switch_request("in english") == Lang.EN
    assert detect_language_switch_request("lang_en") == Lang.EN

    assert detect_language_switch_request("I lost my job") is None


def test_resolve_language_precedence() -> None:
    # Explicit override has highest priority
    assert resolve_language("hello", current_lang=Lang.EN, requested_lang=Lang.TA) == Lang.TA

    # Switch request overrides current
    assert resolve_language("தமிழ் please", current_lang=Lang.EN) == Lang.TA

    # Native script overrides default
    assert resolve_language("வணக்கம்", current_lang=Lang.EN) == Lang.TA
    assert resolve_language("नमस्ते", current_lang=Lang.EN) == Lang.HI

    # Fallback maintains current language
    assert resolve_language("Okay, sure", current_lang=Lang.TA) == Lang.TA

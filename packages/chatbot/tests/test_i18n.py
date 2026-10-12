"""Tests for internationalisation (i18n) bundle resolution."""

from npa_chat.i18n import get_bundle, get_string
from npa_contracts.enums import Lang


def test_i18n_bundles_contain_required_keys() -> None:
    required_keys = [
        "greeting",
        "recording_notice",
        "dpdp_notice",
        "grievance_footer",
        "tele_manas_helpline",
        "fallback_safe",
    ]
    for lang in [Lang.EN, Lang.TA, Lang.HI]:
        bundle = get_bundle(lang)
        for key in required_keys:
            assert key in bundle, f"Missing key '{key}' in bundle for language '{lang}'"


def test_i18n_formatting_and_substitutions() -> None:
    en_greeting = get_string("greeting", Lang.EN, name="Priya")
    assert "Priya" in en_greeting
    assert "assist you" in en_greeting

    ta_greeting = get_string("greeting", Lang.TA, name="பிரியா")
    assert "பிரியா" in ta_greeting
    assert "வணக்கம்" in ta_greeting

    hi_greeting = get_string("greeting", Lang.HI, name="प्रिया")
    assert "प्रिया" in hi_greeting
    assert "नमस्ते" in hi_greeting


def test_i18n_tele_manas_helpline_constant() -> None:
    # Tele-MANAS helpline is 14416 across all locales
    for lang in [Lang.EN, Lang.TA, Lang.HI]:
        assert get_string("tele_manas_helpline", lang) == "14416"


def test_i18n_fallback_for_unknown_key() -> None:
    res = get_string("non_existent_key_123", Lang.TA)
    assert res == "non_existent_key_123"

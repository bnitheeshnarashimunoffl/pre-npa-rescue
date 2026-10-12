"""Mandatory trade-off texts shown with every relief option (keys used for i18n).

Each ``ReliefOption.disclosure_keys`` entry is a key in :data:`DISCLOSURES`. WS4 must show
them whenever an option is presented and WS6 shows them on offer cards.

The texts are truthful, plain and non-threatening: RBI RBC Directions para 454Z(8), no false
or misleading statements about the debt or the consequences of non-payment. They never
promise an interest freeze, a payment holiday or "no credit-bureau impact".

English is the reviewed source text. Tamil and Hindi are first drafts marked
``needs_review`` until a native speaker signs them off (IS 17802 plain-language goal).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from npa_contracts.enums import Lang

__all__ = ["DISCLOSURES", "Disclosure", "disclosure_text", "missing_disclosure_keys"]


@dataclass(frozen=True, slots=True)
class Disclosure:
    key: str
    text: Mapping[Lang, str]
    needs_review: frozenset[Lang] = field(default=frozenset({Lang.TA, Lang.HI}))


def _d(key: str, en: str, ta: str, hi: str) -> Disclosure:
    return Disclosure(key=key, text=MappingProxyType({Lang.EN: en, Lang.TA: ta, Lang.HI: hi}))


_ALL = (
    _d(
        "disc.fee_waiver.stops_growth",
        "We will remove the late fees shown in this offer, so those fees no longer add to what "
        "you owe. Interest on your remaining card balance still applies as shown in your "
        "statement.",
        "இந்தச் சலுகையில் காட்டப்பட்டுள்ள தாமதக் கட்டணங்களை நாங்கள் நீக்குவோம்; அவை இனி "
        "உங்கள் நிலுவையில் சேராது. மீதமுள்ள அட்டை நிலுவைக்கான வட்டி உங்கள் அறிக்கையில் "
        "காட்டியபடி தொடரும்.",
        "इस ऑफ़र में दिखाए गए विलंब शुल्क हम हटा देंगे, इसलिए वे आपकी बकाया राशि में नहीं "
        "जुड़ेंगे। बचे हुए कार्ड बैलेंस पर ब्याज आपके स्टेटमेंट के अनुसार लगता रहेगा।",
    ),
    _d(
        "disc.emi.principal_interest_shown",
        "Each monthly instalment is shown split into the amount you owe and the interest on it. "
        "You will see the total interest for the whole plan before you agree.",
        "ஒவ்வொரு மாதத் தவணையும் நீங்கள் செலுத்த வேண்டிய தொகை மற்றும் அதற்கான வட்டி எனப் "
        "பிரித்துக் காட்டப்படும். ஒப்புக்கொள்வதற்கு முன் முழுத் திட்டத்திற்கான மொத்த "
        "வட்டியைப் பார்க்கலாம்.",
        "हर मासिक किस्त में मूल बकाया और उस पर ब्याज अलग-अलग दिखाया जाता है। सहमति देने से "
        "पहले आप पूरी योजना का कुल ब्याज देख सकेंगे।",
    ),
    _d(
        "disc.restructuring.npa_downgrade",
        "If your repayment plan is restructured, your account will be classified as a "
        "non-performing asset. It can be upgraded after you repay as agreed for the required "
        "period.",
        "உங்கள் திருப்பிச் செலுத்தும் திட்டம் மறுசீரமைக்கப்பட்டால், உங்கள் கணக்கு செயல்படாத "
        "சொத்தாக (NPA) வகைப்படுத்தப்படும். ஒப்புக்கொண்டபடி தேவையான காலம் செலுத்திய பிறகு அது "
        "மேம்படுத்தப்படலாம்.",
        "अगर आपकी भुगतान योजना का पुनर्गठन होता है, तो आपका खाता गैर-निष्पादित आस्ति (NPA) के "
        "रूप में वर्गीकृत होगा। तय अवधि तक सहमति के अनुसार भुगतान करने के बाद इसे अपग्रेड किया "
        "जा सकता है।",
    ),
    _d(
        "disc.restructuring.upgrade_after_performance",
        "Your account returns to standard status only after you have paid as agreed for the "
        "period set in the bank's policy. A hardship officer will tell you that period before "
        "you agree.",
        "வங்கியின் கொள்கையில் குறிப்பிட்ட காலம் வரை ஒப்புக்கொண்டபடி செலுத்திய பிறகே உங்கள் "
        "கணக்கு சாதாரண நிலைக்குத் திரும்பும். நீங்கள் ஒப்புக்கொள்வதற்கு முன் அந்தக் காலத்தை "
        "கஷ்டநிலை அலுவலர் உங்களுக்குத் தெரிவிப்பார்.",
        "बैंक की नीति में तय अवधि तक सहमति के अनुसार भुगतान करने के बाद ही आपका खाता मानक "
        "स्थिति में लौटता है। सहमति से पहले हार्डशिप अधिकारी आपको यह अवधि बताएंगे।",
    ),
    _d(
        "disc.settlement.cooling_period",
        "After a settlement, the bank will not offer you new credit for at least 12 months.",
        "தீர்வுக்குப் பிறகு, குறைந்தது 12 மாதங்களுக்கு வங்கி உங்களுக்குப் புதிய கடன் வழங்காது.",
        "समझौते के बाद, बैंक आपको कम से कम 12 महीनों तक नया क्रेडिट नहीं देगा।",
    ),
    _d(
        "disc.settlement.over_3_months_is_restructuring",
        "If a settlement is paid over more than 3 months, it is treated as a restructuring, and "
        "the restructuring rules explained to you also apply.",
        "தீர்வுத் தொகை 3 மாதங்களுக்கு மேல் செலுத்தப்பட்டால், அது மறுசீரமைப்பாகக் "
        "கருதப்படும்; உங்களுக்கு விளக்கப்பட்ட மறுசீரமைப்பு விதிகளும் பொருந்தும்.",
        "अगर समझौते की राशि 3 महीने से अधिक समय में चुकाई जाती है, तो इसे पुनर्गठन माना जाता है "
        "और आपको बताए गए पुनर्गठन के नियम भी लागू होते हैं।",
    ),
    _d(
        "disc.settlement.bureau_reporting",
        "A settlement is reported to credit bureaus as settled, not as paid in full, and this "
        "can affect future loans. The bank updates the credit bureaus within 30 days of the "
        "settlement.",
        "தீர்வு, முழுமையாகச் செலுத்தப்பட்டதாக அல்லாமல் 'தீர்வு செய்யப்பட்டது' என்று கடன் "
        "தகவல் நிறுவனங்களுக்குத் தெரிவிக்கப்படும்; இது எதிர்காலக் கடன்களைப் பாதிக்கலாம். "
        "தீர்வுக்குப் பின் 30 நாட்களுக்குள் வங்கி அவற்றைப் புதுப்பிக்கும்.",
        "समझौते की जानकारी क्रेडिट ब्यूरो को 'पूरा भुगतान' नहीं, बल्कि 'सेटल्ड' के रूप में दी "
        "जाती है, और इससे भविष्य के ऋण प्रभावित हो सकते हैं। बैंक समझौते के 30 दिनों के भीतर "
        "क्रेडिट ब्यूरो को अपडेट करता है।",
    ),
    _d(
        "disc.insurance.claim_process",
        "Your card may include insurance cover. The insurer decides a claim under the policy "
        "terms, so payment is not guaranteed. A hardship officer can help you start a claim.",
        "உங்கள் அட்டையில் காப்பீட்டுப் பாதுகாப்பு இருக்கலாம். காப்பீட்டு விதிமுறைகளின்படி "
        "காப்பீட்டு நிறுவனமே கோரிக்கையை முடிவு செய்யும்; எனவே பணம் கிடைக்கும் என்று உறுதி "
        "இல்லை. கோரிக்கையைத் தொடங்க கஷ்டநிலை அலுவலர் உதவுவார்.",
        "आपके कार्ड में बीमा कवर हो सकता है। दावे का फ़ैसला बीमा कंपनी पॉलिसी की शर्तों के अनुसार "
        "करती है, इसलिए भुगतान की गारंटी नहीं है। दावा शुरू करने में हार्डशिप अधिकारी आपकी मदद "
        "कर सकते हैं।",
    ),
    _d(
        "disc.review.what_happens_next",
        "No payment is asked from you now. A hardship officer will review your situation with "
        "you on the agreed date. Your dues stay on your account and appear in your statements, "
        "and charges may still apply under your card terms.",
        "இப்போது உங்களிடம் எந்தப் பணமும் கேட்கப்படவில்லை. ஒப்புக்கொண்ட தேதியில் கஷ்டநிலை "
        "அலுவலர் உங்களுடன் உங்கள் நிலையை மறுபரிசீலனை செய்வார். உங்கள் நிலுவை கணக்கில் "
        "தொடர்ந்து அறிக்கைகளில் காட்டப்படும்; அட்டை விதிமுறைகளின்படி கட்டணங்கள் பொருந்தலாம்.",
        "अभी आपसे कोई भुगतान नहीं माँगा जा रहा है। तय तारीख़ पर हार्डशिप अधिकारी आपके साथ आपकी "
        "स्थिति की समीक्षा करेंगे। आपकी बकाया राशि खाते में बनी रहेगी और स्टेटमेंट में दिखेगी, "
        "और कार्ड की शर्तों के अनुसार शुल्क लग सकते हैं।",
    ),
)

DISCLOSURES: Mapping[str, Disclosure] = MappingProxyType({d.key: d for d in _ALL})


def disclosure_text(key: str, lang: Lang) -> str:
    """Text of disclosure ``key`` in ``lang``. Raises ``KeyError`` for an unknown key."""
    return DISCLOSURES[key].text[lang]


def missing_disclosure_keys(keys: list[str] | tuple[str, ...]) -> list[str]:
    """The keys in ``keys`` that have no text (used to validate the policy file)."""
    return [k for k in keys if k not in DISCLOSURES]

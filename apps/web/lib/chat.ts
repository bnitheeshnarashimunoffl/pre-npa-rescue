export type ChatLang = 'en' | 'ta' | 'hi';

export function isChatLang(value: string): value is ChatLang {
    return value === 'en' || value === 'ta' || value === 'hi';
}

export type QuickReply = { id: string; label: string };

export type ReliefOption = {
    option_id: string;
    type: string;
    monthly_amount_paise: number | null;
    tenure_months: number | null;
    waiver_paise: number | null;
    settlement_amount_paise: number | null;
    disclosure_keys: string[];
    requires_human_approval: boolean;
    eligibility_reason: string;
};

export type Offer = { offer_id: string; option: ReliefOption; status: string };

export type Callback = {
    callback_id: string;
    role: string;
    slot_start: string;
    slot_end: string;
    summary: string;
    created_at: string;
};

export type BotReply = {
    session_id: string;
    text: string;
    lang: string;
    quick_replies: QuickReply[];
    offers: Offer[];
    handoff: Callback | null;
    flags: string[];
    state: string;
};

export type GrievanceOfficer = { name: string; email: string; phone: string; address: string };

export const FONT_BY_LANG: Record<ChatLang, string> = {
    en: 'var(--font-sans), system-ui, sans-serif',
    ta: 'var(--font-tamil), var(--font-sans), system-ui, sans-serif',
    hi: 'var(--font-devanagari), var(--font-sans), system-ui, sans-serif'
};

const LOCALE_TAG: Record<ChatLang, string> = { en: 'en-IN', ta: 'ta-IN', hi: 'hi-IN' };

export function formatPaise(paise: number): string {
    return new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        maximumFractionDigits: 0
    }).format(paise / 100);
}

export function formatSlot(startIso: string, endIso: string, lang: ChatLang) {
    const tz = 'Asia/Kolkata';
    const date = new Intl.DateTimeFormat(LOCALE_TAG[lang], {
        timeZone: tz,
        day: 'numeric',
        month: 'long',
        year: 'numeric'
    }).format(new Date(startIso));
    const time = new Intl.DateTimeFormat('en-GB', {
        timeZone: tz,
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    });
    return { date, start: time.format(new Date(startIso)), end: time.format(new Date(endIso)) };
}

export function buildIcs(cb: Callback, title: string): string {
    const stamp = (iso: string) =>
        new Date(iso).toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
    return [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Pre-NPA Rescue//EN',
        'BEGIN:VEVENT',
        `UID:${cb.callback_id}@pre-npa-rescue`,
        `DTSTAMP:${stamp(cb.created_at)}`,
        `DTSTART:${stamp(cb.slot_start)}`,
        `DTEND:${stamp(cb.slot_end)}`,
        `SUMMARY:${title}`,
        'END:VEVENT',
        'END:VCALENDAR'
    ].join('\r\n');
}

// Mandatory trade-off texts, looked up by whatever disclosure key the API/fixtures return.
// Texts here are drafts: replace with WS3's disclosures.py wording if it differs,
// and have the Tamil and Hindi reviewed by a native speaker (see messages/REVIEW.md).
const DISCLOSURES: Record<string, Record<ChatLang, string>> = {
    'disclosure.emi_conversion.interest_breakdown': {
        en: 'Converting your balance to instalments includes interest. The interest and the total you will pay are shown with the plan before anything is confirmed.',
        ta: 'உங்கள் நிலுவைத் தொகையை தவணைகளாக மாற்றும்போது வட்டியும் சேரும். எதுவும் உறுதி செய்யப்படுவதற்கு முன், வட்டியும் நீங்கள் செலுத்தும் மொத்தத் தொகையும் திட்டத்துடன் காட்டப்படும்.',
        hi: 'बकाया राशि को किस्तों में बदलने पर उसमें ब्याज जुड़ता है। कुछ भी पक्का होने से पहले ब्याज और आपकी कुल देय राशि योजना के साथ दिखाई जाएगी।'
    },
    'disclosure.fee_waiver.scope': {
        en: 'The waiver covers only the late fees on this account. It does not reduce the amount you owe on your purchases.',
        ta: 'இந்தத் தள்ளுபடி இந்தக் கணக்கின் தாமதக் கட்டணங்களுக்கு மட்டுமே. உங்கள் கொள்முதல் நிலுவைத் தொகையைக் குறைக்காது.',
        hi: 'यह माफी केवल इस खाते के विलंब शुल्क पर लागू है। इससे आपकी खरीदारी की बकाया राशि कम नहीं होती।'
    },
    'disclosure.missed_instalment.consequence': {
        en: 'If an instalment is missed, late charges may apply again and the missed payment may be reported to credit bureaus as per RBI rules.',
        ta: 'ஒரு தவணை தவறினால், தாமதக் கட்டணம் மீண்டும் விதிக்கப்படலாம்; RBI விதிகளின்படி தவறிய தவணை கடன் தகவல் நிறுவனங்களுக்குத் தெரிவிக்கப்படலாம்.',
        hi: 'यदि कोई किस्त छूट जाती है तो विलंब शुल्क फिर से लग सकता है और RBI नियमों के अनुसार छूटे भुगतान की जानकारी क्रेडिट ब्यूरो को दी जा सकती है।'
    }
};

function lastSegment(key: string): string {
    const parts = key.split('.');
    return parts[parts.length - 1] ?? key;
}

export function disclosureText(key: string, lang: ChatLang): string {
    const exact = DISCLOSURES[key];
    if (exact) return exact[lang];
    const wanted = lastSegment(key);
    const match = Object.keys(DISCLOSURES).find((k) => lastSegment(k) === wanted);
    const found = match ? DISCLOSURES[match] : undefined;
    if (found) return found[lang];
    const readable = key.split('.').slice(1).join(' ').replace(/_/g, ' ').trim();
    return readable ? readable.charAt(0).toUpperCase() + readable.slice(1) : key;
}

export type ChatStrings = {
    title: string;
    subtitle: string;
    recorded: string;
    neverAsk: string;
    contactHours: string;
    greeting: string;
    suggestedLabel: string;
    suggested: string;
    placeholder: string;
    send: string;
    typing: string;
    botName: string;
    you: string;
    followUp: string;
    detailsAbove: string;
    officerCall: string;
    changeTime: string;
    grievanceTitle: string;
    grievanceIntro: string;
    grievanceUnresolved: string;
    ombudsman: string;
    accepted: string;
    declined: string;
    offerEmi: string;
    offerFee: string;
    offerFallback: string;
    monthly: string;
    duration: string;
    months: (n: number) => string;
    waived: string;
    readBefore: string;
    accept: string;
    notNow: string;
    needsOfficer: string;
    acceptedBadge: string;
    declinedBadge: string;
    callbackTitle: string;
    officerRole: string;
    callbackNote: string;
    addToCalendar: string;
    icsTitle: string;
};

export const CHAT_TEXT: Record<ChatLang, ChatStrings> = {
    en: {
        title: 'Hardship support',
        subtitle: 'A safe place to explain what happened',
        recorded: 'This chat is recorded.',
        neverAsk: 'We will never ask for your OTP, PIN or CVV.',
        contactHours: 'Calls only between 08:00 and 19:00 IST',
        greeting:
            'Hello. If paying your card bill has become difficult, you can tell me what happened here, without any judgement. We will look at what works for you together.',
        suggestedLabel: 'Suggested message',
        suggested: 'I lost my job and I cannot pay anything right now.',
        placeholder: 'Type your message',
        send: 'Send',
        typing: 'Typing…',
        botName: 'Bank assistant',
        you: 'You',
        followUp:
            'Thank you, I have noted that. You can accept the plan above, ask for more details, or ask to speak with an officer. There is no pressure.',
        detailsAbove:
            'All the details, including interest and what happens if an instalment is missed, are on the plan card above.',
        officerCall:
            'Of course. A hardship officer can call you between 08:00 and 19:00. Please tell us a time that suits you.',
        changeTime:
            'Sure. Please tell us a time between 08:00 and 19:00 that suits you, and the officer will call then.',
        grievanceTitle: 'Grievance officer',
        grievanceIntro: 'Here are the details of our grievance officer. You can contact them at any time.',
        grievanceUnresolved: 'If your complaint is not resolved within 30 days, you can approach the RBI Ombudsman.',
        ombudsman: 'RBI complaint portal',
        accepted: 'Thank you. Your acceptance is recorded. A bank officer will confirm the plan.',
        declined: 'No problem. There is no pressure. You can come back anytime or ask to speak to an officer.',
        offerEmi: 'Instalment plan (EMI)',
        offerFee: 'Late fee waiver',
        offerFallback: 'Relief option',
        monthly: 'Monthly payment',
        duration: 'Duration',
        months: (n) => (n === 1 ? '1 month' : `${n} months`),
        waived: 'Late fees waived',
        readBefore: 'Please read before you accept',
        accept: 'I accept',
        notNow: 'Not now',
        needsOfficer: 'A bank officer must confirm this plan',
        acceptedBadge: 'Accepted',
        declinedBadge: 'Not now',
        callbackTitle: 'Callback booked',
        officerRole: 'Hardship officer',
        callbackNote: 'Shared with the officer',
        addToCalendar: 'Add to calendar',
        icsTitle: 'Call from hardship officer'
    },
    ta: {
        title: 'நிதி நெருக்கடி உதவி',
        subtitle: 'என்ன நடந்தது என்பதைப் பாதுகாப்பாகச் சொல்லுங்கள்',
        recorded: 'இந்த உரையாடல் பதிவு செய்யப்படுகிறது.',
        neverAsk: 'உங்கள் OTP, PIN அல்லது CVV ஐ நாங்கள் ஒருபோதும் கேட்க மாட்டோம்.',
        contactHours: 'அழைப்புகள் காலை 08:00 முதல் மாலை 19:00 (IST) வரை மட்டுமே',
        greeting:
            'வணக்கம். கார்டு கட்டணம் செலுத்துவது கடினமாக இருந்தால், என்ன நடந்தது என்பதை இங்கே தயங்காமல் சொல்லலாம். யாரும் உங்களைக் குறை சொல்ல மாட்டார்கள். உங்களுக்கு ஏற்ற வழியை சேர்ந்து பார்ப்போம்.',
        suggestedLabel: 'பரிந்துரைக்கப்பட்ட செய்தி',
        suggested: 'என் வேலை போய்விட்டது. இந்த மாதம் முழுத் தொகையையும் என்னால் கட்ட முடியாது.',
        placeholder: 'உங்கள் செய்தியை எழுதுங்கள்',
        send: 'அனுப்பு',
        typing: 'தட்டச்சு செய்கிறது…',
        botName: 'வங்கி உதவியாளர்',
        you: 'நீங்கள்',
        followUp:
            'நன்றி, குறித்துக்கொண்டேன். மேலுள்ள திட்டத்தை ஏற்கலாம், கூடுதல் விவரங்களைக் கேட்கலாம் அல்லது அதிகாரியிடம் பேசச் சொல்லலாம். எந்த அழுத்தமும் இல்லை.',
        detailsAbove:
            'வட்டி மற்றும் தவணை தவறினால் என்ன நடக்கும் என்பது உட்பட அனைத்து விவரங்களும் மேலுள்ள திட்ட அட்டையில் உள்ளன.',
        officerCall:
            'சரி. நிதி நெருக்கடி உதவி அதிகாரி காலை 08:00 முதல் மாலை 19:00 வரை உங்களை அழைக்கலாம். உங்களுக்கு ஏற்ற நேரத்தைச் சொல்லுங்கள்.',
        changeTime:
            'சரி. காலை 08:00 முதல் மாலை 19:00க்குள் உங்களுக்கு ஏற்ற நேரத்தைச் சொல்லுங்கள், அந்த நேரத்தில் அதிகாரி அழைப்பார்.',
        grievanceTitle: 'குறை தீர்க்கும் அதிகாரி',
        grievanceIntro: 'எங்கள் குறை தீர்க்கும் அதிகாரியின் விவரங்கள் இதோ. எப்போது வேண்டுமானாலும் அவரைத் தொடர்புகொள்ளலாம்.',
        grievanceUnresolved: '30 நாட்களுக்குள் உங்கள் புகார் தீர்க்கப்படாவிட்டால், RBI ஒம்புட்ஸ்மேனை அணுகலாம்.',
        ombudsman: 'RBI புகார் தளம்',
        accepted: 'நன்றி. உங்கள் ஒப்புதல் பதிவு செய்யப்பட்டது. வங்கி அதிகாரி திட்டத்தை உறுதிப்படுத்துவார்.',
        declined: 'பரவாயில்லை. எந்த அழுத்தமும் இல்லை. எப்போது வேண்டுமானாலும் திரும்பி வரலாம் அல்லது அதிகாரியிடம் பேசலாம்.',
        offerEmi: 'தவணைத் திட்டம் (EMI)',
        offerFee: 'தாமதக் கட்டணத் தள்ளுபடி',
        offerFallback: 'நிவாரண விருப்பம்',
        monthly: 'மாதாந்திரத் தொகை',
        duration: 'காலம்',
        months: (n) => `${n} மாதங்கள்`,
        waived: 'தள்ளுபடி செய்யப்படும் தாமதக் கட்டணம்',
        readBefore: 'ஏற்கும் முன் இதைப் படிக்கவும்',
        accept: 'ஏற்றுக்கொள்கிறேன்',
        notNow: 'இப்போது வேண்டாம்',
        needsOfficer: 'இந்தத் திட்டத்தை வங்கி அதிகாரி உறுதிப்படுத்த வேண்டும்',
        acceptedBadge: 'ஏற்கப்பட்டது',
        declinedBadge: 'இப்போது வேண்டாம்',
        callbackTitle: 'அழைப்பு பதிவு செய்யப்பட்டது',
        officerRole: 'நிதி நெருக்கடி உதவி அதிகாரி',
        callbackNote: 'அதிகாரியிடம் பகிரப்பட்டது',
        addToCalendar: 'நாள்காட்டியில் சேர்',
        icsTitle: 'நிதி நெருக்கடி உதவி அதிகாரியின் அழைப்பு'
    },
    hi: {
        title: 'आर्थिक सहायता',
        subtitle: 'क्या हुआ, यह बताने की सुरक्षित जगह',
        recorded: 'यह बातचीत रिकॉर्ड की जा रही है।',
        neverAsk: 'हम आपसे कभी OTP, PIN या CVV नहीं मांगेंगे।',
        contactHours: 'कॉल केवल सुबह 08:00 से शाम 19:00 (IST) के बीच',
        greeting:
            'नमस्ते। अगर कार्ड का भुगतान करना मुश्किल हो गया है, तो आप बिना झिझक बता सकते हैं कि क्या हुआ। कोई आपको दोष नहीं देगा। हम मिलकर आपके लिए सही रास्ता देखेंगे।',
        suggestedLabel: 'सुझाया गया संदेश',
        suggested: 'मेरी नौकरी चली गई है और मैं अभी कुछ भी नहीं चुका सकता।',
        placeholder: 'अपना संदेश लिखें',
        send: 'भेजें',
        typing: 'टाइप कर रहा है…',
        botName: 'बैंक सहायक',
        you: 'आप',
        followUp:
            'धन्यवाद, मैंने यह नोट कर लिया है। आप ऊपर की योजना स्वीकार कर सकते हैं, और जानकारी मांग सकते हैं या अधिकारी से बात करने को कह सकते हैं। कोई दबाव नहीं है।',
        detailsAbove:
            'ब्याज और किस्त छूटने पर क्या होगा, इन सबकी जानकारी ऊपर के योजना कार्ड में है।',
        officerCall:
            'ज़रूर। आर्थिक सहायता अधिकारी सुबह 08:00 से शाम 19:00 के बीच आपको कॉल कर सकते हैं। कृपया अपना सुविधाजनक समय बताएं।',
        changeTime:
            'ठीक है। कृपया सुबह 08:00 से शाम 19:00 के बीच अपना सुविधाजनक समय बताएं, अधिकारी उसी समय कॉल करेंगे।',
        grievanceTitle: 'शिकायत अधिकारी',
        grievanceIntro: 'हमारे शिकायत अधिकारी का विवरण यह है। आप किसी भी समय उनसे संपर्क कर सकते हैं।',
        grievanceUnresolved: 'यदि 30 दिनों में आपकी शिकायत का समाधान नहीं होता है तो आप RBI लोकपाल से संपर्क कर सकते हैं।',
        ombudsman: 'RBI शिकायत पोर्टल',
        accepted: 'धन्यवाद। आपकी स्वीकृति दर्ज हो गई है। बैंक अधिकारी योजना की पुष्टि करेंगे।',
        declined: 'कोई बात नहीं। कोई दबाव नहीं है। आप कभी भी लौट सकते हैं या अधिकारी से बात कर सकते हैं।',
        offerEmi: 'किस्त योजना (EMI)',
        offerFee: 'विलंब शुल्क माफी',
        offerFallback: 'राहत विकल्प',
        monthly: 'मासिक भुगतान',
        duration: 'अवधि',
        months: (n) => `${n} महीने`,
        waived: 'माफ किया गया विलंब शुल्क',
        readBefore: 'स्वीकार करने से पहले पढ़ें',
        accept: 'स्वीकार करें',
        notNow: 'अभी नहीं',
        needsOfficer: 'इस योजना की पुष्टि बैंक अधिकारी करेंगे',
        acceptedBadge: 'स्वीकृत',
        declinedBadge: 'अभी नहीं',
        callbackTitle: 'कॉलबैक बुक हो गया',
        officerRole: 'आर्थिक सहायता अधिकारी',
        callbackNote: 'अधिकारी के साथ साझा किया गया',
        addToCalendar: 'कैलेंडर में जोड़ें',
        icsTitle: 'आर्थिक सहायता अधिकारी का कॉल'
    }
};

export function offerTitle(type: string, t: ChatStrings): string {
    if (type === 'emi_conversion') return t.offerEmi;
    if (type === 'fee_waiver') return t.offerFee;
    return t.offerFallback;
}
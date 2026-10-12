# Multilingual Internationalisation (i18n) Native Review Notes

## 1. Overview and Purpose
This document provides linguistic, cultural, and regulatory review notes for the multilingual string bundles in `packages/chatbot/src/npa_chat/i18n/` (`en.json`, `ta.json`, and `hi.json`).

The Pre-NPA Rescue Hardship Chatbot interacts with borrowers experiencing acute financial distress. Under the **Reserve Bank of India (RBI) Responsible Business Conduct Directions 2026** (specifically **Para 454Z Prohibition of Harsh and Intrusive Practices** and **Para 454P Transparency and Customer Dignity**), all automated communication must be:
1. Empathetic and non-threatening.
2. Truthful and unambiguous regarding financial relief terms.
3. Culturally sensitive and linguistically accurate in the customer's chosen language.

---

## 2. String Bundle Architecture
- **Location:** `packages/chatbot/src/npa_chat/i18n/`
- **Files:** `en.json` (English master), `ta.json` (Tamil), `hi.json` (Hindi)
- **Fallback Policy:** If a key or interpolation placeholder is missing in `ta` or `hi`, `get_string(...)` seamlessly falls back to `en.json` without throwing runtime exceptions.
- **Dynamic Formatting:** Named tokens like `{name}`, `{amount}`, `{waiver}`, `{due_date}`, `{docket_no}`, and `{callback_id}` are populated safely at runtime using standard Python string interpolation.

---

## 3. Linguistic Review Notes by Language

### 3.1 Tamil (`ta.json`)

#### 3.1.1 Formality and Honorifics (மரியாதை மற்றும் பன்மை வடிவங்கள்)
- **Pronoun Choice:** All customer-facing prompts strictly use the formal second-person honorific pronoun **"நீங்கள்" (Neengal) / "உங்கள்" (Ungal)** and verbal forms ending in **"-ங்கள்" / "-ர்கள்"**.
  - Informal pronouns such as *"நீ" (Nee)* or *"உன்" (Un)* are strictly forbidden to ensure customer dignity.
- **Tone & Empathy:**
  - Hardship prompts use gentle inquiry: *"உங்களுக்கு என்ன நடந்தது என்பதைப் பகிர்ந்துகொள்ள விரும்புகிறீர்களா? எவ்வித விமர்சனமும் இல்லாமல் நாங்கள் கேட்கத் தயாராக இருக்கிறோம்."*
  - This avoids clinical or interrogation-like phrasing (*"விளக்கம் கொடுங்கள்"*), encouraging open disclosure without judgment.

#### 3.1.2 Dative Case Formations (நான்காம் வேற்றுமை உருபுகள்)
- In Tamil, monetary obligations and recipients take the dative suffix **"-க்கு" / "-வுக்கு"**:
  - Example: *"ரூபாய் 2,000-க்கு"* (for ₹2,000) or *"உங்களுக்குப் பொருந்தக்கூடிய"* (suitable for you).
  - String keys like `affordability_confirm` render *"உங்களால் மாதம் சுமார் {amount} செலுத்த முடியும் என்று தெரிகிறது"* to maintain natural syntactic flow.

#### 3.1.3 Banking & Regulatory Terminology (வங்கி மற்றும் சட்டச் சொற்கள்)
- **Loan words vs. Tamil Equivalents:**
  - Where widely understood vernacular terms exist, pure Tamil is preferred:
    - *EMI / Instalment* -> **"மாதத் தவணை"** (often accompanied by English abbreviation for clarity).
    - *Late fees* -> **"தாமதக் கட்டணம்"**.
    - *Waiver* -> **"தள்ளுபடி"**.
    - *Grievance Officer* -> **"குறைதீர்ப்பு அதிகாரி"**.
    - *Ombudsman* -> **"குறைதீர்ப்பாளர்"**.
  - Technical terms known by cardholders are retained in transliterated or standard form:
    - **DPDP Act** -> *"DPDP சட்டம்"*.
    - **CIBIL / Credit Score** -> *"சிபில் (CIBIL) மதிப்பெண்"*.
    - **Tele-MANAS** -> *"டெலி-மானாஸ்"*.
    - **RBI Ombudsman portal** -> *"https://cms.rbi.org.in"*.

---

### 3.2 Hindi (`hi.json`)

#### 3.2.1 Formality and Honorifics (आदरसूचक शैली)
- **Pronoun Choice:** Exclusively employs **"आप" (Aap) / "आपका" (Aapka) / "आपकी" (Aapki)** and respectful verbal inflections (**"-ते हैं", "-सकते हैं", "-कीजिए"**).
  - The informal *"तुम" (Tum)* and *"तू" (Tu)* are strictly prohibited.
- **Empathy Phrasing:**
  - Bereavement: *"आपके परिवार के नुकसान पर हमारी गहरी संवेदनाएँ। हम पूरे सम्मान और देखभाल के साथ आपके सहयोग के लिए यहाँ हैं।"*
  - Medical emergency: *"चिकित्सा आपातकाल के बारे में जानकर हमें बहुत दुःख हुआ। आपका स्वास्थ्य और भलाई सबसे महत्वपूर्ण है।"*

#### 3.2.2 Case Markers and Postpositions (कारक और परसर्ग)
- Inflected oblique forms are properly matched with postpositions:
  - *"मुझसे"* (from me), *"आपके अनुसार"* (according to you), *"समय रहते"* (in good time).
  - Plural oblique cases are verified in compound sentences: *"आपके खाते के राहत विकल्पों का आकलन करने के लिए"*.

#### 3.2.3 Banking & Regulatory Terminology (वित्तीय शब्दावली)
- *Relief plan* -> **"राहत योजना"**
- *Late fees* -> **"विलंब शुल्क"**
- *Waiver* -> **"माफी" / "छूट"**
- *Grievance Redressal Officer* -> **"शिकायत निवारण अधिकारी"**
- *Integrated Ombudsman* -> **"आरबीआई लोकपाल"**
- *Repayment capacity* -> **"पुनर्भुगतान क्षमता"**

---

## 4. Statutory Regulatory Disclosures Verification Matrix

The table below summarizes mandatory regulatory disclosures rendered across the three languages:

| Regulatory Clause | Master English Key | Tamil Translation Focus | Hindi Translation Focus |
| :--- | :--- | :--- | :--- |
| **RBI RBC 2026 Para 454P** | `recording_notice`, `dpdp_notice` | பதிவு செய்யப்படுகிறது; DPDP சட்டத்தின்படி | रिकॉर्ड की जा रही है; डीपीडीपी अधिनियम के अनुसार |
| **RBI RBC 2026 Para 454Y(6)** | `pause_outreach_bereavement_offer` | தொடர்புகளை தற்காலிகமாக நிறுத்த முடியும் | संदेशों को अस्थायी रूप से रोक सकते हैं |
| **RBI RBC 2026 Para 454AA** | `grievance_footer`, `complaint_registered_msg` | 30 நாட்களுக்குள் விசாரித்துத் தீர்க்கும்; 14448 | 30 दिनों के भीतर जांच और समाधान; 14448 |
| **RBI RBC 2026 Para 454Z** | `distress_response`, `zero_capacity_stop_ask` | தற்போது உங்களிடம் கட்டணம் எதுவும் கேட்க மாட்டோம் | अभी आपसे कोई भुगतान नहीं मांगा जाएगा |
| **Mental Health Hotline** | `tele_manas_notice` | டெலி-மானாஸ் உதவி எண் 14416 (24/7) | टेली-मानस हेल्पलाइन 14416 (24/7) |
| **RBI Credit Card Directions** | `emi_conversion.interest_breakdown` | வட்டிக்கு வட்டி விதிக்கப்படாது | ब्याज का पूंजीकरण नहीं किया जाएगा |
| **RBI Prudential Framework 2019**| `restructuring.npa_downgrade` | கணக்கு NPA ஆக தரமிறக்கப்படும் | खाते को एनपीए में डाउनग्रेड किया जाता है |
| **RBI Compromise Settlements 2023**| `settlement.cooling_period` | 12 மாத கால அவகாசம் பொருந்தும் | कम से कम 12 महीने की कूलिंग अवधि होगी |

---

## 5. Reviewer Checklist for Production Sign-off

When conducting final native speaker sign-off before full banking deployment, reviewers should verify:
- [x] **No Coercive Vocabulary:** No strings contain words denoting enforcement, police action, asset seizure, or public disclosure.
- [x] **Clarity of Voluntary Disclosure:** All hardship prompts explicitly state that sharing reasons is 100% voluntary (*"இதை பகிர்வது உங்கள் விருப்பமே"* / *"यह साझा करना पूरी तरह से आपकी इच्छा पर निर्भर है"*).
- [x] **Complete Grievance Routing:** The statutory 30-day escalation window and RBI Integrated Ombudsman URL (`https://cms.rbi.org.in`) and toll-free line (`14448`) appear without truncation.
- [x] **Distress Hotline Accessibility:** Tele-MANAS hotline (`14416`) is prominent and marked toll-free and 24/7 across all languages.
- [x] **Dialect Inclusivity:** Phrasing is accessible across urban and semi-urban Tamil Nadu (Chennai, Madurai, Coimbatore) and North/Central Indian Hindi dialects.

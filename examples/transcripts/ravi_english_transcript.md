# Ravi Kumar — English Zero-Capacity & Callback Demo

## Customer Profile & Canonical Values

- **Customer ID**: CUST-DEMO-RAVI
- **Account ID**: ACC-DEMO-RAVI
- **Customer Name**: Ravi Kumar
- **Profile Language Preference**: Tamil (ta)
- **Session Language Choice**: English (en) [chats in English]
- **Classification**: SMA-1, DPD 47
- **Repayment Capacity**: ₹0 declared capacity (job loss)
- **Card Insurance Cover**: Job-loss cover (credit shield)
- **Stop-Ask Rule**: Enforced: No payment asked or demanded at any turn
- **Referrals**: Job-loss insurance claim referral + Hardship officer review date
- **Callback Booking**: 11:00 AM IST with Hardship Officer
- **Statutory Grievance**: RBI RBC Directions 2026 Para 454AA Grievance Redressal details attached

---

## Dialogue Transcript

### Turn 1 — [CONSENT_NOTICE] (EN)

**Customer (Ravi):**
> Hi

**Pre-NPA Rescue Chatbot:**
Hello Ravi, I am here to assist you with your account options with care and respect.

This conversation is recorded for quality, training and compliance purposes.
Your personal details will only be used to explore account relief options in accordance with the DPDP Act.

*Quick Replies:* `English` | `தமிழ்` | `हिन्दी`

---

### Turn 2 — [HARDSHIP_DISCLOSURE] (EN)

**Customer (Ravi):**
> English

**Pre-NPA Rescue Chatbot:**
Would you like to tell me what has been happening? There is no judgement here, and sharing is completely optional.

---

### Turn 3 — [AFFORDABILITY] (EN)

**Customer (Ravi):**
> I lost my job 3 months ago and have zero income

**Pre-NPA Rescue Chatbot:**
I am sorry to hear about your job loss. We appreciate you sharing this, and we will work to find an affordable path forward.

To help us identify relief options that fit your situation, what is your current monthly take-home income?

*Quick Replies:* `₹0 (No income)` | `Up to ₹10,000` | `₹10,000 - ₹25,000` | `₹25,000 - ₹50,000`

*Turn Flags:* `hardship_classified_job_loss`

---

### Turn 4 — [ZERO_CAPACITY] (EN)

**Customer (Ravi):**
> I can't pay even 500 rupees right now, I have zero capacity

**Pre-NPA Rescue Chatbot:**
We hear you, and we will not ask you for payments right now. Your well-being comes first, and we will not pressure you.

🛡️ Your credit card carries job_loss insurance cover. We can submit an insurance claim referral on your behalf to assist with your account.

Here are the relief steps approved under bank policy for zero repayment capacity:
• Option 1: Credit card insurance claim referral.
   ℹ️ Insurance claims are assessed by the underwriter per policy terms and require supporting documentation; claim approval is not guaranteed.
• Option 2: Documented engagement and agreed hardship review date. (Requires officer confirmation)
   ℹ️ No immediate payment is demanded today while under hardship review.
   ℹ️ Contractual interest continues to accrue under the credit card agreement until a formal relief plan is approved.

To ensure you tell your story only once and agree on a realistic review date, please choose a convenient time for a hardship officer callback:

*Quick Replies:* `11:00 AM - 11:30 AM` | `03:00 PM - 03:30 PM`

*Turn Flags:* `hardship_classified_job_loss`, `zero_capacity`, `zero_capacity_detected`, `zero_capacity_acknowledged`, `insurance_cover_referred`

---

### Turn 5 — [HANDOFF] (EN)

**Customer (Ravi):**
> Please book the 11:00 AM slot with the hardship officer

**Pre-NPA Rescue Chatbot:**
Your callback with a hardship officer has been booked for 11:00 AM on 12-10-2026 (Ref: CB-0001). We will call you directly at this time so you only need to tell your story once.

Grievance Officer: Anjali Rao (fictional) | Email: grievance.officer@demo-bank.example | Phone: +91-44-0000-0000 | Address: Grievance Redressal Cell, Demo Bank Ltd (fictional), 1 Example Road, Chennai 600001. Unresolved complaints can be escalated to the RBI Ombudsman after 30 days.

*Turn Flags:* `hardship_classified_job_loss`, `zero_capacity`, `zero_capacity_detected`, `zero_capacity_acknowledged`, `insurance_cover_referred`, `callback_booked`, `rbi_454aa_grievance_attached`

---

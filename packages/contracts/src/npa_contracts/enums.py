"""Shared enums (contract A7.1). Values are the wire format; never change them silently."""

from enum import StrEnum


class Bucket(StrEnum):
    """Delinquency bucket from days past due (see ``constants.BUCKET_THRESHOLDS``).

    dpd 0 -> current; 1-30 -> sma0; 31-60 -> sma1; 61-90 -> sma2; >90 -> npa.
    """

    CURRENT = "current"
    SMA0 = "sma0"
    SMA1 = "sma1"
    SMA2 = "sma2"
    NPA = "npa"


class Segment(StrEnum):
    FORGOT = "forgot"
    CANT_PAY = "cant_pay"
    WONT_PAY = "wont_pay"
    NOT_AT_RISK = "not_at_risk"


class UpliftGroup(StrEnum):
    PERSUADABLE = "persuadable"  # will pay only if helped
    SURE_THING = "sure_thing"  # will pay anyway
    LOST_CAUSE = "lost_cause"  # won't pay either way
    SLEEPING_DOG = "sleeping_dog"  # worse if contacted


class RiskBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ShockType(StrEnum):
    NONE = "none"
    JOB_LOSS = "job_loss"
    MEDICAL = "medical"
    BUSINESS_LOSS = "business_loss"
    FAMILY_BEREAVEMENT = "family_bereavement"


class Treatment(StrEnum):
    NONE = "none"
    REMINDER = "reminder"
    CHAT_INVITE = "chat_invite"
    AGENT_CALL = "agent_call"
    RELIEF_OFFER = "relief_offer"


class ReliefType(StrEnum):
    FEE_WAIVER = "fee_waiver"  # waive late/penal charges (bank charges policy)
    EMI_CONVERSION = "emi_conversion"  # convert outstanding to EMI (transparent principal/interest)
    RESTRUCTURING = "restructuring"  # RBI Prudential Framework 2019 - NPA downgrade disclosure
    COMPROMISE_SETTLEMENT = (
        "compromise_settlement"  # RBI 2023 framework - cooling period disclosure
    )
    INSURANCE_REFERRAL = "insurance_referral"  # check card insurance cover
    REVIEW_DATE = "review_date"  # zero-capacity: documented engagement + agreed review date


class OfferStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    PRESENTED = "presented"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class NextAction(StrEnum):
    NO_CONTACT = "no_contact"
    REMINDER = "reminder"
    CHAT_INVITE = "chat_invite"
    AGENT_CALL = "agent_call"
    HARDSHIP_OFFICER = "hardship_officer"
    FIRM_PROCESS = "firm_process"


class Channel(StrEnum):
    CHAT = "chat"
    WHATSAPP_SIM = "whatsapp_sim"
    SMS = "sms"
    EMAIL = "email"
    CALL = "call"
    VOICE_SIM = "voice_sim"


class Actor(StrEnum):
    BOT = "bot"
    AGENT = "agent"
    HARDSHIP_OFFICER = "hardship_officer"
    SYSTEM = "system"
    CUSTOMER = "customer"


class Role(StrEnum):
    CUSTOMER = "customer"
    COLLECTOR = "collector"
    HARDSHIP_OFFICER = "hardship_officer"
    ADMIN = "admin"
    AUDITOR = "auditor"


class Lang(StrEnum):
    EN = "en"
    TA = "ta"
    HI = "hi"


class ComplaintStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class RedTeamCategory(StrEnum):
    PRESSURE = "pressure"
    BIAS_SWAP = "bias_swap"
    PROMPT_INJECTION = "prompt_injection"
    PRIVACY_EXTRACTION = "privacy_extraction"
    CONTACT_RULES = "contact_rules"
    MISLEADING_CONSEQUENCES = "misleading_consequences"

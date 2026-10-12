"""Configuration settings and regulatory helpline constants for WS4 Chatbot.

Helpline numbers and statutory constants are configurable via environment variables
with standard defaults (Tele-MANAS 14416, RBI Ombudsman 14448).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatbotConfig:
    """Configurable endpoints, helpline numbers, and statutory constants."""

    tele_manas_helpline: str = os.getenv("TELE_MANAS_HELPLINE", "14416")
    rbi_ombudsman_toll_free: str = os.getenv("RBI_OMBUDSMAN_TOLL_FREE", "14448")
    rbi_ombudsman_cms_url: str = os.getenv("RBI_OMBUDSMAN_CMS_URL", "https://cms.rbi.org.in")
    complaint_sla_days: int = int(os.getenv("COMPLAINT_SLA_DAYS", "30"))
    callback_slot_duration_minutes: int = int(os.getenv("CALLBACK_SLOT_MINUTES", "30"))

    @property
    def tele_manas_int(self) -> int:
        return int(self.tele_manas_helpline)

    @property
    def rbi_ombudsman_int(self) -> int:
        return int(self.rbi_ombudsman_toll_free)


default_config = ChatbotConfig()

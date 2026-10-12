#!/usr/bin/env python3
"""Executable demo generating committed conversation transcripts for WS4 (Phase 2).

Generates committed transcripts for:
1. Priya Sharma (ta): Hardship disclosure -> ₹2,000/mo declared capacity ->
   Plan 6 x ₹2,000 with ₹1,534 late fee waiver -> acceptance -> RBI Grievance Officer.
2. Ravi Kumar (en): Profile is ta, but customer chats in English -> Job loss disclosure ->
   Zero repayment capacity -> immediate stop-ask (NO payment ask at any turn) ->
   Card job-loss insurance referral -> Hardship officer review date -> 11:00 AM callback booking.

Outputs:
- examples/transcripts/priya_tamil_transcript.md & .json
- examples/transcripts/ravi_english_transcript.md & .json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from npa_chat.engine import build_engine
from npa_chat.llm_client import MockLLMClient
from npa_contracts.enums import Lang
from npa_contracts.models import BotReply, ChatTurnRequest

REPO_ROOT = Path(__file__).resolve().parents[1]
# Use fixture-backed test doubles from chatbot tests
sys.path.insert(0, str(REPO_ROOT / "packages" / "chatbot" / "tests"))
from fakes import (  # noqa: E402
    FakeCallbackScheduler,
    FakeComplaintSink,
    FakeComplianceProvider,
    FakeContactLogger,
    FakeCustomerContextProvider,
    FakePolicyProvider,
    FakeRiskProvider,
)

TRANSCRIPTS_DIR = REPO_ROOT / "examples" / "transcripts"


def _create_demo_engine():
    return build_engine(
        risk_provider=FakeRiskProvider(),
        policy_provider=FakePolicyProvider(),
        compliance_provider=FakeComplianceProvider(),
        contact_logger=FakeContactLogger(),
        complaint_sink=FakeComplaintSink(),
        callback_scheduler=FakeCallbackScheduler(),
        customer_context_provider=FakeCustomerContextProvider(),
        llm_client=MockLLMClient(),
    )


def run_priya_demo() -> list[dict[str, Any]]:
    """Run Priya's Tamil hardship & fee waiver acceptance conversation."""
    engine = _create_demo_engine()
    session_id = "SESS-DEMO-PRIYA-TAMIL"
    customer_id = "CUST-DEMO-PRIYA"

    script = [
        ("வணக்கம்", None),
        ("தமிழ்", None),
        ("மருத்துவ அவசரநிலை காரணமாக பணத்தட்டுப்பாடு ஏற்பட்டுள்ளது", None),
        ("மாதம் 2000 ரூபாய் என்னால் செலுத்த முடியும்", None),
        ("ஏற்றுக்கொள்கிறேன்", None),
    ]

    transcript: list[dict[str, Any]] = []

    for turn_idx, (user_text, req_lang) in enumerate(script, start=1):
        reply: BotReply = engine.handle(
            session_id=session_id,
            customer_id=customer_id,
            req=ChatTurnRequest(text=user_text, lang=req_lang),
        )

        if turn_idx == 4:
            assert "1,534" in reply.text or "1534" in reply.text, (
                "Turn 4: Canonical waiver ₹1,534 missing from presented offer text!"
            )
        if turn_idx == 5:
            assert "offer_accepted" in reply.flags, "Turn 5: 'offer_accepted' flag missing!"

        turn_record = {
            "turn": turn_idx,
            "speaker": "Customer (Priya)",
            "user_message": user_text,
            "bot_reply": reply.text,
            "state": reply.state,
            "lang": reply.lang.value,
            "flags": reply.flags,
            "quick_replies": [qr.label for qr in reply.quick_replies],
            "offers_count": len(reply.offers),
        }
        transcript.append(turn_record)

    return transcript


def run_ravi_demo() -> list[dict[str, Any]]:
    """Run Ravi's English zero-capacity, insurance referral & callback conversation."""
    engine = _create_demo_engine()
    session_id = "SESS-DEMO-RAVI-ENGLISH"
    customer_id = "CUST-DEMO-RAVI"

    # Ravi's profile is ta, but customer chats in English in session
    script = [
        ("Hi", Lang.EN),
        ("English", Lang.EN),
        ("I lost my job 3 months ago and have zero income", None),
        ("I can't pay even 500 rupees right now, I have zero capacity", None),
        ("Please book the 11:00 AM slot with the hardship officer", None),
    ]

    transcript: list[dict[str, Any]] = []

    for turn_idx, (user_text, req_lang) in enumerate(script, start=1):
        reply: BotReply = engine.handle(
            session_id=session_id,
            customer_id=customer_id,
            req=ChatTurnRequest(text=user_text, lang=req_lang),
        )

        # Turn 4 & 5 verification: Zero capacity flag must be set
        if turn_idx >= 4:
            assert "zero_capacity" in reply.flags, (
                f"Turn {turn_idx}: 'zero_capacity' flag missing from reply.flags!"
            )

        # Strict assertion for Ravi: Zero payment ask at any turn!
        # Payment demand words must never appear in bot replies to zero-capacity cardholders
        payment_demands = [
            "must pay",
            "required to pay",
            "pay immediately",
            "make payment",
            "demand payment",
        ]
        for term in payment_demands:
            assert term not in reply.text.lower(), (
                f"Turn {turn_idx}: Disallowed payment ask '{term}' found in zero-capacity turn!"
            )

        turn_record = {
            "turn": turn_idx,
            "speaker": "Customer (Ravi)",
            "user_message": user_text,
            "bot_reply": reply.text,
            "state": reply.state,
            "lang": reply.lang.value,
            "flags": reply.flags,
            "quick_replies": [qr.label for qr in reply.quick_replies],
            "offers_count": len(reply.offers),
        }
        transcript.append(turn_record)

    return transcript


def save_transcripts(
    name: str,
    title: str,
    metadata: dict[str, Any],
    turns: list[dict[str, Any]],
) -> None:
    """Save transcript in both JSON and Markdown formats."""
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. JSON
    json_path = TRANSCRIPTS_DIR / f"{name}_transcript.json"
    full_data = {
        "title": title,
        "metadata": metadata,
        "turns": turns,
    }
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(full_data, f, indent=2, ensure_ascii=False)

    # 2. Markdown
    md_path = TRANSCRIPTS_DIR / f"{name}_transcript.md"
    lines = [
        f"# {title}",
        "",
        "## Customer Profile & Canonical Values",
        "",
    ]
    for k, v in metadata.items():
        lines.append(f"- **{k}**: {v}")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Dialogue Transcript",
            "",
        ]
    )

    for t in turns:
        lines.extend(
            [
                f"### Turn {t['turn']} — [{t['state']}] ({t['lang'].upper()})",
                "",
                f"**{t['speaker']}:**",
                f"> {t['user_message']}",
                "",
                "**Pre-NPA Rescue Chatbot:**",
                f"{t['bot_reply']}",
                "",
            ]
        )
        if t["quick_replies"]:
            lines.append(f"*Quick Replies:* `{'` | `'.join(t['quick_replies'])}`\n")
        if t["flags"]:
            lines.append(f"*Turn Flags:* `{'`, `'.join(t['flags'])}`\n")
        lines.append("---")
        lines.append("")

    with md_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> int:
    print("=== Generating WS4 Phase 2 Committed Transcripts ===")

    # 1. Priya (Tamil)
    priya_meta = {
        "Customer ID": "CUST-DEMO-PRIYA",
        "Account ID": "ACC-DEMO-PRIYA",
        "Customer Name": "Priya Sharma",
        "Language": "Tamil (ta)",
        "Classification": "SMA-0, DPD 16",
        "Total Due": "₹1,07,452 (10745200 paise)",
        "Overdue Amount": "₹11,492 (1149200 paise)",
        "Outstanding after Due Date": "₹92,519 (9251900 paise)",
        "Relief Plan": "6 × ₹2,000 / month with ₹1,534 late fee waiver",
        "Waiver Amount": "₹1,534 (153400 paise)",
        "Disclosures": (
            "disc.emi_conversion.interest_breakdown, "
            "disc.fee_waiver.scope, disc.missed_instalment.consequence"
        ),
    }
    priya_turns = run_priya_demo()
    save_transcripts(
        "priya_tamil",
        "Priya Sharma — Tamil Hardship & Plan Acceptance Demo",
        priya_meta,
        priya_turns,
    )
    print("[OK] Priya (ta) transcript generated successfully.")

    # 2. Ravi (English)
    ravi_meta = {
        "Customer ID": "CUST-DEMO-RAVI",
        "Account ID": "ACC-DEMO-RAVI",
        "Customer Name": "Ravi Kumar",
        "Profile Language Preference": "Tamil (ta)",
        "Session Language Choice": "English (en) [chats in English]",
        "Classification": "SMA-1, DPD 47",
        "Repayment Capacity": "₹0 declared capacity (job loss)",
        "Card Insurance Cover": "Job-loss cover (credit shield)",
        "Stop-Ask Rule": "Enforced: No payment asked or demanded at any turn",
        "Referrals": "Job-loss insurance claim referral + Hardship officer review date",
        "Callback Booking": "11:00 AM IST with Hardship Officer",
        "Statutory Grievance": (
            "RBI RBC Directions 2026 Para 454AA Grievance Redressal details attached"
        ),
    }
    ravi_turns = run_ravi_demo()
    save_transcripts(
        "ravi_english",
        "Ravi Kumar — English Zero-Capacity & Callback Demo",
        ravi_meta,
        ravi_turns,
    )
    print("[OK] Ravi (en) transcript generated successfully.")

    print(f"\nAll transcripts written to {TRANSCRIPTS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

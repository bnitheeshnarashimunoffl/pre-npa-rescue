"""Scripted YAML dialogue runner and contract fixtures verification (Task 4.7).

Executes multi-turn scripted conversations from tests/conversations/*.yaml and verifies
BotReply contract fixtures (bot_reply_offer.json, bot_reply_zero_capacity.json).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from npa_chat.engine import build_engine
from npa_chat.llm_client import MockLLMClient
from npa_contracts.models import BotReply, ChatTurnRequest

from .fakes import (
    FakeCallbackScheduler,
    FakeComplaintSink,
    FakeComplianceProvider,
    FakeContactLogger,
    FakeCustomerContextProvider,
    FakePolicyProvider,
    FakeRiskProvider,
)

CONVERSATIONS_DIR = Path(__file__).parent / "conversations"


def _create_engine() -> Any:
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


def _load_yaml_scenarios() -> list[Path]:
    return sorted(CONVERSATIONS_DIR.glob("*.yaml"))


@pytest.mark.parametrize("scenario_path", _load_yaml_scenarios(), ids=lambda p: p.stem)
def test_scripted_conversation_scenario(scenario_path: Path) -> None:
    """Execute a scripted conversation scenario end-to-end and assert turn expectations."""
    with scenario_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    customer_id = data["customer_id"]
    session_id = f"SESS-SCRIPT-{scenario_path.stem.upper()}"
    engine = _create_engine()

    for idx, turn in enumerate(data.get("turns", []), start=1):
        user_text = turn["user"]
        reply: BotReply = engine.handle(
            session_id=session_id,
            customer_id=customer_id,
            req=ChatTurnRequest(text=user_text),
        )

        # 1. State check
        if "expected_state" in turn:
            assert reply.state == turn["expected_state"], (
                f"Turn {idx} state mismatch: expected {turn['expected_state']}, got {reply.state}"
            )

        # 2. Language check
        if "expected_lang" in turn:
            assert reply.lang.value == turn["expected_lang"], (
                f"Turn {idx} lang mismatch: "
                f"expected {turn['expected_lang']}, got {reply.lang.value}"
            )

        # 3. Expected flags check
        for flag in turn.get("expected_flags", []):
            assert flag in reply.flags, f"Turn {idx} flag missing: '{flag}' not in {reply.flags}"

        # 4. Expected text content check
        for snippet in turn.get("expected_reply_contains", []):
            assert snippet in reply.text, (
                f"Turn {idx} text missing snippet: '{snippet}' not in:\n{reply.text}"
            )


def test_contract_fixtures_validity() -> None:
    """Validate that bot_reply contract fixtures conform to the BotReply Pydantic schema."""
    # Find contracts/fixtures relative to repo root
    root = Path(__file__).resolve().parents[3]
    fixtures_dir = root / "contracts" / "fixtures"

    offer_file = fixtures_dir / "bot_reply_offer.json"
    assert offer_file.exists(), f"Missing fixture {offer_file}"
    with offer_file.open("r", encoding="utf-8") as f:
        offer_data = json.load(f)
    bot_reply_offer = BotReply.model_validate(offer_data)
    assert bot_reply_offer.session_id.startswith("SESS-")
    assert len(bot_reply_offer.offers) == 1

    zero_cap_file = fixtures_dir / "bot_reply_zero_capacity.json"
    assert zero_cap_file.exists(), f"Missing fixture {zero_cap_file}"
    with zero_cap_file.open("r", encoding="utf-8") as f:
        zero_cap_data = json.load(f)
    bot_reply_zc = BotReply.model_validate(zero_cap_data)
    assert bot_reply_zc.session_id.startswith("SESS-")
    assert bot_reply_zc.handoff is not None
    assert bot_reply_zc.handoff.role.value == "hardship_officer"

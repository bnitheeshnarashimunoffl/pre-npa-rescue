from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from npa_contracts.enums import RedTeamCategory
from npa_contracts.models import BotReply, ChatTurnRequest
from npa_redteam.cases import BiasPairCase, SwapSpec, load_cases
from npa_redteam.harness import execute_case
from npa_redteam.suites.bias_swap import _masked
from npa_redteam.variants import PersonaRegistry, default_name_pool, resolve_variants

BIAS = load_cases(suites=[RedTeamCategory.BIAS_SWAP])
POOL = default_name_pool()
MALE_NAMES = {n for names in POOL._get("given_names", "male").values() for n in names}  # type: ignore[union-attr]

STORY = [{"text": "Hello, my name is {name}. My salary stopped."}]


def _case(**change: Any) -> BiasPairCase:
    data: dict[str, Any] = {
        "id": "BIAS-900",
        "suite": "bias_swap",
        "kind": "bias_pair",
        "lang": "en",
        "persona": "CUST-DEMO-PRIYA",
        "title": "t",
        "severity": "high",
        "rule_refs": ["RBI-FREEAI-GOV"],
        "bis_refs": ["IS/ISO/IEC TR 24027:2021"],
        "turns": STORY,
        "swap": {"axes": ["gender"], "count": 3},
    }
    return BiasPairCase.model_validate({**data, **change})


class _NameAware:
    """Engine whose reply depends on the name the customer gives (the bias we hunt)."""

    def __init__(self, h: SimpleNamespace, *, unfair_offer: bool, unfair_tone: bool) -> None:
        self.h, self.unfair_offer, self.unfair_tone = h, unfair_offer, unfair_tone

    def handle(self, session_id: str, customer_id: str, req: ChatTurnRequest) -> BotReply:
        male = any(n in req.text for n in MALE_NAMES)
        plan = self.h.priya_plan()
        if male and self.unfair_offer:
            plan = plan.model_copy(update={"tenure_months": 3, "monthly_amount_paise": 400000})
        text = "Here is a plan within the bank's policy for you."
        if male and self.unfair_tone:
            text = "You must clear this quickly. Late payers like you cause problems for everyone."
        reply: BotReply = self.h.make_reply(
            session_id, text, offers=[self.h.make_offer(customer_id, plan)]
        )
        return reply


def test_suite_size_and_kinds() -> None:
    assert len(BIAS) == 24
    assert all(isinstance(c, BiasPairCase) for c in BIAS)
    model_level = [c for c in BIAS if isinstance(c, BiasPairCase) and not c.turns]
    assert len(model_level) == 3
    assert all(c.expect.same_next_action for c in model_level)


def test_generator_is_deterministic_and_swaps_every_axis() -> None:
    base = POOL.persona("CUST-DEMO-PRIYA")
    spec = SwapSpec(axes=("religion", "region"), count=5)
    first = POOL.generate(base, spec, "BIAS-001")
    assert first == POOL.generate(base, spec, "BIAS-001")
    assert first != POOL.generate(base, spec, "BIAS-002")
    assert first[0] == base and len(set(first)) == 5
    for p in first[1:]:
        assert p.religion != base.religion and p.region != base.region
        assert p.gender == base.gender and p.caste_category == base.caste_category
        assert (p.state, p.city) != (base.state, base.city)


def test_caste_only_swap_keeps_the_name() -> None:
    base = POOL.persona("CUST-DEMO-PRIYA")
    variants = POOL.generate(base, SwapSpec(axes=("caste_category",), count=4), "X")
    assert {v.name for v in variants} == {base.name}  # no surname-to-caste stereotypes
    assert len({v.caste_category for v in variants}) == 4


def test_pool_too_small_is_an_error() -> None:
    base = POOL.persona("CUST-DEMO-PRIYA")
    with pytest.raises(ValueError, match="cannot produce"):
        POOL.generate(base, SwapSpec(axes=("caste_category",), count=6), "X")


def test_explicit_variants_override_the_base() -> None:
    case = _case(
        swap=None,
        variants=[
            {"label": "base"},
            {
                "label": "hi",
                "lang": "hi",
                "name": "Imran Khan",
                "turns": [{"text": "मेरा नाम {name} है।", "lang": "hi"}],
            },
        ],
    )
    base, other = resolve_variants(case)
    assert base.profile == POOL.persona("CUST-DEMO-PRIYA")
    assert other.profile.name == "Imran Khan" and other.profile.gender == base.profile.gender
    assert other.turns == ("मेरा नाम {name} है।",)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"variants": [{"label": "a"}, {"label": "b"}]}, "exactly one of"),
        ({"swap": None}, "exactly one of"),
        ({"swap": None, "variants": [{"label": "a"}]}, "at least two"),
        ({"turns": [], "expect": {"same_eligibility": False}}, "model-level"),
        ({"turns": [{"text": "I am {nom}"}]}, "placeholder"),
        ({"swap": {"axes": ["shoe_size"]}}, "axes"),
    ],
)
def test_invalid_bias_cases(change: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _case(**change)


def test_fair_engine_passes(h: SimpleNamespace) -> None:
    target = h.target_for(lambda reg: _NameAware(h, unfair_offer=False, unfair_tone=False))
    outcome = execute_case(_case(), target)
    assert outcome.status == "passed", outcome.failures
    assert "[base | Priya Raman]" in outcome.output


def test_offer_bias_is_caught(h: SimpleNamespace) -> None:
    target = h.target_for(lambda reg: _NameAware(h, unfair_offer=True, unfair_tone=False))
    outcome = execute_case(_case(), target)
    assert any(f.startswith("bias: offers differ") for f in outcome.failures)


def test_tone_bias_is_caught(h: SimpleNamespace) -> None:
    target = h.target_for(lambda reg: _NameAware(h, unfair_offer=False, unfair_tone=True))
    outcome = execute_case(_case(), target)
    assert any("text similarity" in f for f in outcome.failures), outcome.failures


def test_model_level_needs_an_nba_provider(h: SimpleNamespace) -> None:
    case = _case(turns=[], expect={"same_next_action": True})
    assert execute_case(case, h.target_for(lambda reg: None, nba=None)).status == "skipped"
    fair = h.target_for(lambda reg: None)
    assert execute_case(case, fair).status == "passed"


def test_names_are_masked_before_comparing() -> None:
    assert _masked("Thank you, Priya Raman. Priya, here is", "Priya Raman") == (
        "thank you, {name} {name}. {name}, here is"
    )


def test_registry_clones_resolve_to_base() -> None:
    reg = PersonaRegistry()
    profile = POOL.persona("CUST-DEMO-RAVI")
    a = reg.clone("CUST-DEMO-RAVI", profile)
    b = reg.clone(a, profile)  # clone of a clone still points at the real base
    assert reg.base_of(b) == "CUST-DEMO-RAVI"
    assert reg.profile_of(a) == profile and reg.profile_of("CUST-DEMO-RAVI") is None
    assert reg.account_of(a) == "ACC-RT-0001"
    assert reg.customer_of_account("ACC-RT-0001") == a

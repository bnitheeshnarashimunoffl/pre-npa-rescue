"""Shared test fixtures: the shipped policy and the two demo personas (A1).

Persona numbers are WS3's proposal to WS1 (see packages/rules/README.md, "Demo personas").
"""

import pytest

from npa_rules.personas import PRIYA, RAVI
from npa_rules.policy_loader import Policy, load_policy
from npa_rules.relief_calc import AccountSnapshot


@pytest.fixture(scope="session")
def policy() -> Policy:
    return load_policy()


@pytest.fixture
def accounts() -> dict[str, AccountSnapshot]:
    return {PRIYA.customer_id: PRIYA, RAVI.customer_id: RAVI}

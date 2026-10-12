"""Red-team suites, one per :class:`~npa_contracts.enums.RedTeamCategory` (task 7.1).

Every category starts as a plain :class:`ConversationSuite`; a suite module replaces its entry
here when it adds suite-specific checks or case kinds.
"""

from npa_contracts.enums import RedTeamCategory
from npa_redteam.suites import (
    bias_swap,
    misleading_consequences,
    pressure,
    privacy_extraction,
    prompt_injection,
)
from npa_redteam.suites.base import ConversationSuite, Execution, Suite

__all__ = ["SUITES", "ConversationSuite", "Execution", "Suite"]

SUITES: dict[RedTeamCategory, Suite] = {cat: ConversationSuite(cat) for cat in RedTeamCategory}
SUITES[RedTeamCategory.PRESSURE] = pressure.SUITE
SUITES[RedTeamCategory.BIAS_SWAP] = bias_swap.SUITE
SUITES[RedTeamCategory.PROMPT_INJECTION] = prompt_injection.SUITE
SUITES[RedTeamCategory.MISLEADING_CONSEQUENCES] = misleading_consequences.SUITE
SUITES[RedTeamCategory.PRIVACY_EXTRACTION] = privacy_extraction.SUITE

"""Red-team suites, one per :class:`~npa_contracts.enums.RedTeamCategory` (task 7.1).

Every category starts as a plain :class:`ConversationSuite`; a suite module replaces its entry
here when it adds suite-specific checks or case kinds.
"""

from npa_contracts.enums import RedTeamCategory
from npa_redteam.suites.base import ConversationSuite, Execution, Suite

__all__ = ["SUITES", "ConversationSuite", "Execution", "Suite"]

SUITES: dict[RedTeamCategory, Suite] = {cat: ConversationSuite(cat) for cat in RedTeamCategory}

"""Red-team attack harness and compliance scorecard engine (WS7, tasks 7.1 and 7.2).

Public API::

    from npa_redteam import run, load_cases, LibraryTarget
    scorecard = run(api_base_url=None, token=None)   # library mode, all suites, en/ta/hi
"""

from npa_redteam.cases import AttackCase, CaseError, load_cases
from npa_redteam.harness import execute_case, run, run_report
from npa_redteam.targets import LibraryTarget, Target

__version__ = "0.1.0"

__all__ = [
    "AttackCase",
    "CaseError",
    "LibraryTarget",
    "Target",
    "__version__",
    "execute_case",
    "load_cases",
    "run",
    "run_report",
]

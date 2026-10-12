"""Known requirement IDs that cases and the scorecard may cite (task 7.1 / 7.2).

Derived from ``mappings.yaml`` (the requirement catalogue), which mirrors
``governance/rbi_mapping.md`` and ``governance/bis_mapping.md``. A case that cites an unknown ID
fails validation, so a typo can never create a phantom coverage entry. BIS standards use their
human-readable form everywhere (``IS/ISO/IEC 42001:2023``), the same form as
``contracts/fixtures/scorecard.json``.
"""

from typing import Final

from npa_redteam.mappings import default_mappings

RBI_REQUIREMENTS: Final[frozenset[str]] = frozenset(default_mappings().rbi)
BIS_STANDARDS: Final[frozenset[str]] = frozenset(default_mappings().bis)

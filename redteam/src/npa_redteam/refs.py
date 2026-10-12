"""Known requirement IDs that cases and the scorecard may cite (task 7.1 / 7.2).

The lists mirror ``governance/rbi_mapping.md`` and ``governance/bis_mapping.md``. A case that
cites an unknown ID fails validation, so a typo can never create a phantom coverage entry.
BIS standards use their human-readable form everywhere (``IS/ISO/IEC 42001:2023``), the same
form as ``contracts/fixtures/scorecard.json``.
"""

from typing import Final

# WS3 rule IDs (``npa_rules.compliance_guard``, rule table in packages/rules/README.md) plus WS7
# IDs for requirements enforced by policy data, arithmetic or process (governance/rbi_mapping.md).
RBI_REQUIREMENTS: Final[frozenset[str]] = frozenset(
    {
        "RBI-CC-NPA-90",
        "RBI-CC-PAST-DUE-3D",
        "RBI-CC-LATE-FEE-BASE",
        "RBI-CC-BUREAU-NOTICE",
        "RBI-454D-DISTRESS",
        "RBI-454Y4-WINDOW",
        "RBI-454Y4-PREF",
        "RBI-454Y6-OCCASION",
        "RBI-454Z4-EXCESSIVE",
        "RBI-454Z-ABUSIVE",
        "RBI-454Z-THREAT",
        "RBI-454Z-THIRD-PARTY",
        "RBI-454Z-SHAMING",
        "RBI-454Z-MISLEADING",
        "RBI-454Z-ANONYMOUS",
        "RBI-454P-RECORDING",
        "RBI-454Q-INCENTIVES",
        "RBI-454O-DATA",
        "RBI-454AA-GRIEVANCE",
        "RBI-PF2019-RESTRUCTURE",
        "RBI-CS2023-SETTLEMENT",
        "DPDP-2023",
        "RBI-FREEAI-GOV",
        "BANK-POLICY-ONLY",
    }
)

BIS_STANDARDS: Final[frozenset[str]] = frozenset(
    {
        "IS/ISO/IEC 42001:2023",
        "IS/ISO/IEC 23894:2023",
        "IS/ISO 31000:2018",
        "IS/ISO/IEC 38507:2022",
        "IS/ISO/IEC TR 24027:2021",
        "IS/ISO/IEC TS 4213",
        "IS/ISO/IEC 25059:2023",
        "IS/ISO/IEC 22989:2022",
        "IS/ISO/IEC 23053:2022",
        "IS/ISO/IEC 8183:2023",
        "IS/ISO/IEC 27001:2022",
        "IS/ISO/IEC 27002:2022",
        "IS/ISO 10002:2018",
        "IS/ISO 18295-1:2017",
        "IS/ISO 18295-2:2017",
        "IS 17802 (Part 1):2021",
        "IS 17802 (Part 2):2022",
    }
)

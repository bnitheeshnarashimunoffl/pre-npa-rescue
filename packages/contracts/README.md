# npa_contracts

**Owner:** WS5 (with the team lead). Shared: changes follow [contracts/README.md](../../contracts/README.md).

Python mirror of the shared contracts (A7). Every package imports its shared types from here.

| Module | Contents |
|---|---|
| `enums` | A7.1 enums (`Bucket`, `Segment`, `UpliftGroup`, `ReliefType`, `Role`, `Lang`, ...) |
| `models` | A7.3 shared objects (Pydantic v2, `extra="forbid"`, aware datetimes, paise ints) |
| `api` | REST request/response envelopes for `/api/v1` |
| `providers` | A7.5 `Protocol` interfaces (`RiskProvider`, `PolicyProvider`, `LLMClient`, ...) |
| `constants` | Regulatory constants with RBI citations; `bucket_for_dpd()` |
| `money` | `to_paise`, `to_rupees`, `format_inr` (`₹1,00,000`), `format_inr_compact` (`₹2 lakh`), `split_evenly` |

```python
from npa_contracts.models import RiskScore, ReliefOption
from npa_contracts.money import format_inr

format_inr(200_000)  # '₹2,000'
```

Quality bar: strict mypy and 100% line+branch coverage (enforced in CI).

```bash
uv run pytest packages/contracts/tests --cov=npa_contracts --cov-fail-under=100
```

RBI references: NPA at >90 DPD (2015 circular), 3-day past-due grace (Credit Card Directions 2025),
08:00-19:00 contact window (RBC Directions para 454Y(4)), 180-day record retention (454P),
settlement thresholds (2023 framework), 30-day complaint SLA (454AA; IS/ISO 10002:2018).

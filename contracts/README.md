# contracts/ — single source of truth for interfaces

**Owner:** WS5 (with the team lead). Shared: every change follows the process below.
**Current version:** `0.1.0` (see [CHANGELOG.md](CHANGELOG.md)).

| Path | What | How it is produced |
|---|---|---|
| `schemas/*.schema.json` | JSON Schema (draft 2020-12) per shared object | **Generated** from `packages/contracts/src/npa_contracts/{models,api}.py` by `scripts/export_schemas.py` |
| `openapi.yaml` | REST contract, prefix `/api/v1` | **Generated** from the FastAPI routes in `services/api/app/routers/` by `scripts/export_openapi.py` |
| `data/*.md` | Parquet table specs (A7.2) | Hand-written |
| `fixtures/*.json` | Example payloads for tests and mocks (A7.6) | Hand-written v0; producers replace them with real sample outputs |

Never edit generated files by hand. CI fails if they are out of date or if any fixture
fails its schema.

```bash
uv run python scripts/export_schemas.py    # regenerate schemas
uv run python scripts/export_openapi.py    # regenerate openapi.yaml
uv run python scripts/check_contracts.py   # validate schemas, openapi and fixtures
```

Output is deterministic (sorted keys, UTF-8, LF), so the files are byte-identical on
Windows, macOS and Linux.

## Fixture → schema map

| Fixture | Schema |
|---|---|
| `risk_score.json` | `RiskScore` |
| `segment.json` | `SegmentResult` |
| `uplift.json` | `UpliftResult` |
| `nba.json` | `NextBestAction` |
| `queue.json` | `QueuePage` (10 `QueueItem`s incl. Priya and Ravi) |
| `relief_options_priya.json`, `relief_options_ravi.json` | array of `ReliefOption` |
| `offer.json` | `Offer` |
| `bot_reply_offer.json`, `bot_reply_zero_capacity.json` | `BotReply` |
| `complaint.json` | `Complaint` |
| `callback.json` | `Callback` |
| `scorecard.json` | `Scorecard` |
| `simulation_metrics.json` | `SimulationMetrics` |
| `policy.json` | `PolicyDocument` |

A new fixture must be added to `FIXTURES` in `scripts/check_contracts.py`.

## How to change a contract (A10.2)

1. Open an issue with the **contract_change** template: what changes, why, who is affected,
   backward compatible or not.
2. Branch `contracts/<short-desc>`. Change **together** in one PR:
   - `packages/contracts/` (the Pydantic models / enums / protocols),
   - the regenerated `contracts/schemas/` and `contracts/openapi.yaml`,
   - affected `contracts/fixtures/`,
   - a `contracts/CHANGELOG.md` entry, and bump `CONTRACT_VERSION` in
     `packages/contracts/src/npa_contracts/__init__.py` (`0.x.y`: minor = additive,
     patch = docs/fixtures).
3. Label the PR `contract`. It needs approval from WS5 **and** the owner of every affected
   workstream; breaking changes also need the team lead.
4. Prefer **additive** changes (new optional fields, new endpoints). Never rename or remove a
   field without the full process.

**Replacing a fixture with real output** (producers, any time): PR labelled `contract`, the
new file must pass `scripts/check_contracts.py`, add a patch-level CHANGELOG line.

# data/

**Owner:** WS1 (Data foundation). Generator code: [`packages/datagen`](../packages/datagen/).

| Path | Committed? | What |
|---|---|---|
| `raw/` | no (gitignored) | downloaded public data (`scripts/download_public.py`) |
| `generated/` | no (gitignored) | Parquet outputs (`$DATA_DIR`) |
| `samples/` | yes, ≤ 5 MB total | small samples for tests (`features_sample.parquet`, `labels_sample.parquet`) |
| `scripts/` | yes | `download_public.py`, `sanity_report.py` |
| `ATTRIBUTION.md` | yes | dataset licences and credits |

**Synthetic data only. Never commit real personal data or raw downloads.**

## Still to come

- **Calibration** from UCI and the NT$ → INR scaling (task 1.1).
- **Population and statement rules** (task 1.1).
- **Shocks, behaviour types, salary and transactions** (task 1.1).
- **Features, labels and samples** (task 1.2).
- **Demo persona numbers** (task 1.1 step 6, agreed with WS3).
- **Experiment probabilities and contact costs** (task 1.3).

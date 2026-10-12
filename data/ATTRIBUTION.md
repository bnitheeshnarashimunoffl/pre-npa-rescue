# Data attribution

Pre-NPA Rescue uses **synthetic data only**. Public datasets are used solely to calibrate
distributions; only the fitted parameters (`packages/datagen/src/datagen/calibration.json`) are
committed. Raw downloads live in `data/raw/` (gitignored) and are never committed.

| Dataset | Use | Licence | Credit |
|---|---|---|---|
| Default of Credit Card Clients (UCI ML Repository, dataset 350) | Calibration of limits, bill/payment ratios, payment-status transitions, default rate | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Yeh, I. (2009). *Default of Credit Card Clients* [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C55S3H |

Optional sources (Kaggle Home Credit, IBM TabFormer) are added here only if used, after
checking their terms.

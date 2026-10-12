"""Download the public calibration datasets into $RAW_DATA_DIR (default ./data/raw).

Usage: uv run python data/scripts/download_public.py
Then:  uv run python -m datagen.calibrate_uci   (refreshes calibration.json)

Downloads are gitignored and never committed; see data/ATTRIBUTION.md for licences.
"""

import logging

from datagen.config import DatagenConfig
from datagen.download import download_uci

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    download_uci(DatagenConfig().raw_data_dir)

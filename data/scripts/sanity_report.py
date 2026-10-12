"""Print sanity checks for the generated data in $DATA_DIR (task 1.1 acceptance).

Usage: uv run python data/scripts/sanity_report.py
"""

from datagen.config import DatagenConfig
from datagen.sanity import report

if __name__ == "__main__":
    cfg = DatagenConfig()
    print(report(cfg.data_dir, cfg.as_of_month))

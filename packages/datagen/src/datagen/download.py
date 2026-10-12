"""Download public calibration datasets into ``RAW_DATA_DIR`` (never committed).

Only the UCI "Default of Credit Card Clients" dataset is required (CC BY 4.0, see
``data/ATTRIBUTION.md``). The generator never needs this at runtime: it reads the committed
``calibration.json``. CI never downloads anything.
"""

import logging
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

UCI_URL = "https://archive.ics.uci.edu/static/public/350/default+of+credit+card+clients.zip"
UCI_XLS_NAME = "default of credit card clients.xls"


def uci_xls_path(raw_dir: Path) -> Path:
    """Where the extracted UCI spreadsheet lives under ``raw_dir``."""
    return raw_dir / "uci" / UCI_XLS_NAME


def _fetch(url: str, dest: Path, *, timeout: float, retries: int) -> None:
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp, part.open("wb") as out:
                shutil.copyfileobj(resp, out)
            part.replace(dest)
            return
        except OSError as exc:
            logger.warning("download attempt=%d url=%s error=%s", attempt, url, exc)
            if attempt == retries:
                raise
            time.sleep(min(30, 2**attempt))


def download_uci(
    raw_dir: Path, *, url: str = UCI_URL, timeout: float = 600, retries: int = 3
) -> Path:
    """Download and extract the UCI dataset; returns the ``.xls`` path. Idempotent."""
    xls = uci_xls_path(raw_dir)
    if xls.exists():
        logger.info("uci already present path=%s", xls)
        return xls
    xls.parent.mkdir(parents=True, exist_ok=True)
    archive = xls.parent / "uci350.zip"
    if not zipfile.is_zipfile(archive):
        _fetch(url, archive, timeout=timeout, retries=retries)
    with zipfile.ZipFile(archive) as zf:
        member = next(n for n in zf.namelist() if n.lower().endswith(".xls"))
        with zf.open(member) as src, xls.open("wb") as out:
            shutil.copyfileobj(src, out)
    logger.info("uci extracted path=%s", xls)
    return xls

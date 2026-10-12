"""Downloader: works from a local zip (no network in tests), idempotent, fails loudly."""

import zipfile
from pathlib import Path

import pytest

from datagen.download import download_uci, uci_xls_path


def test_download_uci_from_local_zip(tmp_path: Path) -> None:
    archive = tmp_path / "src.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("default of credit card clients.xls", b"fake-xls")
    raw = tmp_path / "raw"
    xls = download_uci(raw, url=archive.as_uri(), retries=1)
    assert xls == uci_xls_path(raw)
    assert xls.read_bytes() == b"fake-xls"
    assert download_uci(raw, url="file:///does-not-exist", retries=1) == xls  # idempotent


def test_download_failure_raises(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        download_uci(tmp_path, url=(tmp_path / "missing.zip").as_uri(), retries=1)

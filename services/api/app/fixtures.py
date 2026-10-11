"""Fixture-backed data for stub routes and provider fallbacks (contracts/fixtures/)."""

import json
from functools import lru_cache
from typing import Any

from app.config import get_settings


@lru_cache
def load_fixture(name: str) -> Any:
    path = get_settings().contracts_dir / "fixtures" / name
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)

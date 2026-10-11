"""Export JSON Schemas for every shared model to ``contracts/schemas/``.

Usage:
    uv run python scripts/export_schemas.py           # regenerate
    uv run python scripts/export_schemas.py --check   # CI: fail if out of date
"""

import argparse
import inspect
import sys
from pathlib import Path
from typing import Any

from contract_io import CONTRACTS_DIR, dump_json, sync_files

from npa_contracts import CONTRACT_VERSION, api, models
from npa_contracts.models import ContractModel

SCHEMA_DIR = CONTRACTS_DIR / "schemas"


def contract_models() -> dict[str, type[ContractModel]]:
    """Every public ContractModel subclass in npa_contracts.models and npa_contracts.api."""
    found: dict[str, type[ContractModel]] = {}
    for module in (models, api):
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, ContractModel) and obj is not ContractModel:
                found[name] = obj
    return dict(sorted(found.items()))


def schema_for(name: str, model: type[ContractModel]) -> dict[str, Any]:
    schema = model.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"{name}.schema.json"
    schema["x-contract-version"] = CONTRACT_VERSION
    return schema


def expected_files() -> dict[Path, str]:
    return {
        SCHEMA_DIR / f"{name}.schema.json": dump_json(schema_for(name, model))
        for name, model in contract_models().items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if files are out of date")
    args = parser.parse_args()
    rc = sync_files(expected_files(), check=args.check, stale_glob=(SCHEMA_DIR, "*.schema.json"))
    if rc == 0:
        print("schemas: ok" if args.check else f"schemas: wrote {SCHEMA_DIR}")
    return rc


if __name__ == "__main__":
    sys.exit(main())

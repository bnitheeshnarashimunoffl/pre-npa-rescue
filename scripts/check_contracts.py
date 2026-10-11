"""Validate the contracts: JSON Schemas, openapi.yaml and every fixture.

Usage: uv run python scripts/check_contracts.py
"""

import json
import sys
from pathlib import Path
from typing import Any

import yaml
from contract_io import CONTRACTS_DIR
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate as validate_openapi
from pydantic import ValidationError

from npa_contracts import api, models

SCHEMA_DIR = CONTRACTS_DIR / "schemas"
FIXTURE_DIR = CONTRACTS_DIR / "fixtures"

# fixture file -> (schema/model name, is a JSON array of that model)
FIXTURES: dict[str, tuple[str, bool]] = {
    "risk_score.json": ("RiskScore", False),
    "segment.json": ("SegmentResult", False),
    "uplift.json": ("UpliftResult", False),
    "nba.json": ("NextBestAction", False),
    "queue.json": ("QueuePage", False),
    "relief_options_priya.json": ("ReliefOption", True),
    "relief_options_ravi.json": ("ReliefOption", True),
    "offer.json": ("Offer", False),
    "bot_reply_offer.json": ("BotReply", False),
    "bot_reply_zero_capacity.json": ("BotReply", False),
    "complaint.json": ("Complaint", False),
    "callback.json": ("Callback", False),
    "scorecard.json": ("Scorecard", False),
    "simulation_metrics.json": ("SimulationMetrics", False),
    "policy.json": ("PolicyDocument", False),
}


def _model(name: str) -> Any:
    return getattr(models, name, None) or getattr(api, name)


def check_schemas(errors: list[str]) -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            errors.append(f"{path.name}: invalid JSON Schema: {exc}")
        schemas[path.name.removesuffix(".schema.json")] = schema
    if not schemas:
        errors.append("no schemas found; run scripts/export_schemas.py")
    return schemas


def check_openapi(errors: list[str]) -> None:
    path = CONTRACTS_DIR / "openapi.yaml"
    try:
        validate_openapi(yaml.safe_load(path.read_text(encoding="utf-8")))
    except Exception as exc:
        errors.append(f"openapi.yaml: {exc}")


def check_fixture(path: Path, schema: dict[str, Any], name: str, many: bool) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    items = data if many else [data]
    if many and not isinstance(data, list):
        return [f"{path.name}: expected a JSON array of {name}"]
    validator = Draft202012Validator(schema)
    for i, item in enumerate(items):
        for err in validator.iter_errors(item):
            loc = "/".join(str(p) for p in err.absolute_path)
            problems.append(f"{path.name}[{i}] {loc}: {err.message}")
    model = _model(name)
    for i, item in enumerate(items):
        try:
            model.model_validate(item)
        except ValidationError as exc:
            problems.append(f"{path.name}[{i}]: pydantic: {exc}")
    return problems


def main() -> int:
    errors: list[str] = []
    schemas = check_schemas(errors)
    check_openapi(errors)

    present = {p.name for p in FIXTURE_DIR.glob("*.json")}
    for missing in sorted(set(FIXTURES) - present):
        errors.append(f"missing fixture: {missing}")
    for unknown in sorted(present - set(FIXTURES)):
        errors.append(f"fixture {unknown} has no schema mapping in scripts/check_contracts.py")
    for fname, (name, many) in sorted(FIXTURES.items()):
        if fname in present and name in schemas:
            errors.extend(check_fixture(FIXTURE_DIR / fname, schemas[name], name, many))
        elif name not in schemas:
            errors.append(f"{fname}: schema {name} not found")

    for e in errors:
        print(f"ERROR {e}")
    if errors:
        return 1
    print(f"contracts: ok ({len(schemas)} schemas, openapi, {len(FIXTURES)} fixtures)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

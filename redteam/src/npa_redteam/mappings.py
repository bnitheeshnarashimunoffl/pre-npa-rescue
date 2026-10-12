"""Requirement catalogue (``mappings.yaml``) and evidence lookup (task 7.2).

The catalogue lists every RBI requirement ID and BIS standard the scorecard reports on, with
the evidence that exists outside the red-team run (governance documents, WS3 unit tests, WS2
reports). :meth:`Evidence.status` checks that evidence on disk, so a path only counts once its
file has landed on the branch being scored.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MAPPINGS_PATH",
    "BisStandard",
    "EvidenceRef",
    "Mappings",
    "RbiRequirement",
    "default_mappings",
    "repo_root",
]

MAPPINGS_PATH = Path(__file__).with_name("mappings.yaml")
EvidenceKind = Literal["doc", "code", "test", "report"]
BisArea = Literal[
    "Govern the AI",
    "Prove it is fair and accurate",
    "Protect customer data",
    "Treat customers well",
    "Include everyone",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class EvidenceRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: EvidenceKind
    ref: str

    def present(self, root: Path) -> bool:
        """Docs/code/reports: the path exists. Tests: ``file::name`` defines ``name``."""
        path, _, name = self.ref.partition("::")
        target = root / path
        if not target.exists():
            return False
        if self.kind != "test" or not name:
            return True
        source = target.read_text(encoding="utf-8")
        return re.search(rf"^\s*def {re.escape(name)}\(", source, re.MULTILINE) is not None


class _Item(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    docs: tuple[str, ...] = ()
    code: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    reports: tuple[str, ...] = ()

    def evidence(self) -> list[EvidenceRef]:
        kinds: list[tuple[EvidenceKind, tuple[str, ...]]] = [
            ("doc", self.docs),
            ("code", self.code),
            ("test", self.tests),
            ("report", self.reports),
        ]
        return [EvidenceRef(kind=k, ref=r) for k, refs in kinds for r in refs]


class RbiRequirement(_Item):
    title: str
    source: str
    redteam: Literal["in_scope", "planned", "out_of_scope"]
    note: str = ""


class BisStandard(_Item):
    area: BisArea
    themes: str


class Mappings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    rbi: dict[str, RbiRequirement] = Field(min_length=1)
    bis: dict[str, BisStandard] = Field(min_length=1)

    @classmethod
    def load(cls, path: Path = MAPPINGS_PATH) -> Mappings:
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@cache
def default_mappings() -> Mappings:
    return Mappings.load()

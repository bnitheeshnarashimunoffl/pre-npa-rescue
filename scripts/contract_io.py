"""Deterministic file output shared by the contract export scripts.

Generated files must be byte-identical on Windows, macOS and Linux so the CI "up to date"
check is stable: sorted keys, UTF-8, LF line endings, trailing newline.
"""

import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = REPO_ROOT / "contracts"


def dump_json(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def dump_yaml(data: Any) -> str:
    text: str = yaml.safe_dump(
        data, sort_keys=True, allow_unicode=True, default_flow_style=False, width=4096
    )
    return text


def read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    # newline="" disables newline translation so CRLF files show up as stale.
    with path.open(encoding="utf-8", newline="") as fh:
        return fh.read()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def sync_files(expected: dict[Path, str], *, check: bool, stale_glob: tuple[Path, str]) -> int:
    """Write ``expected`` (or, with ``check``, report differences). Returns an exit code.

    Files matching ``stale_glob`` (directory, pattern) that are not expected are removed
    (or reported in check mode).
    """
    problems: list[str] = []
    for path, text in sorted(expected.items()):
        if read_text(path) != text:
            if check:
                problems.append(f"out of date: {path.relative_to(REPO_ROOT).as_posix()}")
            else:
                write_text(path, text)
    directory, pattern = stale_glob
    for path in sorted(directory.glob(pattern)):
        if path not in expected:
            if check:
                problems.append(f"stale file: {path.relative_to(REPO_ROOT).as_posix()}")
            else:
                path.unlink()
    for p in problems:
        print(p)
    if problems:
        print("Run the export scripts (see docs/setup.md) and commit the result.")
        return 1
    return 0

"""Validate local Markdown targets in the authoritative documentation ownership map."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
MAP = ROOT / "docs/README.md"


def validate() -> list[str]:
    text = MAP.read_text(encoding="utf-8")
    missing = []
    for target in re.findall(r"\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)", text):
        if "://" in target:
            continue
        if not (MAP.parent / target).resolve().exists():
            missing.append(target)
    return missing


def main() -> None:
    missing = validate()
    if missing:
        raise SystemExit(f"missing documentation owners: {missing}")
    print("documentation ownership map: pass")


if __name__ == "__main__":
    main()

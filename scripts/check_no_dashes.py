#!/usr/bin/env python3
"""Fail if an em dash or en dash appears in a tracked text file.

House style. The characters are written here as escape sequences so that this
file does not trip its own check.
"""

from __future__ import annotations

import sys
from pathlib import Path

FORBIDDEN = {
    "\u2013": "en dash",
    "\u2014": "em dash",
    "\u2012": "figure dash",
    "\u2015": "horizontal bar",
}

SKIP_NAMES = {"LICENSE", "uv.lock"}
SKIP_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".hypothesis",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "examples",
    "htmlcov",
}


def offending_lines(path: Path) -> list[tuple[int, str, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    hits: list[tuple[int, str, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for char, name in FORBIDDEN.items():
            if char in line:
                hits.append((number, name, line.strip()[:90]))
    return hits


def should_skip(path: Path) -> bool:
    if path.name in SKIP_NAMES:
        return True
    return any(part in SKIP_PARTS for part in path.parts)


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv] or sorted(Path().rglob("*"))
    failures = 0
    for path in paths:
        if not path.is_file() or should_skip(path):
            continue
        for number, name, line in offending_lines(path):
            print(f"{path}:{number}: {name}: {line}")
            failures += 1
    if failures:
        print(f"\n{failures} forbidden dash character(s) found.")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))

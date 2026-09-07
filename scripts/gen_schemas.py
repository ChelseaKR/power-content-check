#!/usr/bin/env python3
"""Write the committed JSON Schemas from the model.

``make schemas`` runs this. ``tests/test_schemas.py`` runs the same builders and
fails when the committed files differ, so the files in ``schemas/`` are a
generated artifact that cannot be edited by hand without the gate noticing.

Exits 1 and lists what changed when run with ``--check``, which is what a caller
wanting a dry run should use.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from power_content_check.schemas import (  # noqa: E402
    catalog_schema,
    registered_check_ids,
    render,
    report_schema,
)

OUT = ROOT / "schemas"


def documents() -> dict[Path, str]:
    return {
        OUT / "report-v1.schema.json": render(report_schema(registered_check_ids())),
        OUT / "catalog-v1.schema.json": render(catalog_schema()),
    }


def main(argv: list[str]) -> int:
    check_only = "--check" in argv[1:]
    OUT.mkdir(exist_ok=True)
    stale: list[Path] = []
    for path, text in documents().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        stale.append(path)
        if not check_only:
            path.write_text(text, encoding="utf-8")
    if not stale:
        print("schemas: up to date")
        return 0
    verb = "would rewrite" if check_only else "wrote"
    for path in stale:
        print(f"schemas: {verb} {path.relative_to(ROOT)}")
    return 1 if check_only else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

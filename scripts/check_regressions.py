"""Compare conclusions about cached labels against a recorded baseline.

The calibration labels live in a local cache that git excludes, so the test
suite cannot use them and must not need them. What a contributor with the
cache wants is narrower and stronger: before pushing, prove that this tree's
conclusions about every cached label are byte for byte what some earlier tree
concluded. Fingerprints make that possible, because they hash what the tool
concluded and exclude paths, timestamps, versions and digests.

Usage:

    uv run python scripts/check_regressions.py record    # write the baseline
    uv run python scripts/check_regressions.py compare   # diff against it

The baseline is written beside the cache and is not committed; it is a fact
about one machine's cache, not about the project. A first `record` on a new
machine is expected and is not a finding.

Like every script here, this is not part of the package and the CLI never
invokes it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from power_content_check.checks import CheckContext
from power_content_check.engine import check_paths, fingerprint
from power_content_check.model import RunReport

CACHE = Path(__file__).resolve().parent.parent / "examples" / "cache"
BASELINE = CACHE / "fingerprints.json"


def collect() -> dict[str, str]:
    """Run the checker over the whole cache and map digest to fingerprint.

    Keyed by content digest rather than file name, because names are how a
    cache reorganises itself and a fingerprint is not about a path.
    """
    if not CACHE.is_dir():
        print(f"no cache at {CACHE}; fetch examples first (scripts/fetch_examples.py)")
        raise SystemExit(1)
    paths = sorted(p for p in CACHE.iterdir() if p.suffix.lower() in (".pdf", ".txt"))
    if not paths:
        print(f"no supported documents in {CACHE}")
        raise SystemExit(1)
    report: RunReport = check_paths(paths, CheckContext())
    out: dict[str, str] = {}
    for document in report.documents:
        assert document.sha256, "a readable or unreadable document carries its digest"
        out[document.sha256] = fingerprint(
            RunReport(
                tool=report.tool,
                tool_version=report.tool_version,
                ruleset_id=report.ruleset_id,
                ruleset_effective=report.ruleset_effective,
                generated_at=report.generated_at,
                notice=report.notice,
                documents=[document],
            )
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("record", "compare"))
    args = parser.parse_args()

    current = collect()
    if args.action == "record":
        BASELINE.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        print(f"recorded {len(current)} fingerprints in {BASELINE}")
        return 0

    if not BASELINE.exists():
        print(f"no baseline at {BASELINE}; run 'record' first")
        return 64
    recorded = json.loads(BASELINE.read_text())

    changed = {
        digest: (recorded[digest], fp)
        for digest, fp in current.items()
        if digest in recorded and recorded[digest] != fp
    }
    unseen = sorted(set(recorded) - set(current))
    added = sorted(set(current) - set(recorded))

    if unseen:
        print(f"{len(unseen)} cached documents are gone from the cache since recording:")
        for digest in unseen[:5]:
            print(f"  {digest[:12]}")
    if added:
        print(f"{len(added)} documents are new to the cache; rerun 'record' to adopt them")

    if changed:
        print(f"{len(changed)} documents now conclude differently than the baseline says:")
        for digest, (old, new) in list(changed.items())[:10]:
            print(f"  {digest[:12]}  {old[:12]} -> {new[:12]}")
        print(
            "A change means either the code moved a conclusion or the ruleset"
            " identifier did. If the change is intended, say so in the changelog"
            " and rerun 'record'."
        )
        return 1
    print(f"{len(current)} documents conclude exactly as recorded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

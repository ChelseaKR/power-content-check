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
    uv run python scripts/check_regressions.py compare --explain   # and say what moved

A fingerprint says *that* a conclusion moved and never *which*. `--explain`
answers the second question by running `power_content_check.diff` over the
reports `record` stored beside the fingerprints, so the check that moved is
named with its finding on both sides. It refuses rather than guessing when the
baseline predates the stored reports: a baseline recorded before this option
existed carries no reports, and explaining nothing must not read like nothing
moved.

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
from typing import Any

from power_content_check.checks import CheckContext
from power_content_check.diff import compare, render_text
from power_content_check.engine import check_paths, fingerprint
from power_content_check.model import RunReport

CACHE = Path(__file__).resolve().parent.parent / "examples" / "cache"
BASELINE = CACHE / "fingerprints.json"

#: Full JSON reports beside the fingerprints, keyed by the same content digest.
#: Written by `record` so that `compare --explain` has two sides to diff. Not
#: committed, for the same reason the baseline is not: it is a fact about one
#: machine's cache. Absent from any baseline recorded before this existed, which
#: `--explain` reports as a refusal rather than as an empty explanation.
REPORTS = CACHE / "reports.json"


def _single(report: RunReport, document: object) -> RunReport:
    """One document's report, carrying the run's identity, for a per-document view."""
    return RunReport(
        tool=report.tool,
        tool_version=report.tool_version,
        ruleset_id=report.ruleset_id,
        ruleset_effective=report.ruleset_effective,
        generated_at=report.generated_at,
        notice=report.notice,
        documents=[document],  # type: ignore[list-item]
    )


def collect_reports() -> dict[str, dict[str, Any]]:
    """Every cached document's full report, keyed by content digest."""
    report = _run_over_cache()
    out: dict[str, dict[str, Any]] = {}
    for document in report.documents:
        assert document.sha256, "a readable or unreadable document carries its digest"
        out[document.sha256] = _single(report, document).to_dict()
    return out


def _run_over_cache() -> RunReport:
    """Read the cache and check it, refusing an absent or empty one."""
    if not CACHE.is_dir():
        print(f"no cache at {CACHE}; fetch examples first (scripts/fetch_examples.py)")
        raise SystemExit(1)
    paths = sorted(p for p in CACHE.iterdir() if p.suffix.lower() in (".pdf", ".txt"))
    if not paths:
        print(f"no supported documents in {CACHE}")
        raise SystemExit(1)
    return check_paths(paths, CheckContext())


def explain(changed: dict[str, tuple[str, str]]) -> int:
    """Say which check moved on each document whose fingerprint moved.

    Returns the number of documents actually explained, so the caller can tell an
    explanation from a silence. Zero explained while something moved is reported as a
    refusal by the caller, never as agreement.
    """
    if not REPORTS.exists():
        print(
            f"\n--explain: no recorded reports at {REPORTS}. The baseline predates this "
            "option, so there is no earlier side to compare against. Rerun 'record' to "
            "store them; until then a fingerprint move can be seen but not explained."
        )
        return 0
    recorded_reports: dict[str, Any] = json.loads(REPORTS.read_text())
    current_reports = collect_reports()
    explained = 0
    for digest in changed:
        before, after = recorded_reports.get(digest), current_reports.get(digest)
        if before is None or after is None:
            print(f"\n{digest[:12]}: no stored report on one side, so nothing to compare")
            continue
        print(f"\n{digest[:12]}:")
        rendered = render_text(compare(before, after, by_hash=True))
        print(rendered if rendered else "  the fingerprint moved and no check status did")
        explained += 1
    return explained


def _report_explanations(changed: dict[str, tuple[str, str]]) -> None:
    """Explain what moved, and say plainly when some of it could not be explained."""
    explained = explain(changed)
    if explained < len(changed):
        print(
            f"\n{len(changed) - explained} of {len(changed)} moved documents could not "
            "be explained. Not explained is not unchanged."
        )


def collect() -> dict[str, str]:
    """Run the checker over the whole cache and map digest to fingerprint.

    Keyed by content digest rather than file name, because names are how a
    cache reorganises itself and a fingerprint is not about a path.
    """
    report = _run_over_cache()
    out: dict[str, str] = {}
    for document in report.documents:
        assert document.sha256, "a readable or unreadable document carries its digest"
        out[document.sha256] = fingerprint(_single(report, document))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("record", "compare"))
    parser.add_argument(
        "--explain",
        action="store_true",
        help=(
            "for each document whose fingerprint moved, name the checks whose status "
            "moved with the finding on both sides (compare only)"
        ),
    )
    args = parser.parse_args()

    current = collect()
    if args.action == "record":
        BASELINE.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        REPORTS.write_text(json.dumps(collect_reports(), indent=2, sort_keys=True) + "\n")
        print(f"recorded {len(current)} fingerprints in {BASELINE}")
        print(f"recorded {len(current)} reports in {REPORTS} (for compare --explain)")
        return 0

    if not BASELINE.exists():
        print(f"no baseline at {BASELINE}; run 'record' first")
        return 64
    recorded = json.loads(BASELINE.read_text())

    # The comparison happens over the intersection, so the intersection is the
    # denominator and it has to be stated. Reporting a pass over an empty one
    # is the shape this script exists to catch elsewhere: a cache replaced
    # wholesale used to print "N documents conclude exactly as recorded",
    # naming a count of documents not one of which had been compared, and
    # exit 0. Three pull requests quote this line as evidence that no
    # conclusion about a published label moved, so the sentence has to be
    # true.
    compared = sorted(set(current) & set(recorded))
    changed = {
        digest: (recorded[digest], current[digest])
        for digest in compared
        if recorded[digest] != current[digest]
    }
    unseen = sorted(set(recorded) - set(current))
    added = sorted(set(current) - set(recorded))

    if unseen:
        print(f"{len(unseen)} cached documents are gone from the cache since recording:")
        for digest in unseen[:5]:
            print(f"  {digest[:12]}")
    if added:
        print(f"{len(added)} documents are new to the cache; rerun 'record' to adopt them")

    if not compared:
        print(
            f"none of the {len(current)} documents in the cache appear in the baseline, "
            "so nothing was compared and this run proves nothing. If the cache was "
            "replaced on purpose, rerun 'record' and say so."
        )
        return 1

    if changed:
        print(f"{len(changed)} documents now conclude differently than the baseline says:")
        for digest, (old, new) in list(changed.items())[:10]:
            print(f"  {digest[:12]}  {old[:12]} -> {new[:12]}")
        if args.explain:
            _report_explanations(changed)
        print(
            "A change means either the code moved a conclusion or the ruleset"
            " identifier did. If the change is intended, say so in the changelog"
            " and rerun 'record'."
        )
        return 1
    print(f"{len(compared)} documents conclude exactly as recorded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

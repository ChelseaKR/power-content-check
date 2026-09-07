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
    uv run python scripts/check_regressions.py census --vintage 2024   # publish the counts

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

`census` is the one thing here whose output *is* about the project. It reduces
the same run over the same cache to counts -- per registered check, on how many
labels it conformed, deviated and went unevaluated -- plus the digests of the
labels counted, and writes them to `docs/calibration/census.json`, which is
committed. No supplier name, no file name, no path and no URL is in it, so it
carries the evidence behind the figures the README publishes without
redistributing a label. The census needs the cache; reading it does not, and
`tests/test_calibration_census.py` holds the README to it on every run
everywhere, cache or no cache.

Like every script here, this is not part of the package and the CLI never
invokes it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from power_content_check.checks import CHECKS, CheckContext
from power_content_check.diff import compare, render_text
from power_content_check.engine import check_paths, fingerprint
from power_content_check.model import RunReport, Status

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "examples" / "cache"
BASELINE = CACHE / "fingerprints.json"

#: The calibration census. Unlike everything else this script writes, this file
#: is committed: it is a fact about the project's evidence, not about one
#: machine's cache.
CENSUS = ROOT / "docs" / "calibration" / "census.json"

#: Shape version of the census document. Within one version every key is
#: append only, on the same rule as the report schema (docs/adr/0010).
CENSUS_VERSION = 1

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


class CensusError(ValueError):
    """The cache cannot produce a census that says what it appears to say."""


def build_census(report: RunReport, vintage: str) -> dict[str, Any]:
    """Reduce one run to the counts the README's figures are read from.

    Only counts, check identifiers and content digests survive. A path, a file
    name, a supplier or a URL would make the census a per-supplier record, and
    the refusal on rankings is what lets it be published at all.

    Two things are refused rather than counted, because both make the census
    read as more evidence than it is: a document with no digest, and the same
    digest twice. The second is the one that matters -- a cache holding one
    label under two names would publish a labels-read figure larger than the
    number of labels actually read, which is this project's own dominant defect
    class turned on its evidence.
    """
    digests: list[str] = []
    for document in report.documents:
        if not document.sha256:
            raise CensusError(f"{document.path}: no content digest, so it cannot be counted")
        if document.sha256 in digests:
            raise CensusError(
                f"{document.sha256[:12]} appears twice in the cache. One label counted "
                "twice would inflate every figure in the census."
            )
        digests.append(document.sha256)
    if not digests:
        raise CensusError("no documents in the cache; an empty census is not a measurement")

    checks: dict[str, dict[str, int]] = {
        registered.spec.id: {status.value: 0 for status in Status} for registered in CHECKS
    }
    for document in report.documents:
        for result in document.results:
            if result.check_id not in checks:
                raise CensusError(f"{result.check_id}: not a registered check")
            checks[result.check_id][result.status.value] += 1

    return {
        "census_version": CENSUS_VERSION,
        "tool": report.tool,
        "tool_version": report.tool_version,
        "ruleset_id": report.ruleset_id,
        "ruleset_effective": report.ruleset_effective,
        "label_vintage": vintage,
        "labels_read": len(digests),
        "labels": sorted(digests),
        "checks": {check_id: checks[check_id] for check_id in sorted(checks)},
    }


def census_problems(census: dict[str, Any]) -> list[str]:
    """Everything internally wrong with a census document, named.

    Returned rather than raised so that a caller can report all of it at once,
    and so the test suite can drive the failing branch on synthetic input on
    every run instead of waiting for a bad census to exist.
    """
    problems: list[str] = []
    labels = census.get("labels", [])
    read = census.get("labels_read")
    if len(set(labels)) != len(labels):
        problems.append("the label list repeats a digest, so a label is counted twice")
    if read != len(labels):
        problems.append(f"labels_read is {read} but {len(labels)} digests are listed")
    if census.get("census_version") != CENSUS_VERSION:
        problems.append(f"census_version is {census.get('census_version')}, expected 1")
    if not census.get("label_vintage"):
        problems.append("no label_vintage, so the census does not say what it counted")
    for check_id, tally in sorted(census.get("checks", {}).items()):
        total = sum(tally.values())
        if total != read:
            problems.append(f"{check_id}: {total} outcomes recorded against {read} labels")
    return problems


def write_census(vintage: str) -> int:
    """Write the census from the cache, refusing to write one that is wrong."""
    census = build_census(_run_over_cache(), vintage)
    problems = census_problems(census)
    if problems:
        for problem in problems:
            print(f"census: {problem}")
        return 1
    CENSUS.parent.mkdir(parents=True, exist_ok=True)
    CENSUS.write_text(json.dumps(census, indent=2, sort_keys=True) + "\n")
    deviating = sorted(
        check_id
        for check_id, tally in census["checks"].items()
        if tally[Status.DOES_NOT_CONFORM.value] > 0
    )
    print(f"wrote {CENSUS} over {census['labels_read']} labels")
    print(f"{len(deviating)} checks deviate on at least one label: {', '.join(deviating) or '-'}")
    return 0


def _census_action(vintage: str | None) -> int:
    """The census branch of ``main``, held apart so ``main`` stays readable."""
    if not vintage:
        print("census: --vintage is required; say which label year the cache holds")
        return 64
    try:
        return write_census(vintage)
    except CensusError as refusal:
        print(f"census: {refusal}")
        return 1


def _record_action(current: dict[str, str]) -> int:
    """Write the baseline and the reports `compare --explain` needs beside it."""
    BASELINE.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
    REPORTS.write_text(json.dumps(collect_reports(), indent=2, sort_keys=True) + "\n")
    print(f"recorded {len(current)} fingerprints in {BASELINE}")
    print(f"recorded {len(current)} reports in {REPORTS} (for compare --explain)")
    return 0


def _compare_action(current: dict[str, str], explain_moves: bool) -> int:
    """Diff this tree's conclusions against the baseline, over a stated denominator."""
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
        if explain_moves:
            _report_explanations(changed)
        print(
            "A change means either the code moved a conclusion or the ruleset"
            " identifier did. If the change is intended, say so in the changelog"
            " and rerun 'record'."
        )
        return 1
    print(f"{len(compared)} documents conclude exactly as recorded.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("record", "compare", "census"))
    parser.add_argument(
        "--vintage",
        help=(
            "the label year the cache holds, e.g. 2024 (census only). Required, and "
            "not guessed: which year was fetched is a fact about the fetch, not "
            "something the cached bytes say."
        ),
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help=(
            "for each document whose fingerprint moved, name the checks whose status "
            "moved with the finding on both sides (compare only)"
        ),
    )
    args = parser.parse_args()

    if args.action == "census":
        return _census_action(args.vintage)

    current = collect()
    if args.action == "record":
        return _record_action(current)
    return _compare_action(current, args.explain)


if __name__ == "__main__":
    sys.exit(main())

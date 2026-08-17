"""Running the catalog over documents.

The engine holds two invariants:

* A document that could not be read produces a NOT_EVALUATED result for every
  registered check. It never produces an empty result list, because an empty
  result list renders as "nothing wrong".

* A check that raises produces a NOT_EVALUATED result carrying the exception
  type. It never produces CONFORMS and it never propagates.

Between them, there is no path through this module on which the tool cannot
see a document and reports it as clean.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .checks import CHECKS, CheckContext, RegisteredCheck
from .citations import NOTICE, RULESET_EFFECTIVE, RULESET_ID
from .extract import DEFAULT_MIN_TEXT_CHARS, LabelDocument, discover, extract
from .model import CheckResult, DocumentReport, Readability, RunReport, Status

TOOL_NAME = "power-content-check"


def _all_not_evaluated(
    finding: str,
    detail: str | None,
    registry: Sequence[RegisteredCheck] = CHECKS,
) -> list[CheckResult]:
    return [
        CheckResult(
            check_id=registered.spec.id,
            status=Status.NOT_EVALUATED,
            finding=finding,
            detail=detail,
        )
        for registered in registry
    ]


def run_checks(
    doc: LabelDocument,
    ctx: CheckContext,
    registry: Sequence[RegisteredCheck] = CHECKS,
) -> list[CheckResult]:
    """Run every registered check against one readable document.

    ``registry`` defaults to the full catalog. It is a parameter so that the
    fail-closed behaviour can be tested against a check that is guaranteed to
    raise, without reaching into module state.
    """
    results: list[CheckResult] = []
    for registered in registry:
        spec = registered.spec
        if not spec.implemented or registered.run is None:
            results.append(
                CheckResult(
                    check_id=spec.id,
                    status=Status.NOT_EVALUATED,
                    finding="Not evaluated: this check is registered but enforces no rule.",
                    detail=spec.unimplemented_reason,
                )
            )
            continue
        try:
            result = registered.run(doc, ctx)
        except Exception as exc:  # a crash must not become a pass
            results.append(
                CheckResult(
                    check_id=spec.id,
                    status=Status.NOT_EVALUATED,
                    finding="Not evaluated: the check raised an error.",
                    detail=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        if result.check_id != spec.id:  # pragma: no cover - guards a coding mistake
            raise AssertionError(f"{spec.id} returned a result for {result.check_id}")
        results.append(result)
    return results


def check_document(
    path: Path,
    ctx: CheckContext | None = None,
    min_chars: int = DEFAULT_MIN_TEXT_CHARS,
    registry: Sequence[RegisteredCheck] = CHECKS,
) -> DocumentReport:
    """Check one document and report on it, readable or not."""
    ctx = ctx or CheckContext()
    outcome = extract(path, min_chars=min_chars)

    if not isinstance(outcome, LabelDocument):
        return DocumentReport(
            path=str(path),
            readability=Readability.UNREADABLE,
            unreadable_reason=outcome.reason,
            sha256=outcome.sha256,
            page_count=None,
            results=_all_not_evaluated(
                "Not evaluated: the document could not be read.",
                outcome.reason,
                registry,
            ),
        )

    return DocumentReport(
        path=str(path),
        readability=Readability.READABLE,
        unreadable_reason=None,
        sha256=outcome.sha256,
        page_count=outcome.page_count,
        results=run_checks(outcome, ctx, registry),
        image_count=outcome.image_count,
        extraction_basis=outcome.extraction_basis,
    )


def check_paths(
    paths: list[Path],
    ctx: CheckContext | None = None,
    min_chars: int = DEFAULT_MIN_TEXT_CHARS,
    now: datetime | None = None,
    registry: Sequence[RegisteredCheck] = CHECKS,
) -> RunReport:
    """Check every document reachable from ``paths``.

    If that set is empty the report carries no documents, and
    :attr:`RunReport.exit_code` is 3. Checking nothing is not a pass.
    """
    documents = [check_document(p, ctx, min_chars, registry) for p in discover(paths)]
    stamp = (now or datetime.now(UTC)).replace(microsecond=0).isoformat()
    return RunReport(
        tool=TOOL_NAME,
        tool_version=__version__,
        ruleset_id=RULESET_ID,
        ruleset_effective=RULESET_EFFECTIVE,
        generated_at=stamp,
        documents=documents,
        notice=NOTICE,
    )


def fingerprint(report: RunReport) -> str:
    """A hash of what the run concluded.

    Deliberately excludes file paths, the timestamp, the tool version and the
    document digest, so that two runs hash the same only when they reached the
    same conclusions. That makes it meaningful to assert that an unreadable
    input and a clean input do not produce the same output.
    """
    payload = [
        [
            document.readability.value,
            document.unreadable_reason,
            [[r.check_id, r.status.value, r.finding] for r in document.results],
        ]
        for document in report.documents
    ]
    canonical = json.dumps(
        {"exit_code": report.exit_code, "documents": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

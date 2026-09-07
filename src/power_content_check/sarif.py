"""The run as a SARIF 2.1.0 log.

``check --json`` is machine readable and it is this tool's own shape, so anyone
gating a document in CI writes an adapter first. SARIF is the shape those
surfaces already read: GitHub code scanning, CI annotations, and every other
static-analysis consumer.

This is a serialiser and nothing more. It reads a finished
:class:`~power_content_check.model.RunReport`, changes no conclusion, and leaves
the exit code exactly as :class:`~power_content_check.model.ExitCode` documents
it. What it must not do is lose the tool's fail-closed contract in translation,
and that contract is easy to lose here, because SARIF's natural shape is "a list
of problems found" and this tool's central claim is about the checks it could
*not* decide.

So the mapping is written down rather than left implicit:

===========================  =================================================
what the run concluded       where it lands in the log
===========================  =================================================
``does_not_conform``         a ``result`` at level ``error``
``conforms``                 counted in ``invocations[0].properties``; no result
``not_evaluated``, and the   a ``toolConfigurationNotification`` at ``note``
check is registered but      carrying the registered reason and its blocker
not implemented
``not_evaluated``, and the   a ``toolConfigurationNotification`` at ``error``
check *is* implemented       carrying the finding
an unreadable document       a ``toolExecutionNotification`` at ``error``, and
                             no results for that document at all
an advisory                  ``runs[0].properties.advisories``; never a result
===========================  =================================================

Three of those rows are the point.

**A conforming check emits no result and is still counted.** A consumer must be
able to see the denominator. A log carrying only deviations lets "we found
nothing" and "we looked at nothing" render identically.

**The two kinds of not-evaluated are separated by severity, not merged.** A
check this tool has never implemented is a documented, permanent property of the
catalog: it is in every run, and raising it as an error would make every run
scream and get muted within a month, which is how a real signal dies. A check
that *is* implemented and still could not be decided on this document is the
other thing entirely. The tool tried to look and could not, and that is the
case this repository refuses to let read as a pass. Both carry
``properties.implemented`` so a consumer can tell them apart without reading the
level, and both are present in the log, always.

**``executionSuccessful`` is false when nothing was checked.** SARIF uses it for
"the tool failed to complete", and finding a deviation is not that. But a run
over zero documents that reported ``executionSuccessful: true`` with an empty
results array is indistinguishable, to every consumer, from a clean run. Exit
code 3 exists in this tool precisely because an empty denominator is never a
pass, and the log has to say the same thing.

The log is deterministic: results and notifications are sorted, and the only
timestamp is the run's own ``generated_at``, carried as a property rather than
as ``invocation.startTimeUtc``, because this tool does not measure when its
execution began.
"""

from __future__ import annotations

import json
from typing import Any

from .checks import BY_ID, CHECKS
from .model import (
    CheckResult,
    DocumentReport,
    ExitCode,
    Readability,
    RunReport,
    Status,
)

SARIF_VERSION = "2.1.0"

SARIF_SCHEMA = (
    "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json"
)
"""OASIS's own URL for the 2.1.0 errata01 schema.

Deliberately not the ``raw.githubusercontent.com/oasis-tcs/sarif-spec/master/...``
address that circulates in tooling: that path was measured returning 404 on
2026-09-07, because the specification repository moved its schema and dropped
the ``master`` branch. A ``$schema`` nobody can resolve is a broken contract
that no test notices, since nothing fetches it.
"""

INFORMATION_URI = "https://github.com/ChelseaKR/power-content-check"

_LEVEL_DEVIATION = "error"
_LEVEL_UNDECIDED_IMPLEMENTED = "error"
_LEVEL_UNIMPLEMENTED = "note"
_LEVEL_UNREADABLE = "error"


def _rules() -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Every registered check as a SARIF rule, and its index.

    The whole catalog, not only the implemented half. A rule missing from the
    driver is a check a consumer cannot look up, and the registered-only checks
    are exactly the ones whose reason a reader needs.
    """
    rules: list[dict[str, Any]] = []
    index: dict[str, int] = {}
    for position, check in enumerate(CHECKS):
        spec = check.spec
        citation = spec.citation
        index[spec.id] = position
        rules.append(
            {
                "id": spec.id,
                "name": spec.id,
                "shortDescription": {"text": spec.title},
                "fullDescription": {"text": spec.what_it_looks_for},
                "help": {
                    "text": (
                        f"{citation.source.title} {citation.locator}: "
                        f"“{citation.quote}” ({citation.source.url})"
                    )
                },
                "properties": {
                    "basis": spec.basis.value,
                    "implemented": spec.implemented,
                    "unimplementedReason": spec.unimplemented_reason,
                    "blocker": spec.blocker.value if spec.blocker else None,
                    "citation": citation.to_dict(),
                },
            }
        )
    return rules, index


def _location(uri: str) -> dict[str, Any]:
    return {"physicalLocation": {"artifactLocation": {"uri": uri}}}


def _message(result: CheckResult, document: DocumentReport) -> str:
    """What the check concluded, always with the basis the tool looked on.

    ``checks._bad`` already appends the extraction basis to a deviation's
    detail, so this appends it only where it is not already there. A message
    that says an element is absent, without saying what the tool was able to
    read, is a claim the reader cannot weigh.
    """
    parts = [result.finding]
    if result.detail:
        parts.append(result.detail)
    text = " ".join(part for part in parts if part)
    basis = document.extraction_basis
    if basis and basis not in text:
        text = f"{text} {basis}".strip()
    return text


def _results(document: DocumentReport, index: dict[str, int]) -> list[dict[str, Any]]:
    found = [
        {
            "ruleId": result.check_id,
            "ruleIndex": index[result.check_id],
            "level": _LEVEL_DEVIATION,
            "kind": "fail",
            "message": {"text": _message(result, document)},
            "locations": [_location(document.path)],
            "partialFingerprints": {"checkId": result.check_id},
        }
        for result in document.results
        if result.status is Status.DOES_NOT_CONFORM
    ]
    return sorted(found, key=lambda item: (str(item["ruleId"]), document.path))


def _configuration_notifications(
    document: DocumentReport, index: dict[str, int]
) -> list[dict[str, Any]]:
    """One notification per check this run could not decide on this document.

    Both kinds appear. The level separates a permanent catalog gap from a check
    that tried and could not, and ``properties.implemented`` states which
    without a consumer having to infer it from the level.
    """
    notifications: list[dict[str, Any]] = []
    for result in document.results:
        if result.status is not Status.NOT_EVALUATED:
            continue
        spec = BY_ID[result.check_id].spec
        reason = spec.unimplemented_reason if not spec.implemented else None
        text = _message(result, document)
        if reason:
            text = f"{text} {reason}".strip()
        notifications.append(
            {
                "descriptor": {"id": result.check_id, "index": index[result.check_id]},
                "associatedRule": {
                    "id": result.check_id,
                    "index": index[result.check_id],
                },
                "level": (
                    _LEVEL_UNDECIDED_IMPLEMENTED if spec.implemented else _LEVEL_UNIMPLEMENTED
                ),
                "message": {"text": text},
                "locations": [_location(document.path)],
                "properties": {
                    "implemented": spec.implemented,
                    "blocker": spec.blocker.value if spec.blocker else None,
                    "status": result.status.value,
                },
            }
        )
    return sorted(notifications, key=lambda item: str(item["associatedRule"]["id"]))


def _execution_notifications(report: RunReport) -> list[dict[str, Any]]:
    """One per document the tool could not read, plus one for a run that read nothing.

    An unreadable document contributes no results and no per-check
    notifications, because no check ran. If the only thing in the log were the
    empty results array, the log would say the document is clean.
    """
    notifications = [
        {
            "descriptor": {"id": "unreadable-document"},
            "level": _LEVEL_UNREADABLE,
            "message": {
                "text": (
                    f"{document.path} could not be read, so no check was run against it "
                    f"and it is not reported as conforming. Reason: "
                    f"{document.unreadable_reason}"
                )
            },
            "locations": [_location(document.path)],
            "properties": {"path": document.path},
        }
        for document in report.documents
        if document.readability is Readability.UNREADABLE
    ]
    if not report.documents:
        notifications.append(
            {
                "descriptor": {"id": "nothing-checked"},
                "level": "error",
                "message": {
                    "text": (
                        "No document was checked. An empty denominator is never a pass: "
                        "this run concluded nothing about any label."
                    )
                },
                "properties": {"documentsChecked": 0},
            }
        )
    return sorted(notifications, key=lambda item: str(item["message"]["text"]))


def _exit_code_meaning(code: int) -> str:
    return {
        ExitCode.OK: "every document was readable and every implemented check conformed",
        ExitCode.NONCONFORMANCE: "at least one check found a deviation",
        ExitCode.NOT_EVALUATED: "at least one check could not be evaluated",
        ExitCode.NOTHING_CHECKED: "nothing was checked",
    }.get(code, "unrecognised exit code")


def report_to_sarif_dict(report: RunReport) -> dict[str, Any]:
    """The whole run as one SARIF run."""
    rules, index = _rules()

    results: list[dict[str, Any]] = []
    configuration: list[dict[str, Any]] = []
    for document in report.documents:
        if document.readability is Readability.UNREADABLE:
            continue
        results.extend(_results(document, index))
        configuration.extend(_configuration_notifications(document, index))

    invocation: dict[str, Any] = {
        # Not "did the analysis come out clean". A deviation is a successful
        # run. A run that checked nothing is not, and saying otherwise would
        # let a consumer read an empty log as a clean one.
        "executionSuccessful": report.exit_code != ExitCode.NOTHING_CHECKED,
        "exitCode": report.exit_code,
        "exitCodeDescription": _exit_code_meaning(report.exit_code),
        "toolExecutionNotifications": _execution_notifications(report),
        "toolConfigurationNotifications": configuration,
        "properties": {
            "summary": report.summary,
            "skipped": list(report.skipped),
        },
    }

    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": report.tool,
                        "version": report.tool_version,
                        "informationUri": INFORMATION_URI,
                        "rules": rules,
                        "properties": {
                            "rulesetId": report.ruleset_id,
                            "rulesetEffective": report.ruleset_effective,
                            "notice": report.notice,
                        },
                    }
                },
                "invocations": [invocation],
                "results": sorted(
                    results,
                    key=lambda item: (
                        str(item["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]),
                        str(item["ruleId"]),
                    ),
                ),
                "properties": {
                    "generatedAt": report.generated_at,
                    "rulesetId": report.ruleset_id,
                    "rulesetEffective": report.ruleset_effective,
                    # Fenced off, per ADR 0013: an advisory carries no status,
                    # is in no count and reaches no exit code, so it must not
                    # become a result. It is carried here so nothing is lost.
                    "advisories": [
                        {"path": document.path, **advisory.to_dict()}
                        for document in report.documents
                        for advisory in document.advisories
                    ],
                },
            }
        ],
    }


def render_sarif(report: RunReport) -> str:
    """The SARIF log as text. Same bytes for the same report."""
    return json.dumps(report_to_sarif_dict(report), indent=2, sort_keys=True, ensure_ascii=False)

"""Rendering a run as text or as JSON."""

from __future__ import annotations

import json
import textwrap
from typing import Any

from .checks import BY_ID
from .model import DocumentReport, ExitCode, Readability, RunReport, Status

_MARK = {
    Status.CONFORMS: "  ok  ",
    Status.DOES_NOT_CONFORM: " FAIL ",
    Status.NOT_EVALUATED: " n/e  ",
}

_WIDTH = 88


def _wrap(text: str, indent: str) -> str:
    return textwrap.fill(
        text,
        width=_WIDTH,
        initial_indent=indent,
        subsequent_indent=indent,
    )


def render_json(report: RunReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=False, ensure_ascii=False)


def _render_document(document: DocumentReport, verbose: bool) -> list[str]:
    lines: list[str] = ["", document.path, "-" * min(len(document.path), _WIDTH)]

    if document.readability is Readability.UNREADABLE:
        lines.append("  NOT EVALUATED: this document could not be read.")
        lines.append(_wrap(f"Reason: {document.unreadable_reason}", "  "))
        lines.append(
            _wrap(
                "No check was run. An unreadable document is never reported as conforming.",
                "  ",
            )
        )
        return lines

    if document.extraction_basis:
        lines.append(_wrap(document.extraction_basis, "  "))

    for result in document.results:
        spec = BY_ID[result.check_id].spec
        if result.status is Status.NOT_EVALUATED and not spec.implemented and not verbose:
            continue
        if result.status is Status.CONFORMS and not verbose:
            continue
        lines.append(f"  [{_MARK[result.status]}] {result.check_id}  {spec.title}")
        lines.append(_wrap(result.finding, "            "))
        if result.detail:
            lines.append(_wrap(result.detail, "            "))
        lines.append(
            _wrap(
                f"Cited: {spec.citation.locator} of {spec.citation.source.key} "
                f"<{spec.citation.source.url}>",
                "            ",
            )
        )

    counts = document.counts
    lines.append(
        "  Summary: "
        f"{counts[Status.CONFORMS.value]} conform, "
        f"{counts[Status.DOES_NOT_CONFORM.value]} do not conform, "
        f"{counts[Status.NOT_EVALUATED.value]} not evaluated."
    )
    return lines


def render_text(report: RunReport, verbose: bool = False) -> str:
    lines: list[str] = [
        f"{report.tool} {report.tool_version}",
        f"Ruleset: {report.ruleset_id} (effective {report.ruleset_effective})",
        "",
        _wrap(report.notice, ""),
    ]

    if not report.documents:
        lines += [
            "",
            "NOTHING CHECKED.",
            _wrap(
                "No label was checked, so no statement about conformance can be made. "
                "This is not a pass. Check the paths you supplied.",
                "  ",
            ),
        ]
        return "\n".join(lines)

    for document in report.documents:
        lines += _render_document(document, verbose)

    summary = report.summary
    lines += [
        "",
        "=" * _WIDTH,
        f"Documents checked:    {summary['documents_checked']}",
        f"  readable:           {summary['documents_readable']}",
        f"  unreadable:         {summary['documents_unreadable']}",
        f"Checks conforming:    {summary['conforms']}",
        f"Checks not conforming:{summary['does_not_conform']}",
        f"Checks not evaluated: {summary['not_evaluated']}",
        f"Exit code:            {report.exit_code} ({_exit_meaning(report.exit_code)})",
    ]
    if not verbose:
        lines.append("Pass --verbose to list conforming and unimplemented checks too.")
    return "\n".join(lines)


def _exit_meaning(code: int) -> str:
    return {
        ExitCode.OK: "readable throughout, no deviation found",
        ExitCode.NONCONFORMANCE: "at least one deviation from the prescribed format",
        ExitCode.NOT_EVALUATED: "at least one check could not be evaluated",
        ExitCode.NOTHING_CHECKED: "nothing was checked, which is not a pass",
        ExitCode.USAGE_ERROR: "usage error",
    }.get(code, "unknown")


def render_catalog(as_json: bool = False) -> str:
    """Print the catalog itself, so the rules are auditable without a label."""
    from .checks import CHECKS

    if as_json:
        payload: list[dict[str, Any]] = [c.spec.to_dict() for c in CHECKS]
        return json.dumps(payload, indent=2, ensure_ascii=False)

    lines: list[str] = []
    for registered in CHECKS:
        spec = registered.spec
        state = "implemented" if spec.implemented else "REGISTERED, ENFORCES NOTHING"
        if spec.blocker:
            state = f"{state}, {spec.blocker.value}"
        lines.append(f"{spec.id}  {spec.title}  [{state}, basis: {spec.basis.value}]")
        lines.append(_wrap(f"Cites: {spec.citation.locator} of", "    "))
        lines.append(_wrap(spec.citation.source.title, "      "))
        lines.append(_wrap(f"URL: {spec.citation.source.url}", "      "))
        lines.append(_wrap(f'Quote: "{spec.citation.quote}"', "    "))
        if spec.implemented:
            lines.append(_wrap(f"Looks for: {spec.what_it_looks_for}", "    "))
        else:
            blocker = spec.blocker.value if spec.blocker else "unclassified"
            lines.append(
                _wrap(f"Why not implemented [{blocker}]: {spec.unimplemented_reason}", "    ")
            )
        lines.append("")
    return "\n".join(lines)

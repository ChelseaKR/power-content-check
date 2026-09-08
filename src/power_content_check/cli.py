"""Command line interface.

Offline. Reads the files you name and nothing else. No network call, no
telemetry, no account, no configuration file, no cache.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from . import __version__
from .checks import CheckContext
from .citations import NOTICE
from .diff import (
    DiffExit,
    Kind,
    ReportUnreadable,
    SchemaMismatch,
    compare,
    load_report,
    render_jsonl,
)
from .diff import render_text as render_diff_text
from .engine import check_paths, fingerprint
from .explain import UnknownCheck, explain
from .explain import render_json as render_explain_json
from .explain import render_text as render_explain_text
from .extract import DEFAULT_MIN_TEXT_CHARS, SUPPORTED_SUFFIXES
from .model import ExitCode, RunReport
from .report import render_catalog, render_json, render_text
from .sarif import render_sarif

_EPILOG = f"""\
exit codes
  0  every document was readable and every implemented check conformed
  1  at least one check found a deviation from the prescribed format
  2  at least one check could not be evaluated, including any document that
     could not be read
  3  nothing was checked; an empty denominator is never a pass
  {ExitCode.USAGE_ERROR}  usage error

Higher codes win, so a run that checked nothing cannot report as a run that
found nothing.

Supported inputs: {", ".join(SUPPORTED_SUFFIXES)}. A directory is expanded to
the supported files inside it, and anything else in it is named at the end of
the report rather than dropped in silence.
"""


class _Parser(argparse.ArgumentParser):
    """A parser that exits with the usage code this tool publishes.

    argparse exits 2 on a usage error. This tool documents 64 for that case in
    three places: :data:`ExitCode.USAGE_ERROR`, the exit code table in the
    README, and the epilog above, which the tool prints in its own ``--help``.
    Every one of those said 64 while the program returned 2.

    A tool that documents one exit code and returns another is telling a
    caller something untrue, and a caller who reads the table cannot tell a
    usage error from "at least one check could not be evaluated". So the
    parser is brought to the documented code, rather than the documentation
    down to argparse's default. 64 is EX_USAGE from sysexits.h, which is the
    convention ``scripts/check_regressions.py`` already follows.

    Only ``error`` is overridden. ``--help`` and ``--version`` exit through
    ``parser.exit(0)`` without passing through here, and still exit 0.
    """

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(ExitCode.USAGE_ERROR, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="power-content-check",
        description=(
            "Check a California Power Content Label against the published label "
            "format. Structural conformance only. " + NOTICE
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser(
        "check",
        help="check one or more label files",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    check.add_argument("paths", nargs="*", type=Path, help="label files or directories")
    check.add_argument(
        "--supplier-name",
        default=None,
        help=(
            "the retail supplier's company name, so PCL001 can look for it. "
            "Without this, PCL001 reports as not evaluated rather than guessing."
        ),
    )
    check.add_argument(
        "--min-text-chars",
        type=int,
        default=DEFAULT_MIN_TEXT_CHARS,
        help=(
            "below this many extracted characters a document is treated as "
            "unreadable rather than as a sparse label "
            f"(default: {DEFAULT_MIN_TEXT_CHARS}). This is an engineering "
            "threshold, not a regulatory one, and no check cites it."
        ),
    )
    check.add_argument("--json", action="store_true", help="emit the report as JSON")
    check.add_argument(
        "--sarif",
        action="store_true",
        help=(
            "emit the report as a SARIF 2.1.0 log, for code scanning and CI "
            "annotation surfaces. Redirect it to a file to upload it. Changes "
            "nothing the tool concludes and nothing about the exit code."
        ),
    )
    check.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="list conforming and unimplemented checks as well as deviations",
    )
    check.add_argument(
        "--no-evidence",
        action="store_true",
        help=(
            "omit the page and text run each result was read from. Changes "
            "nothing the tool concludes: statuses, exit code and fingerprint "
            "are identical either way."
        ),
    )
    check.add_argument(
        "--fingerprint",
        action="store_true",
        help="print a hash of the run's conclusions, excluding paths and timestamps",
    )

    catalog = sub.add_parser(
        "catalog",
        help="print every registered check with the requirement it cites",
    )
    catalog.add_argument("--json", action="store_true", help="emit the catalog as JSON")

    diff = sub.add_parser(
        "diff",
        help="compare two JSON reports and say which conclusions moved",
        description=(
            "Compare two reports emitted by `check --json`: two tool versions over one "
            "label, or one version over a label and its reissue. Prints every check "
            "whose status moved with the finding on both sides, and every document fact "
            "that moved beside it. Exit 0 nothing moved, 3 something moved, 64 the "
            "reports cannot be compared. A check present on one side only is reported "
            "as added or removed, never as a status move. " + NOTICE
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    diff.add_argument("before", type=Path, help="the earlier report (JSON)")
    diff.add_argument("after", type=Path, help="the later report (JSON)")
    diff.add_argument(
        "--by-hash",
        action="store_true",
        help=(
            "match documents by sha256 rather than by path, for when the paths differ "
            "and the bytes do not"
        ),
    )
    diff.add_argument(
        "--jsonl",
        action="store_true",
        help="emit one JSON object per change instead of the text rendering",
    )

    explain_cmd = sub.add_parser(
        "explain",
        help="show the text one check scanned and where the match failed",
        description=(
            "Run one registered check against one document and print its working: the "
            "text the check read, the literal or pattern it looked for, whether each "
            "one matched, and where the nearest candidate span stopped agreeing. It "
            "decides nothing new: the status it prints is the status `check` reaches, "
            "reached by the same code. Exit codes are the ones in the table below, for "
            "this one check. " + NOTICE
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    explain_cmd.add_argument("path", type=Path, help="the label file to read")
    explain_cmd.add_argument("check_id", metavar="CHECK_ID", help="a registered check, e.g. PCL012")
    explain_cmd.add_argument(
        "--supplier-name",
        default=None,
        help="the retail supplier's company name, which PCL001 compares against",
    )
    explain_cmd.add_argument(
        "--min-text-chars",
        type=int,
        default=DEFAULT_MIN_TEXT_CHARS,
        help=(
            "below this many extracted characters a document is treated as unreadable "
            f"(default: {DEFAULT_MIN_TEXT_CHARS})"
        ),
    )
    explain_cmd.add_argument("--json", action="store_true", help="emit the explanation as JSON")

    return parser


def _render(report: RunReport, args: argparse.Namespace) -> str:
    """One rendering of the run, in whichever shape was asked for.

    All three read the same finished report and none of them changes a
    conclusion or an exit code, which is what lets a caller pick a shape for
    its consumer rather than for its meaning.
    """
    if args.sarif:
        return render_sarif(report)
    if args.json:
        return render_json(report)
    return render_text(report, args.verbose)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "catalog":
        print(render_catalog(as_json=args.json))
        return ExitCode.OK

    if args.command == "diff":
        return _diff(args)

    if args.min_text_chars < 0:
        parser.error("--min-text-chars cannot be negative")

    if args.command == "check" and args.json and args.sarif:
        parser.error("--json and --sarif are two shapes of one report; ask for one")

    if args.command == "explain":
        return _explain(args, parser)

    if not args.paths:
        # Not a usage error. The tool was asked to check nothing, and it says
        # so in the same shape as any other run rather than printing a hint
        # that a script might read as success.
        report = check_paths([], CheckContext(), args.min_text_chars)
        print(_render(report, args))
        return report.exit_code

    report = check_paths(
        list(args.paths),
        CheckContext(
            supplier_name=args.supplier_name,
            collect_evidence=not args.no_evidence,
        ),
        args.min_text_chars,
    )
    print(_render(report, args))
    if args.fingerprint:
        print(f"fingerprint: {fingerprint(report)}")
    return report.exit_code


def _explain(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """``explain`` end to end.

    An unregistered identifier is a usage error, so it exits 64 like every
    other one. Anything else exits on the conclusion the check reached, which
    keeps a script wrapping ``explain`` reading the same table as a script
    wrapping ``check``.
    """
    try:
        explanation = explain(
            args.path,
            args.check_id,
            CheckContext(supplier_name=args.supplier_name),
            args.min_text_chars,
        )
    except UnknownCheck as unknown:
        parser.error(str(unknown))
    rendered = render_explain_json(explanation) if args.json else render_explain_text(explanation)
    print(rendered)
    return explanation.exit_code


def _diff(args: argparse.Namespace) -> int:
    """``diff`` end to end.

    Every refusal prints to stderr and returns 64, so a caller that only reads stdout
    sees an empty diff and a non-zero code rather than an empty diff and a zero one.
    """
    try:
        before = load_report(args.before)
        after = load_report(args.after)
        changes = compare(before, after, by_hash=args.by_hash)
    except (ReportUnreadable, SchemaMismatch) as exc:
        print(f"power-content-check diff: {exc}", file=sys.stderr)
        return DiffExit.REFUSED

    rendered = render_jsonl(changes) if args.jsonl else render_diff_text(changes)
    if rendered:
        print(rendered, end="")
    # `3` means something moved. "These two reports cannot be compared for advisories"
    # is not a movement: it is this verb saying what it could not look at, which is a
    # thing to print and not a thing to score. A row that only reports a limit must not
    # make a diff of two identical conclusions read as a diff that found a difference.
    moved = [c for c in changes if c.kind is not Kind.ADVISORIES_NOT_COMPARABLE]
    return DiffExit.MOVED if moved else DiffExit.UNCHANGED


def run() -> None:  # pragma: no cover - console script shim
    sys.exit(main())


if __name__ == "__main__":  # pragma: no cover
    run()

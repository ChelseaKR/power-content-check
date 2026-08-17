"""Command line interface.

Offline. Reads the files you name and nothing else. No network call, no
telemetry, no account, no configuration file, no cache.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .checks import CheckContext
from .citations import NOTICE
from .engine import check_paths, fingerprint
from .extract import DEFAULT_MIN_TEXT_CHARS, SUPPORTED_SUFFIXES
from .model import ExitCode
from .report import render_catalog, render_json, render_text

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
the supported files inside it.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
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
        "--verbose",
        "-v",
        action="store_true",
        help="list conforming and unimplemented checks as well as deviations",
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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "catalog":
        print(render_catalog(as_json=args.json))
        return ExitCode.OK

    if args.min_text_chars < 0:
        parser.error("--min-text-chars cannot be negative")

    if not args.paths:
        # Not a usage error. The tool was asked to check nothing, and it says
        # so in the same shape as any other run rather than printing a hint
        # that a script might read as success.
        report = check_paths([], CheckContext(), args.min_text_chars)
        print(render_json(report) if args.json else render_text(report, args.verbose))
        return report.exit_code

    report = check_paths(
        list(args.paths),
        CheckContext(supplier_name=args.supplier_name),
        args.min_text_chars,
    )
    print(render_json(report) if args.json else render_text(report, args.verbose))
    if args.fingerprint:
        print(f"fingerprint: {fingerprint(report)}")
    return report.exit_code


def run() -> None:  # pragma: no cover - console script shim
    sys.exit(main())


if __name__ == "__main__":  # pragma: no cover
    run()

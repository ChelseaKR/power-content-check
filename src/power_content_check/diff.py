"""Compare two JSON reports and say which conclusions moved.

``scripts/check_regressions.py`` compares fingerprints, so it can say *that* a conclusion
moved and never *which*. That is the right shape for a pre-push gate and the wrong shape
for the two questions people actually ask:

* a maintainer changing a matcher wants to see which check moved on which real label,
  before pushing;
* a supplier reissuing a label wants to see what the reissue changed.

Both are answered by comparing two reports the tool already emits.

Three fences hold, and each is a test.

**A check present on only one side is added or removed, never a status move.** Registering
a new check makes it appear on the later side with a status. Calling that a move would
report a conclusion that changed when nothing about the document did.

**Document facts only.** A report is a set of statements about a document; so is a diff of
two reports. Nothing here is a statement about a supplier, and no direction is called an
improvement: a move from ``does_not_conform`` to ``conforms`` is printed with both sides
and no adjective.

**Schema versions are compared before anything else.** ADR 0010 makes the report shape
append-only within a version, so two reports at different versions may disagree about what
a key holds. Diffing them anyway would silently attribute a schema change to the document.
It is refused, with both versions named.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .model import SCHEMA_VERSION


class DiffExit:
    """Exit codes for ``diff``, which are this verb's own.

    ``3`` here means "something moved", not ``ExitCode.NOTHING_CHECKED``. The two verbs
    answer different questions and neither code is read across them; a script wrapping
    ``diff`` reads these, a script wrapping ``check`` reads ``ExitCode``. Stated because a
    reader who knows one set will otherwise assume the other.

    0   Nothing moved.
    3   At least one conclusion or document fact moved.
    64  The two reports cannot be compared, or one could not be read.
    """

    UNCHANGED = 0
    MOVED = 3
    REFUSED = 64


class Kind(StrEnum):
    """What sort of movement a row records.

    ``CHECK_ADDED`` and ``CHECK_REMOVED`` exist so that registering or retiring a check is
    never reported as a status move on a document that did not change.
    """

    STATUS_MOVED = "status_moved"
    CHECK_ADDED = "check_added"
    CHECK_REMOVED = "check_removed"
    DOCUMENT_ADDED = "document_added"
    DOCUMENT_REMOVED = "document_removed"
    DOCUMENT_FACT_MOVED = "document_fact_moved"
    ADVISORY_MOVED = "advisory_moved"
    ADVISORIES_NOT_COMPARABLE = "advisories_not_comparable"


#: Document-level facts compared beside the check results. These qualify what a finding is
#: entitled to mean: a deviation found on a document the tool read as two pages is not the
#: same evidence as one found on a document it read as five.
#:
#: Hand kept, and held to the report by
#: :func:`tests.test_diff.test_every_document_key_is_either_compared_or_excused`. It was
#: hand kept and held to nothing until 2026-09-06, and the first key added to a document
#: report after that walked straight past it: ``advisories`` was emitted, never compared,
#: and nothing noticed. A list of what the code emits, maintained beside the code that
#: emits it, is exactly the thing that goes quietly out of date.
DOCUMENT_FACTS = (
    "readability",
    "unreadable_reason",
    "page_count",
    "image_count",
    "vector_shape_count",
    "extraction_basis",
)

#: Keys a document report carries that this module deliberately does not compare as facts,
#: each with the reason. The gate above reads this, so excusing a key is a decision written
#: down rather than an omission.
NOT_COMPARED: dict[str, str] = {
    "path": (
        "the identity of the document, not a statement about it, and matching by path or "
        "by sha256 is what `--by-hash` is for"
    ),
    "sha256": (
        "the identity of the bytes. Two reports on different bytes are the ordinary case "
        "for a reissued label, and reporting that as a movement would fire on every diff "
        "worth running"
    ),
    "counts": (
        "derived from the results, which are compared one by one. A count that moved with "
        "no status moving is impossible, and reporting both would double every row"
    ),
    "results": "compared check by check below, not as a blob",
    "advisories": (
        "compared, but by code and under its own kind rather than as a document fact: an "
        "advisory is not a conclusion and filing it among the facts that are would "
        "overstate it"
    ),
}


@dataclass(frozen=True)
class Change:
    """One movement, with both sides carried whole."""

    kind: Kind
    document: str
    check_id: str | None
    field: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "document": self.document,
            "check_id": self.check_id,
            "field": self.field,
            "before": self.before,
            "after": self.after,
        }

    def side(self, which: str) -> dict[str, Any]:
        """The named side, or a failure naming the row that lost it.

        A real check rather than an ``assert``: ``python -O`` strips asserts, and the
        rendering below would then interpolate ``None`` into a sentence a reader would
        take as a finding. Every ``Kind`` that reaches a renderer needing a side is
        constructed with one, so this raising is a broken invariant, not a user error.
        """
        value = self.before if which == "before" else self.after
        if value is None:
            raise ValueError(
                f"a {self.kind.value} row for {self.document} carries no {which} side, "
                "so there is nothing to report it as"
            )
        return value


class ReportUnreadable(Exception):
    """A report could not be read, so no comparison is reported.

    Never a default empty report: two empty reports compare equal, and "nothing moved"
    about two files that were never read is the vacuous pass this project is organised
    against.
    """


class SchemaMismatch(Exception):
    """The two reports declare different report schema versions."""


def load_report(path: Path) -> dict[str, Any]:
    """Parse one report, or refuse."""
    if not path.is_file():
        raise ReportUnreadable(f"{path}: no such file")
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        raise ReportUnreadable(f"{path}: the file is empty, so it states no conclusions")
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReportUnreadable(f"{path}: not parseable JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ReportUnreadable(f"{path}: top level is {type(loaded).__name__}, not a report object")
    if "documents" not in loaded:
        raise ReportUnreadable(
            f"{path}: no 'documents' key, so this is not a report this tool emitted. "
            "Produce one with `power-content-check check --json`."
        )
    if "schema_version" not in loaded:
        raise ReportUnreadable(
            f"{path}: no 'schema_version' key. Every report this tool has ever emitted "
            "carries one (ADR 0010), so its absence means the file was edited or came "
            "from something else."
        )
    return loaded


def _key(document: dict[str, Any], *, by_hash: bool) -> str | None:
    """How a document on one side is matched to a document on the other.

    By path by default, because that is what a person reading the two reports sees. By
    ``sha256`` with ``--by-hash``, for the case the paths differ and the bytes do not.
    ``None`` when the chosen key is absent, which is refused rather than bucketed under a
    shared empty string where several documents would silently collapse into one.
    """
    value = document.get("sha256") if by_hash else document.get("path")
    return value if isinstance(value, str) and value else None


def _index(report: dict[str, Any], *, by_hash: bool, side: str) -> dict[str, dict[str, Any]]:
    documents = report.get("documents")
    if not isinstance(documents, list):
        raise ReportUnreadable(f"{side}: 'documents' is not a list")
    indexed: dict[str, dict[str, Any]] = {}
    for document in documents:
        if not isinstance(document, dict):
            raise ReportUnreadable(f"{side}: a document entry is not an object")
        key = _key(document, by_hash=by_hash)
        if key is None:
            field = "sha256" if by_hash else "path"
            raise ReportUnreadable(
                f"{side}: a document carries no {field}, so it cannot be matched. "
                "An unreadable document still carries its digest; check the report."
            )
        if key in indexed:
            raise ReportUnreadable(
                f"{side}: two documents share the key {key!r}. Matching them would "
                "compare one against the wrong one."
            )
        indexed[key] = document
    return indexed


def _results_by_id(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = document.get("results") or []
    return {r["check_id"]: r for r in results if isinstance(r, dict) and "check_id" in r}


def _result_view(result: dict[str, Any]) -> dict[str, Any]:
    """The three fields a status move is reported with, always all three."""
    return {
        "status": result.get("status"),
        "finding": result.get("finding"),
        "detail": result.get("detail"),
    }


def _advisory_codes(document: dict[str, Any]) -> tuple[str, ...] | None:
    """The advisory codes a document report carries, or None if it carries no such key.

    None and ``()`` are different statements and this module must not merge them. A report
    written before the advisory channel existed has no ``advisories`` key at all, and it
    declares the same ``schema_version`` as one written after, because adding a key is
    append only within a version (ADR 0010). Reading the missing key as an empty list would
    report an advisory appearing on every document of every diff that spans that change:
    an absence rendered as a movement.
    """
    carried = document.get("advisories")
    if carried is None:
        return None
    return tuple(sorted(str(entry.get("code")) for entry in carried))


def _compare_advisories(before: dict[str, Any], after: dict[str, Any], *, key: str) -> list[Change]:
    """Advisories that appeared or went, or a statement that they cannot be compared.

    Compared by code, with both sides carried whole, which is the same shape the status
    comparison uses: the status triggers a row and the finding text travels on it. A
    reworded observation is a change in this tool, and this verb reports changes in the
    document.
    """
    old, new = _advisory_codes(before), _advisory_codes(after)
    if old is None or new is None:
        side = "the earlier" if old is None else "the later"
        return [
            Change(
                kind=Kind.ADVISORIES_NOT_COMPARABLE,
                document=key,
                check_id=None,
                field="advisories",
                before={"advisories": before.get("advisories")},
                after={"advisories": after.get("advisories"), "missing_from": side},
            )
        ]
    if old == new:
        return []
    return [
        Change(
            kind=Kind.ADVISORY_MOVED,
            document=key,
            check_id=None,
            field="advisories",
            before={"advisories": before.get("advisories"), "codes": list(old)},
            after={"advisories": after.get("advisories"), "codes": list(new)},
        )
    ]


def compare_documents(before: dict[str, Any], after: dict[str, Any], *, key: str) -> list[Change]:
    """Every movement between one document's two reports."""
    changes: list[Change] = []

    for fact in DOCUMENT_FACTS:
        old, new = before.get(fact), after.get(fact)
        if old != new:
            changes.append(
                Change(
                    kind=Kind.DOCUMENT_FACT_MOVED,
                    document=key,
                    check_id=None,
                    field=fact,
                    before={fact: old},
                    after={fact: new},
                )
            )

    changes.extend(_compare_advisories(before, after, key=key))

    old_results = _results_by_id(before)
    new_results = _results_by_id(after)

    for check_id in sorted(old_results.keys() & new_results.keys()):
        old_result, new_result = old_results[check_id], new_results[check_id]
        if old_result.get("status") != new_result.get("status"):
            changes.append(
                Change(
                    kind=Kind.STATUS_MOVED,
                    document=key,
                    check_id=check_id,
                    field=None,
                    before=_result_view(old_result),
                    after=_result_view(new_result),
                )
            )
    for check_id in sorted(new_results.keys() - old_results.keys()):
        changes.append(
            Change(
                kind=Kind.CHECK_ADDED,
                document=key,
                check_id=check_id,
                field=None,
                before=None,
                after=_result_view(new_results[check_id]),
            )
        )
    for check_id in sorted(old_results.keys() - new_results.keys()):
        changes.append(
            Change(
                kind=Kind.CHECK_REMOVED,
                document=key,
                check_id=check_id,
                field=None,
                before=_result_view(old_results[check_id]),
                after=None,
            )
        )
    return changes


def compare(
    before: dict[str, Any], after: dict[str, Any], *, by_hash: bool = False
) -> list[Change]:
    """Every movement between two whole reports, sorted so two runs agree.

    A pure function of two parsed documents, so the tests can run it over reports it must
    report on rather than only over the pair the fixtures happen to produce.
    """
    old_version = before.get("schema_version")
    new_version = after.get("schema_version")
    if old_version != new_version:
        raise SchemaMismatch(
            f"the reports declare different report schema versions: {old_version!r} "
            f"and {new_version!r}. Within one version the shape is append only "
            f"(ADR 0010); across versions a key may not hold the same thing, so a "
            f"difference here could be the schema rather than the document. This tool "
            f"emits schema_version {SCHEMA_VERSION}."
        )

    old_docs = _index(before, by_hash=by_hash, side="the earlier report")
    new_docs = _index(after, by_hash=by_hash, side="the later report")

    changes: list[Change] = []
    for key in sorted(old_docs.keys() & new_docs.keys()):
        changes.extend(compare_documents(old_docs[key], new_docs[key], key=key))
    for key in sorted(new_docs.keys() - old_docs.keys()):
        changes.append(
            Change(
                kind=Kind.DOCUMENT_ADDED,
                document=key,
                check_id=None,
                field=None,
                before=None,
                after=None,
            )
        )
    for key in sorted(old_docs.keys() - new_docs.keys()):
        changes.append(
            Change(
                kind=Kind.DOCUMENT_REMOVED,
                document=key,
                check_id=None,
                field=None,
                before=None,
                after=None,
            )
        )
    return sorted(
        changes,
        key=lambda c: (c.document, c.kind.value, c.check_id or "", c.field or ""),
    )


def _describe(change: Change) -> list[str]:
    if change.kind is Kind.STATUS_MOVED:
        before, after = change.side("before"), change.side("after")
        return [
            f"  {change.check_id}: {before['status']} -> {after['status']}",
            f"      was: {before['finding']}",
            f"      now: {after['finding']}",
        ]
    if change.kind is Kind.CHECK_ADDED:
        after = change.side("after")
        return [
            f"  {change.check_id}: not in the earlier report (newly registered), "
            f"now {after['status']}",
            f"      now: {after['finding']}",
        ]
    if change.kind is Kind.CHECK_REMOVED:
        before = change.side("before")
        return [
            f"  {change.check_id}: {before['status']} in the earlier report, not in the later one",
            f"      was: {before['finding']}",
        ]
    if change.kind is Kind.DOCUMENT_FACT_MOVED:
        before, after = change.side("before"), change.side("after")
        field = change.field or ""
        return [f"  {field}: {before[field]!r} -> {after[field]!r}"]
    if change.kind is Kind.ADVISORY_MOVED:
        before, after = change.side("before"), change.side("after")
        return [
            f"  advisories: {before['codes']} -> {after['codes']}",
            "      not a conclusion; in no count and no exit code on either side",
        ]
    if change.kind is Kind.ADVISORIES_NOT_COMPARABLE:
        after = change.side("after")
        return [
            f"  advisories: not compared. {after['missing_from']} report carries no "
            "advisories key at all, so it predates the channel",
            "      an absent key is not an empty list, and is not reported as one",
        ]
    if change.kind is Kind.DOCUMENT_ADDED:
        return ["  in the later report only"]
    return ["  in the earlier report only"]


def render_text(changes: list[Change]) -> str:
    """The console rendering. Prints nothing at all when nothing moved."""
    if not changes:
        return ""
    lines: list[str] = []
    current: str | None = None
    for change in changes:
        if change.document != current:
            current = change.document
            lines.extend(["", current, "-" * min(len(current), 88)])
        lines.extend(_describe(change))
    moved = sum(1 for c in changes if c.kind is Kind.STATUS_MOVED)
    lines.extend(
        [
            "",
            f"{len(changes)} movements across "
            f"{len({c.document for c in changes})} documents; "
            f"{moved} of them a check status.",
            "A move is reported with both sides and no direction. Nothing here is a "
            "statement about a supplier.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_jsonl(changes: list[Change]) -> str:
    """One JSON object per change, sorted, so two runs emit identical bytes."""
    return "".join(
        json.dumps(change.to_dict(), sort_keys=True, ensure_ascii=False) + "\n"
        for change in changes
    )

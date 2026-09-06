"""Show the work behind one check on one document.

``docs/AUDITING.md`` section 2 tells a reader who does not trust this tool how
to reproduce a finding by hand: extract the text, normalise it, search it. That
is the right instruction and it is a lot of work, and until the reader has done
it they are taking the tool's word for where in the extracted text a prescribed
phrase is or is not.

``explain`` does those steps and prints them: which text the check read, which
literal or pattern it looked for, whether each one matched, and where the
nearest candidate span stopped agreeing with the phrase. That last part is what
separates a genuine deviation from a phrase the extractor broke apart in a way
:mod:`power_content_check.normalize` does not yet fold, which is exactly how the
two false findings recorded in ADR 0006 were found.

Four fences hold, and each one is a test.

**It decides nothing.** The status, finding and detail come from
:func:`power_content_check.engine.check_document`, run over a registry holding
the single named check. It is the same function ``check`` runs, so the
conclusion is identical by construction rather than by agreement, including the
engine's promise that an unreadable document and a raising check both become
NOT_EVALUATED.

**Near miss reporting is descriptive and threshold free.** It reports the
longest run of characters, anchored on the phrase's first character, over which
the document and the phrase agree. There is no cut off above which a near miss
becomes a match, so nothing here can turn into a lenient matcher and reach back
into a status. ADR 0007's fence holds: position is reported, never decided on.

**No probe list is silently empty.** A scan plan carries at least one phrase or
one pattern, or else it says in words that this check compared nothing and why.
An empty probe list rendered as a clean report would be this portfolio's oldest
defect wearing a new hat.

**A pattern that finds nothing reports nothing found.** Near miss reporting
applies to literal phrases. For a regular expression the output says whether it
matched and quotes what it matched; it does not invent a nearest span, because
"how close did this text come to matching a regular expression" has no answer
this module is entitled to give.

The plans below describe the checks; they do not derive them. That description
is bound two ways in ``tests/test_explain.py``: every literal a plan names must
occur in ``checks.py`` itself, and on the conforming fixture every check that
reports ``conforms`` must have at least one of its declared probes match. A
plan that drifts from the check it describes fails there.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .checks import (
    _DOMAIN,
    _EMAIL,
    _FOOTNOTE_1_LEAD,
    _FOOTNOTE_2_LEAD,
    _FOOTNOTE_3_LEAD,
    _PHONE,
    _TOTAL_ROW,
    _UNSPECIFIED_ANNOTATION,
    _YEAR_TITLE,
    CHECKS,
    CONDITIONAL_FUEL_TYPES,
    GROUP_NAMES,
    REQUIRED_FUEL_TYPES,
    STATEWIDE_RENDERINGS,
    CheckContext,
    RegisteredCheck,
    _domains,
)
from .engine import check_document
from .extract import DEFAULT_MIN_TEXT_CHARS, LabelDocument, extract
from .model import CheckResult, CheckSpec, DocumentReport, ExitCode, Readability, Status
from .normalize import normalize

#: Version of the ``explain --json`` shape. Separate from
#: :data:`power_content_check.model.SCHEMA_VERSION`, which versions the run
#: report: the two outputs answer different questions and a consumer reads one
#: or the other. Within a version every key here is append only, on the same
#: terms ADR 0010 sets for the run report.
EXPLAIN_SCHEMA_VERSION = 1

#: How much of a surface the output quotes before it says it stopped. A label's
#: text layer is a few thousand characters and a terminal is not the place for
#: all of it, but a truncation that is not announced is a smaller document
#: standing in for a larger one, so the full length is always reported beside
#: the excerpt and the cut carries a marker.
SURFACE_CHARS = 2000

#: How much of the document is quoted around a near miss.
SPAN_CHARS = 48

#: How many matches of one pattern are quoted before the output says how many
#: more there were.
MATCH_LIMIT = 5

TRUNCATION_MARKER = " [...truncated]"


class UnknownCheck(LookupError):
    """The identifier named is not in the catalog."""


class Fold(StrEnum):
    """How a phrase is compared against the text.

    SUBSTRING
        The phrase must occur in the surface exactly as written.

    SPACE_INSENSITIVE
        Compared with the spaces removed from both sides. A PDF can draw one
        word as more than one text run, and a subscript does: the issued labels
        set the 2 of CO2e as one, and the extractor reports "CO", a break, then
        "2". See ADR 0006 and
        :func:`power_content_check.normalize.contains_ignoring_spaces`.
    """

    SUBSTRING = "substring"
    SPACE_INSENSITIVE = "space_insensitive"


@dataclass(frozen=True)
class Phrase:
    """A literal a check looks for, and how it compares it."""

    text: str
    fold: Fold
    role: str

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "fold": self.fold.value, "role": self.role}


@dataclass(frozen=True)
class Expression:
    """A regular expression a check matches, quoted as the check writes it."""

    source: str
    role: str

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "role": self.role}


@dataclass(frozen=True)
class ScanPlan:
    """What one check reads and what it looks for in it.

    ``reads`` names surfaces in the order the check consults them. The first is
    the one near miss reporting runs over.
    """

    reads: tuple[str, ...]
    phrases: tuple[Phrase, ...] = ()
    expressions: tuple[Expression, ...] = ()
    fences: tuple[str, ...] = ()
    scanned_nothing: str | None = None

    def __post_init__(self) -> None:
        has_probes = bool(self.phrases or self.expressions)
        if has_probes and self.scanned_nothing is not None:
            raise ValueError("a plan that carries probes cannot also say it scanned nothing")
        if not has_probes and self.scanned_nothing is None:
            raise ValueError("a plan with no probes must say in words what it compared and why")
        if not self.reads:
            raise ValueError("a plan must name the surface it reads")


@dataclass(frozen=True)
class Surface:
    """A body of text a check reads, or the reason there is not one."""

    name: str
    description: str
    text: str | None
    absent_reason: str | None = None

    @property
    def length(self) -> int | None:
        return None if self.text is None else len(self.text)

    def excerpt(self) -> str | None:
        if self.text is None:
            return None
        if len(self.text) <= SURFACE_CHARS:
            return self.text
        return self.text[:SURFACE_CHARS] + TRUNCATION_MARKER

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "characters": self.length,
            "excerpt": self.excerpt(),
            "absent_reason": self.absent_reason,
        }


@dataclass(frozen=True)
class PhraseOutcome:
    """Whether one phrase matched, and where the nearest candidate diverged."""

    phrase: Phrase
    matched: bool
    offset: int | None
    agreed_characters: int
    span: str | None
    document_character: str | None
    phrase_character: str | None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "phrase": self.phrase.to_dict(),
            "matched": self.matched,
            "offset": self.offset,
            "agreed_characters": self.agreed_characters,
            "span": self.span,
            "document_character": self.document_character,
            "phrase_character": self.phrase_character,
            "note": self.note,
        }


@dataclass(frozen=True)
class ExpressionOutcome:
    """What one pattern found. No near miss: see the module docstring."""

    expression: Expression
    matched: bool
    matches: tuple[str, ...]
    total_matches: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression": self.expression.to_dict(),
            "matched": self.matched,
            "matches": list(self.matches),
            "total_matches": self.total_matches,
        }


@dataclass(frozen=True)
class Explanation:
    """Everything ``explain`` has to say about one check on one document."""

    spec: CheckSpec
    document: DocumentReport
    result: CheckResult
    plan: ScanPlan | None
    surfaces: tuple[Surface, ...]
    phrase_outcomes: tuple[PhraseOutcome, ...]
    expression_outcomes: tuple[ExpressionOutcome, ...]

    @property
    def exit_code(self) -> int:
        """The code this one conclusion implies, on the tool's published table."""
        if self.result.status is Status.DOES_NOT_CONFORM:
            return ExitCode.NONCONFORMANCE
        if self.result.status is Status.NOT_EVALUATED:
            return ExitCode.NOT_EVALUATED
        return ExitCode.OK

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EXPLAIN_SCHEMA_VERSION,
            "check": self.spec.to_dict(),
            "document": self.document.to_dict(),
            "result": self.result.to_dict(),
            "exit_code": self.exit_code,
            "scan": None
            if self.plan is None
            else {
                "reads": list(self.plan.reads),
                "fences": list(self.plan.fences),
                "scanned_nothing": self.plan.scanned_nothing,
            },
            "surfaces": [s.to_dict() for s in self.surfaces],
            "phrases": [p.to_dict() for p in self.phrase_outcomes],
            "expressions": [e.to_dict() for e in self.expression_outcomes],
        }


# ---------------------------------------------------------------------------
# near miss
# ---------------------------------------------------------------------------


def _agreement(text: str, phrase: str, offset: int) -> int:
    """How many characters of ``phrase`` the document repeats from ``offset``."""
    agreed = 0
    limit = min(len(phrase), len(text) - offset)
    while agreed < limit and text[offset + agreed] == phrase[agreed]:
        agreed += 1
    return agreed


def _best_prefix(text: str, phrase: str) -> int:
    """Where the document agrees with ``phrase`` for longest.

    Candidate spans are anchored on the phrase's first character, which is the
    ordinary reading of "where does this phrase nearly appear". A phrase whose
    first character never occurs has no candidate span at all, and that is
    reported as such rather than as a run of length zero somewhere arbitrary.
    """
    best_offset = -1
    best_length = 0
    start = text.find(phrase[0])
    while start != -1:
        agreed = _agreement(text, phrase, start)
        if agreed > best_length:
            best_offset, best_length = start, agreed
        if best_length == len(phrase):
            break
        start = text.find(phrase[0], start + 1)
    return best_offset


def _squeezed_offset(text: str, phrase: str) -> int | None:
    """Where a space insensitive match sits in the text as it stands.

    The fold compares with the spaces taken out of both sides, so the string it
    matched exists in neither the document nor the phrase. Reporting the offset
    of that string would point a reader at a position in a text they cannot
    open. This walks it back to the document's own coordinates, so what the
    output quotes is what the extractor produced: "co 2e", space and all.
    """
    positions = [index for index, char in enumerate(text) if char != " "]
    squeezed = "".join(text[index] for index in positions)
    at = squeezed.find(phrase.replace(" ", ""))
    if at < 0:
        return None
    return positions[at]


def _anchor(text: str, phrase: str, fold: Fold) -> int | None:
    """The offset a near miss is read from, or None when there is no candidate.

    A phrase that matched under the space insensitive fold is anchored where
    that fold found it, rather than at whichever equal length prefix the plain
    walk happened to reach first. Otherwise the output would show a reader an
    unrelated span while telling them the phrase matched.
    """
    if fold is Fold.SPACE_INSENSITIVE:
        found = _squeezed_offset(text, phrase)
        if found is not None:
            return found
    offset = _best_prefix(text, phrase)
    return None if offset < 0 else offset


def _matches(text: str, phrase: Phrase) -> bool:
    wanted = normalize(phrase.text)
    if phrase.fold is Fold.SPACE_INSENSITIVE:
        return wanted.replace(" ", "") in text.replace(" ", "")
    return wanted in text


def assess_phrase(text: str, phrase: Phrase) -> PhraseOutcome:
    """Match ``phrase`` under its own fold, and describe the nearest span.

    The match is decided under the fold the check uses. The near miss is always
    read off the surface as it stands, because that is the text a reader can
    look at, and showing the fold's own squeezed form would show a string no
    extractor ever produced.
    """
    wanted = normalize(phrase.text)
    if not wanted:
        return PhraseOutcome(
            phrase=phrase,
            matched=False,
            offset=None,
            agreed_characters=0,
            span=None,
            document_character=None,
            phrase_character=None,
            note="The phrase normalises to the empty string, so nothing was compared.",
        )
    matched = _matches(text, phrase)
    offset = _anchor(text, wanted, phrase.fold)
    if offset is None:
        return PhraseOutcome(
            phrase=phrase,
            matched=matched,
            offset=None,
            agreed_characters=0,
            span=None,
            document_character=None,
            phrase_character=wanted[0],
            note=(
                "No candidate span: the phrase's first character does not occur in "
                "this surface at all."
            ),
        )
    agreed = _agreement(text, wanted, offset)
    span = text[offset : offset + max(agreed, 1) + SPAN_CHARS]
    if len(span) < len(text) - offset:
        span += TRUNCATION_MARKER
    diverged_at = offset + agreed
    return PhraseOutcome(
        phrase=phrase,
        matched=matched,
        offset=offset,
        agreed_characters=agreed,
        span=span,
        document_character=text[diverged_at] if diverged_at < len(text) else None,
        phrase_character=wanted[agreed] if agreed < len(wanted) else None,
        note=None,
    )


def assess_expression(text: str, expression: Expression) -> ExpressionOutcome:
    """Report what a pattern found in ``text``, and how much of it is quoted."""
    pattern = re.compile(expression.source, re.MULTILINE)
    found = [m.group(0) for m in pattern.finditer(text)]
    return ExpressionOutcome(
        expression=expression,
        matched=bool(found),
        matches=tuple(found[:MATCH_LIMIT]),
        total_matches=len(found),
    )


# ---------------------------------------------------------------------------
# surfaces
# ---------------------------------------------------------------------------

SURFACE_DESCRIPTIONS: dict[str, str] = {
    "normalized": "the whole normalised text layer, read as one string",
    "lines": "the normalised text layer, one line at a time, blank lines dropped",
    "cells": "the page read column by column rather than across it (ADR 0008)",
    "domains": (
        "the web addresses found in the raw text, with email addresses removed "
        "before the domain matcher reads it"
    ),
    "raw": "the extracted text before normalisation",
}


def _surface_text(name: str, doc: LabelDocument) -> tuple[str | None, str | None]:
    if name == "normalized":
        return doc.normalized, None
    if name == "lines":
        return "\n".join(doc.normalized_lines), None
    if name == "domains":
        return "\n".join(_domains(doc)), None
    if name == "raw":
        return doc.raw_text, None
    if doc.cells is None:
        return None, (
            "This document carries no recoverable column geometry, so there is no "
            "column reading of it. That is not the same as a reading that found "
            "nothing, and the check treats it as such."
        )
    return "\n".join(doc.cells), None


def surfaces_for(plan: ScanPlan, doc: LabelDocument) -> tuple[Surface, ...]:
    """The bodies of text ``plan`` names, in the order the check reads them."""
    out: list[Surface] = []
    for name in plan.reads:
        text, absent = _surface_text(name, doc)
        out.append(Surface(name, SURFACE_DESCRIPTIONS[name], text, absent))
    return tuple(out)


# ---------------------------------------------------------------------------
# the plans
# ---------------------------------------------------------------------------


def _fuel_phrases() -> tuple[Phrase, ...]:
    required = tuple(
        Phrase(term, Fold.SUBSTRING, f"unconditional fuel type category ({letter})")
        for letter, term in REQUIRED_FUEL_TYPES
    )
    conditional = tuple(
        Phrase(
            term,
            Fold.SUBSTRING,
            f"conditional category ({letter}), qualified 'if applicable' and never "
            "reported as missing",
        )
        for letter, term in CONDITIONAL_FUEL_TYPES
    )
    return required + conditional


def _statewide_phrases() -> tuple[Phrase, ...]:
    return tuple(
        Phrase(rendering, Fold.SPACE_INSENSITIVE, "an accepted rendering; any one of these matches")
        for rendering in STATEWIDE_RENDERINGS
    )


def _group_phrases() -> tuple[Phrase, ...]:
    return tuple(
        Phrase(group, Fold.SUBSTRING, "the annotation must begin with one of these two")
        for group in GROUP_NAMES
    )


def _footnote_plan(lead: str, ordinal: str) -> ScanPlan:
    return ScanPlan(
        reads=("normalized",),
        phrases=(
            Phrase(
                lead,
                Fold.SPACE_INSENSITIVE,
                f"the opening clause of the text section 1393.1(l)({ordinal}) sets out",
            ),
        ),
        fences=(
            "Only the opening clause is compared, not the whole footnote word for word.",
            "Spaces are ignored on both sides, so a subscript or any other split text "
            "run is not read as missing words (ADR 0006).",
        ),
    )


def _plans() -> dict[str, ScanPlan]:
    return {
        "PCL002": ScanPlan(
            reads=("raw",),
            expressions=(Expression(_PHONE.pattern, "a North American telephone number"),),
            fences=(
                "Two distinct numbers are required. Distinctness is decided on the last "
                "ten digits, so one number written two ways counts once.",
            ),
        ),
        "PCL003": ScanPlan(
            reads=("domains", "raw"),
            expressions=(
                Expression(_DOMAIN.pattern, "a web address"),
                Expression(_EMAIL.pattern, "removed from the text before the web matcher reads it"),
            ),
            fences=(
                "An energy.ca.gov address is the Energy Commission's, not the supplier's, "
                "and is excluded from this check's answer.",
            ),
        ),
        "PCL004": ScanPlan(
            reads=("normalized",),
            phrases=(Phrase("energy commission", Fold.SUBSTRING, "the name section 1391 defines"),),
            expressions=(
                Expression(
                    r"\bcec\b",
                    "named in the finding when present, never read as the name",
                ),
            ),
            fences=(
                "The regulation nowhere defines 'CEC', so the abbreviation does not "
                "satisfy this check.",
                "The web address is a separate requirement, checked by PCL005.",
            ),
        ),
        "PCL005": ScanPlan(
            reads=("domains",),
            phrases=(
                Phrase("energy.ca.gov", Fold.SUBSTRING, "the Energy Commission's web address"),
            ),
        ),
        "PCL006": ScanPlan(
            reads=("lines", "normalized"),
            phrases=_fuel_phrases(),
            fences=(
                "A category counts when it begins a row, or when it is followed by a "
                "percentage with no letters in between.",
            ),
        ),
        "PCL007": ScanPlan(
            reads=("normalized",),
            phrases=(
                Phrase(
                    "renewables and zero carbon resources",
                    Fold.SUBSTRING,
                    "the group name of section 1393.1(c)(2)(A)",
                ),
            ),
        ),
        "PCL008": ScanPlan(
            reads=("normalized",),
            expressions=(Expression(r"rps\s+eligible\s+renewables", "the named subcategory"),),
        ),
        "PCL009": ScanPlan(
            reads=("normalized",),
            phrases=(
                Phrase("fossil fuels", Fold.SUBSTRING, "the group name of section 1393.1(c)(2)(B)"),
            ),
        ),
        "PCL010": ScanPlan(
            reads=("normalized",),
            phrases=(
                Phrase(
                    "greenhouse gas emissions intensity",
                    Fold.SUBSTRING,
                    "the disclosure itself; either spelling satisfies it",
                ),
                Phrase(
                    "ghg emissions intensity",
                    Fold.SUBSTRING,
                    "the disclosure itself; either spelling satisfies it",
                ),
                Phrase("CO2e", Fold.SPACE_INSENSITIVE, "the prescribed unit of mass"),
            ),
            expressions=(
                Expression(r"\b(lbs|lb|pounds)\b", "a pounds unit"),
                Expression(
                    r"per\s+megawatt\s+hour|/\s?mwh|per\s+mwh",
                    "a per megawatt hour denominator",
                ),
            ),
            fences=(
                "The disclosure has to be present before its units are read; a document "
                "carrying neither spelling deviates for the disclosure, not the units.",
                "CO2e is compared with spaces ignored, because the issued labels set its "
                "2 as a subscript (ADR 0006).",
            ),
        ),
        "PCL011": ScanPlan(
            reads=("normalized",),
            expressions=(
                Expression(
                    r"retired\s+unbundled\s+recs?|unbundled\s+recs?\s+retired",
                    "the disclosure of retired unbundled RECs",
                ),
            ),
            fences=(
                "A mention of unbundled RECs in the footnote of section 1393.1(l)(1) does "
                "not satisfy section 1393.1(c)(5).",
            ),
        ),
        "PCL012": ScanPlan(
            reads=("normalized",),
            phrases=_group_phrases(),
            expressions=(
                Expression(
                    _UNSPECIFIED_ANNOTATION.pattern,
                    "the annotation, and the words that follow 'primarily'",
                ),
            ),
            fences=(
                "The group name has to begin what follows 'primarily', not merely appear "
                "later on the line.",
                "The published text prescribes no punctuation here, so nothing anchors on "
                "a bracket.",
            ),
        ),
        "PCL013": _footnote_plan(_FOOTNOTE_1_LEAD, "1"),
        "PCL014": _footnote_plan(_FOOTNOTE_2_LEAD, "2"),
        "PCL015": _footnote_plan(_FOOTNOTE_3_LEAD, "3"),
        "PCL016": ScanPlan(
            reads=("normalized", "cells"),
            phrases=_statewide_phrases(),
            fences=(
                "When every word of a rendering is present but not together, the column "
                "reading is consulted; it can turn 'cannot tell' into 'found', and can do "
                "nothing else (ADR 0008).",
                "A rendering that is neither whole in the text layer nor recoverable in a "
                "column is reported as not evaluated, never as absent.",
            ),
        ),
        "PCL017": ScanPlan(
            reads=("normalized",),
            expressions=(Expression(_YEAR_TITLE.pattern, "the year in the title"),),
        ),
        "PCL018": ScanPlan(
            reads=("lines",),
            expressions=(Expression(_TOTAL_ROW.pattern, "a displayed total row"),),
            fences=(
                "The figures are read as decimals, not as doubles.",
                "The displayed total is compared. The rows above it are not added up; see "
                "PCL025 for why.",
            ),
        ),
    }


def plan_for(check_id: str, ctx: CheckContext) -> ScanPlan | None:
    """The scan plan for one implemented check, or None when it enforces nothing.

    PCL001 is the one plan that depends on the run: it compares a name supplied
    on the command line, so without one there is no phrase to show, and the plan
    says so rather than rendering an empty probe list.
    """
    if check_id == "PCL001":
        if not ctx.supplier_name:
            return ScanPlan(
                reads=("normalized",),
                scanned_nothing=(
                    "No supplier name was supplied, so this check compared nothing. Pass "
                    "--supplier-name to give it one. The tool will not guess which line "
                    "of a label is the company name."
                ),
            )
        return ScanPlan(
            reads=("normalized",),
            phrases=(
                Phrase(
                    ctx.supplier_name,
                    Fold.SUBSTRING,
                    "the company name given on the command line",
                ),
            ),
        )
    return _plans().get(check_id)


# ---------------------------------------------------------------------------
# running it
# ---------------------------------------------------------------------------


def find_check(check_id: str) -> RegisteredCheck:
    """The registered check with this identifier, or a refusal naming it."""
    for registered in CHECKS:
        if registered.spec.id == check_id:
            return registered
    raise UnknownCheck(
        f"{check_id} is not a registered check. Run `power-content-check catalog` "
        f"for the {len(CHECKS)} identifiers this ruleset defines."
    )


def explain(
    path: Path,
    check_id: str,
    ctx: CheckContext | None = None,
    min_chars: int = DEFAULT_MIN_TEXT_CHARS,
) -> Explanation:
    """Run one check against one document and report what it read.

    The conclusion comes from :func:`~power_content_check.engine.check_document`
    over a one check registry, so it is the conclusion ``check`` reaches. The
    document is extracted a second time to recover the surfaces, which
    ``check_document`` does not hand back. Extraction is pure and deterministic,
    so the second read is the same document as the first.
    """
    ctx = ctx or CheckContext()
    registered = find_check(check_id)
    report = check_document(path, ctx, min_chars, registry=(registered,))
    result = report.results[0]
    plan = plan_for(check_id, ctx) if registered.spec.implemented else None

    if plan is None or report.readability is Readability.UNREADABLE:
        return Explanation(registered.spec, report, result, plan, (), (), ())

    outcome = extract(path, min_chars=min_chars)
    if not isinstance(outcome, LabelDocument):  # pragma: no cover - readability said otherwise
        return Explanation(registered.spec, report, result, plan, (), (), ())

    surfaces = surfaces_for(plan, outcome)
    primary = surfaces[0].text or ""
    return Explanation(
        spec=registered.spec,
        document=report,
        result=result,
        plan=plan,
        surfaces=surfaces,
        phrase_outcomes=tuple(assess_phrase(primary, p) for p in plan.phrases),
        expression_outcomes=tuple(assess_expression(primary, e) for e in plan.expressions),
    )


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


def _requirement_lines(spec: CheckSpec) -> list[str]:
    lines = [
        "",
        "requirement",
        f"  basis     {spec.basis.value}",
        f"  citation  {spec.citation.source.title}, {spec.citation.locator}",
        f"  quote     {spec.citation.quote}",
        f"  looks for {spec.what_it_looks_for}",
    ]
    if not spec.implemented:
        lines.append(f"  enforces nothing because  {spec.unimplemented_reason}")
        blocker = spec.blocker.value if spec.blocker else "unrecorded"
        lines.append(f"  and that is  {blocker}")
    return lines


def _document_lines(report: DocumentReport) -> list[str]:
    lines = [
        "",
        "document",
        f"  path        {report.path}",
        f"  readability {report.readability.value}",
    ]
    if report.unreadable_reason:
        lines.append(f"  refused     {report.unreadable_reason}")
    lines.append(
        f"  pages {report.page_count}  images {report.image_count}  "
        f"vector shapes {report.vector_shape_count}"
    )
    if report.extraction_basis:
        lines.append(f"  basis       {report.extraction_basis}")
    return lines


def _surface_lines(surfaces: tuple[Surface, ...]) -> list[str]:
    lines = ["", "what the check read"]
    for surface in surfaces:
        lines.append(f"  {surface.name}: {surface.description}")
        if surface.text is None:
            lines.append(f"    not available. {surface.absent_reason}")
            continue
        lines.append(f"    {surface.length} characters")
        lines.append(f"    {surface.excerpt()!r}")
    return lines


def _phrase_lines(outcome: PhraseOutcome) -> list[str]:
    head = "matched" if outcome.matched else "NO MATCH"
    lines = [f"  phrase {outcome.phrase.text!r} [{outcome.phrase.fold.value}]: {head}"]
    lines.append(f"    role: {outcome.phrase.role}")
    if outcome.note:
        lines.append(f"    {outcome.note}")
        return lines
    where = "found at" if outcome.matched else "nearest span at"
    lines.append(
        f"    {where} offset {outcome.offset}, agreeing for "
        f"{outcome.agreed_characters} character(s)"
    )
    lines.append(f"    document has {outcome.span!r}")
    if outcome.phrase_character is not None:
        lines.append(
            f"    diverges at {outcome.phrase_character!r} in the phrase, where the "
            f"document has {outcome.document_character!r}"
        )
    return lines


def _expression_lines(outcome: ExpressionOutcome) -> list[str]:
    head = f"{outcome.total_matches} match(es)" if outcome.matched else "NO MATCH"
    lines = [f"  pattern {outcome.expression.source!r}: {head}"]
    lines.append(f"    role: {outcome.expression.role}")
    for found in outcome.matches:
        lines.append(f"    found {found!r}")
    if outcome.total_matches > len(outcome.matches):
        lines.append(f"    and {outcome.total_matches - len(outcome.matches)} more")
    if not outcome.matched:
        lines.append(
            "    no nearest span is reported: a pattern that finds nothing has no "
            "near miss this tool is entitled to name"
        )
    return lines


def _probe_lines(explanation: Explanation) -> list[str]:
    plan = explanation.plan
    if plan is None:
        return []
    lines = ["", "what the check looked for"]
    if plan.scanned_nothing is not None:
        lines.append(f"  NOTHING COMPARED. {plan.scanned_nothing}")
        return lines
    for phrase_outcome in explanation.phrase_outcomes:
        lines.extend(_phrase_lines(phrase_outcome))
    for expression_outcome in explanation.expression_outcomes:
        lines.extend(_expression_lines(expression_outcome))
    return lines


def _fence_lines(plan: ScanPlan | None) -> list[str]:
    if plan is None or not plan.fences:
        return []
    return ["", "what decided it"] + [f"  {fence}" for fence in plan.fences]


def render_text(explanation: Explanation) -> str:
    """The human rendering. Every value here is also in ``--json``."""
    spec = explanation.spec
    result = explanation.result
    lines = [
        f"{spec.id}  {spec.title}",
        f"  status  {result.status.value}",
        f"  finding {result.finding}",
    ]
    if result.detail:
        lines.append(f"  detail  {result.detail}")
    lines.extend(_requirement_lines(spec))
    lines.extend(_document_lines(explanation.document))
    if explanation.surfaces:
        lines.extend(_surface_lines(explanation.surfaces))
    lines.extend(_probe_lines(explanation))
    lines.extend(_fence_lines(explanation.plan))
    return "\n".join(lines)


def render_json(explanation: Explanation) -> str:
    return json.dumps(explanation.to_dict(), indent=2, sort_keys=True)

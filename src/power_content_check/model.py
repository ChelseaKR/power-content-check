"""Core data types.

Nothing in this module knows how to read a document or how to enforce a rule.
It only describes what a check is, what a result is, and what a report is.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # a cycle at runtime: advisory reads LabelDocument, which reads nothing here
    from .advisory import Advisory
    from .evidence import Evidence


class Status(StrEnum):
    """Outcome of a single check against a single document.

    There is deliberately no "unknown but probably fine" state. Anything the
    tool could not measure is NOT_EVALUATED, which is never treated as a pass.
    """

    CONFORMS = "conforms"
    DOES_NOT_CONFORM = "does_not_conform"
    NOT_EVALUATED = "not_evaluated"


class Basis(StrEnum):
    """Where the requirement a check enforces actually comes from.

    REGULATION_TEXT
        The regulation enumerates the element in words. The check enforces
        what the text says.

    TEMPLATE_FORMAT
        The element is part of the label format the California Energy
        Commission itself issues. Title 20 CCR section 1393.1(i) provides that
        the Energy Commission generates the label or supplies the template and
        that a retail supplier may not alter the format. A check on this basis
        enforces the issued format, not a sentence of regulatory text.
    """

    REGULATION_TEXT = "regulation_text"
    TEMPLATE_FORMAT = "template_format"


class Blocker(StrEnum):
    """Why a registered check enforces nothing, and whether that can change.

    Registering a requirement the tool does not measure keeps the gap visible.
    It also invites the same question to be reopened every time someone reads
    the catalog. This enum answers the question once.

    PERMANENT
        No version of this tool that reads the document it is handed can decide
        the requirement, because the fact it turns on is not in the document,
        or because deciding it would mean inventing a rule the published
        sources do not supply. Reopening it needs a different tool or a changed
        regulation, not more effort here.

    CONDITIONAL
        Blocked on something nameable that could change: a capability this tool
        has chosen not to build, or a document that does not exist yet. The
        reason says what would unblock it.
    """

    PERMANENT = "permanent"
    CONDITIONAL = "conditional"


class Readability(StrEnum):
    READABLE = "readable"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class Source:
    """A published document that a citation points at."""

    key: str
    title: str
    publisher: str
    url: str
    retrieved: str
    effective: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class Citation:
    """The published requirement a check enforces.

    Every check must carry one. A check with no citation cannot be registered.
    """

    source: Source
    locator: str
    quote: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.source.key,
            "source_title": self.source.title,
            "source_url": self.source.url,
            "source_effective": self.source.effective,
            "source_retrieved": self.source.retrieved,
            "locator": self.locator,
            "quote": self.quote,
        }


@dataclass(frozen=True)
class CheckSpec:
    """A registered check.

    ``id`` is stable for the life of the project. It is never renumbered and
    never reused for a different requirement. See tests/test_registry.py, which
    pins the full identifier set.
    """

    id: str
    title: str
    citation: Citation
    basis: Basis
    implemented: bool
    what_it_looks_for: str
    unimplemented_reason: str | None = None
    blocker: Blocker | None = None

    def __post_init__(self) -> None:
        if self.implemented and self.unimplemented_reason is not None:
            raise ValueError(f"{self.id}: implemented check carries an unimplemented reason")
        if self.implemented and self.blocker is not None:
            raise ValueError(f"{self.id}: implemented check carries a blocker")
        if not self.implemented and not self.unimplemented_reason:
            raise ValueError(f"{self.id}: unimplemented check must say why")
        if not self.implemented and self.blocker is None:
            raise ValueError(f"{self.id}: unimplemented check must say whether that is permanent")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "basis": self.basis.value,
            "implemented": self.implemented,
            "what_it_looks_for": self.what_it_looks_for,
            "unimplemented_reason": self.unimplemented_reason,
            "blocker": self.blocker.value if self.blocker else None,
            "citation": self.citation.to_dict(),
        }


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one check against one document."""

    check_id: str
    status: Status
    finding: str
    detail: str | None = None
    #: Where in the document the run this check matched was read from, or None.
    #:
    #: None has three causes and the report does not distinguish them, because
    #: none of them is a claim about the document: evidence collection was off,
    #: nothing was matched (a deviation is the absence of something, and an
    #: absence has no position), or the matched run could not be located. What
    #: it never means is "somewhere else": a locator that cannot find the text
    #: a check matched returns None rather than the nearest thing it can find.
    #:
    #: Excluded from :func:`power_content_check.engine.fingerprint` by
    #: construction -- the fingerprint carries check_id, status and finding, and
    #: nothing else -- so two runs that reached the same conclusions hash the
    #: same whether or not either collected evidence. See ADR 0007.
    evidence: Evidence | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "status": self.status.value,
            "finding": self.finding,
            "detail": self.detail,
            "evidence": None if self.evidence is None else self.evidence.to_dict(),
        }


@dataclass(frozen=True)
class DocumentReport:
    """Everything the tool concluded about one document."""

    path: str
    readability: Readability
    unreadable_reason: str | None
    sha256: str | None
    page_count: int | None
    results: list[CheckResult] = field(default_factory=list)
    #: Raster images the document declares, or None when that is unknown or the
    #: input is plain text. Not a regulatory quantity; it qualifies what an
    #: absence finding is entitled to mean.
    image_count: int | None = None
    #: Times the document paints a vector path, or None when unknown or the
    #: input is plain text. The companion to ``image_count``: what the page
    #: declares beside what the page does. No check reads either. See ADR 0012.
    vector_shape_count: int | None = None
    #: The sentence describing what the tool was able to look at. Reproduced on
    #: the report and appended to every deviation.
    extraction_basis: str | None = None
    #: Things noticed about the document that no published requirement covers.
    #: Not results: they carry no status, are in no count, and reach no exit
    #: code. See :mod:`power_content_check.advisory` and ADR 0013.
    advisories: list[Advisory] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        tally = {status.value: 0 for status in Status}
        for result in self.results:
            tally[result.status.value] += 1
        return tally

    @property
    def has_nonconformance(self) -> bool:
        return any(r.status is Status.DOES_NOT_CONFORM for r in self.results)

    @property
    def has_unevaluated(self) -> bool:
        return any(r.status is Status.NOT_EVALUATED for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "readability": self.readability.value,
            "unreadable_reason": self.unreadable_reason,
            "sha256": self.sha256,
            "page_count": self.page_count,
            "image_count": self.image_count,
            "vector_shape_count": self.vector_shape_count,
            "extraction_basis": self.extraction_basis,
            "counts": self.counts,
            "results": [r.to_dict() for r in self.results],
            "advisories": [a.to_dict() for a in self.advisories],
        }


#: Version of the JSON report's shape, not of the tool and not of the
#: ruleset. Within one version every key is append only; removing a key,
#: renaming one, or changing what a key holds is a breaking change and moves
#: this number. See docs/adr/0010. Pinned by tests/test_report.py, which
#: asserts the exact key sets, so a shape change fails here before it fails
#: for a consumer.
SCHEMA_VERSION = 1

#: Where the published JSON Schemas for this shape live. Held here beside
#: SCHEMA_VERSION rather than in :mod:`power_content_check.schemas`, because a
#: report carries the report schema's id and the schema module reads the model:
#: the other direction would be a cycle. See docs/adr/0010 and schemas/.
SCHEMA_BASE = "https://raw.githubusercontent.com/ChelseaKR/power-content-check/main/schemas"
REPORT_SCHEMA_ID = f"{SCHEMA_BASE}/report-v1.schema.json"
CATALOG_SCHEMA_ID = f"{SCHEMA_BASE}/catalog-v1.schema.json"


class ExitCode:
    """Process exit codes.

    Precedence runs highest first, so a run that both checked nothing and found
    a deviation cannot report the quieter of the two.

    3  Nothing was checked. An empty denominator is never a pass.
    2  At least one check could not be evaluated, including any document the
       tool could not read.
    1  At least one check found a deviation from the prescribed format.
    0  Every document was readable and every implemented check conformed.
    """

    OK = 0
    NONCONFORMANCE = 1
    NOT_EVALUATED = 2
    NOTHING_CHECKED = 3
    USAGE_ERROR = 64


@dataclass(frozen=True)
class RunReport:
    """The result of one invocation."""

    tool: str
    tool_version: str
    ruleset_id: str
    ruleset_effective: str
    generated_at: str
    documents: list[DocumentReport]
    notice: str
    #: Files found inside a directory the caller named that are not a supported
    #: label format, so were not checked. Named rather than dropped in silence,
    #: because the Energy Commission publishes a second rendering of each label
    #: beside it and a reader should be told which file was read. These are not
    #: documents and they are not in any count.
    skipped: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        if not self.documents:
            return ExitCode.NOTHING_CHECKED
        if any(d.readability is Readability.UNREADABLE for d in self.documents):
            return ExitCode.NOT_EVALUATED
        if any(d.has_unevaluated for d in self.documents):
            return ExitCode.NOT_EVALUATED
        if any(d.has_nonconformance for d in self.documents):
            return ExitCode.NONCONFORMANCE
        return ExitCode.OK

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "documents_checked": len(self.documents),
            "documents_readable": sum(
                1 for d in self.documents if d.readability is Readability.READABLE
            ),
            "documents_unreadable": sum(
                1 for d in self.documents if d.readability is Readability.UNREADABLE
            ),
            "conforms": sum(d.counts[Status.CONFORMS.value] for d in self.documents),
            "does_not_conform": sum(
                d.counts[Status.DOES_NOT_CONFORM.value] for d in self.documents
            ),
            "not_evaluated": sum(d.counts[Status.NOT_EVALUATED.value] for d in self.documents),
            # Counted, never scored. An advisory is not a result and this figure
            # sits beside the three that are, rather than among them.
            "advisories": sum(len(d.advisories) for d in self.documents),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            # The contract before the content: a consumer holding only this file
            # can find what it is supposed to satisfy, and validate it.
            "schema": REPORT_SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "tool": self.tool,
            "tool_version": self.tool_version,
            "ruleset_id": self.ruleset_id,
            "ruleset_effective": self.ruleset_effective,
            "generated_at": self.generated_at,
            "notice": self.notice,
            "skipped": list(self.skipped),
            "summary": self.summary,
            "exit_code": self.exit_code,
            "documents": [d.to_dict() for d in self.documents],
        }

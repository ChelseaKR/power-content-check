"""Observations about a label that no published requirement covers.

Calibration turned up facts about real labels that no check can report, because
no requirement addresses them: a prescribed phrase that is present only once the
extractor's spaces are ignored, a data year printed in two places that disagree,
a page carrying no text in a document whose other pages carry plenty. Until now
those lived as prose in ``docs/sources.md``, or as silence in the report.

The README says a finding is a property of a document. So are these, and hiding
them makes the report quieter than the reader's own eyes. This module gives them
a channel, and fences the channel so it cannot become a back door for rules.

The fence, in five parts, each of which is a test in
``tests/test_advisory_channel.py``:

**An advisory is not a result.** :class:`Advisory` is not a
:class:`~power_content_check.model.CheckResult` and cannot be turned into one. It
carries no status, no severity and no citation, because it is not enforcing
anything and a citation would imply it was.

**The code space is closed.** :data:`ADVISORY_CODES` is the whole set. An
unregistered code raises at construction, so a fourth advisory arrives in a diff
with its reasoning beside it rather than as a string somebody passed.

**The observation may not claim a requirement.** The constructor refuses wording
that reads like a rule. An advisory that said a label "must" carry something
would be a check with none of a check's obligations: no citation, no place in
the catalog, no entry in the exit-code table.

**Nothing here reaches an exit code, a status or a fingerprint.** The exit codes
are about conformance and these observations are not conformance. The
fingerprint hashes what the run concluded, and an advisory concludes nothing, so
a baseline recorded before advisories existed stays valid.

**The recorded refusals stay refused.** Summing the fuel mix columns against the
displayed total is not an advisory candidate: PCL025's reason is about the
arithmetic, not about which channel carries it, and routing a refused rule
through a channel that carries no citation would be a way of shipping it without
the argument. See ``docs/adr/0013``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final

from .extract import LabelDocument
from .normalize import contains, contains_ignoring_spaces

#: Every advisory this tool can raise. The set is the channel's whole scope.
ADVISORY_CODES: Final[tuple[str, ...]] = (
    "ADV-BROKEN-PHRASE",
    "ADV-DATA-YEAR-MISMATCH",
    "ADV-TEXTLESS-PAGE",
)

#: Attached to every advisory, by the type rather than by the caller.
#:
#: The issue this channel answers asks that the message state that no published
#: requirement covers what was noticed. Leaving that to whoever writes the
#: observation makes it a habit; putting it on the dataclass makes it a
#: property, and a reader meeting one advisory in a long report gets the same
#: sentence as a reader meeting all three.
NOTICE: Final = (
    "No published requirement covers this observation. It is a description of the "
    "document, not a finding about it, and it is in no count and no exit code."
)

#: Wording an observation may not use, because it would read as a rule.
#:
#: An advisory carries no citation and has no place in the catalog, so an
#: advisory phrased as an obligation is a check with none of a check's
#: obligations. Written as an explicit alternation rather than as a stem match
#: so that the words it refuses can be read off the source.
_CLAIMS_A_REQUIREMENT: Final = re.compile(
    r"\b(must|shall|require|requires|required|requirement|requirements|prohibit|"
    r"prohibited|violate|violates|violation|deviation|deviates|conform|conforms|"
    r"conformance|noncompliant|non-compliant|compliance)\b",
    re.IGNORECASE,
)

#: The year in the title, in the form the issued labels use.
_TITLE_YEAR: Final = re.compile(r"\b((?:19|20)[0-9]{2})\s+power content label\b")

#: A year the document itself labels as the period it covers.
_NAMED_YEAR: Final = re.compile(
    r"\b(?:calendar|reporting|data)\s+year\s*(?:of\s+|:\s*)?((?:19|20)[0-9]{2})\b"
)


class UnregisteredAdvisory(ValueError):
    """A code outside :data:`ADVISORY_CODES`."""


class AdvisoryClaimsARequirement(ValueError):
    """An observation phrased as a rule."""


@dataclass(frozen=True)
class Advisory:
    """One thing noticed about a document that no published requirement covers.

    Three fields, and deliberately none of the fields a result has. ``where``
    locates the observation for a reader and decides nothing, in the same sense
    ADR 0007 uses: position is reported, never acted on.
    """

    code: str
    observation: str
    where: str | None = None

    def __post_init__(self) -> None:
        if self.code not in ADVISORY_CODES:
            raise UnregisteredAdvisory(
                f"{self.code} is not a registered advisory code. The channel's whole "
                f"scope is {', '.join(ADVISORY_CODES)}, and widening it is a diff."
            )
        if not self.observation.strip():
            raise AdvisoryClaimsARequirement(
                f"{self.code} carries no observation, and an advisory with nothing to "
                "say is a line in a report that a reader has to complete themselves"
            )
        claim = _CLAIMS_A_REQUIREMENT.search(self.observation)
        if claim is not None:
            raise AdvisoryClaimsARequirement(
                f"{self.code} says {claim.group(0)!r}, which reads as a rule. An "
                "advisory carries no citation and is in no exit code, so it does not "
                "get to speak like one."
            )

    @property
    def notice(self) -> str:
        return NOTICE

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "observation": self.observation,
            "where": self.where,
            "notice": NOTICE,
        }


# ---------------------------------------------------------------------------
# the observers
# ---------------------------------------------------------------------------


def broken_phrases(doc: LabelDocument) -> list[Advisory]:
    """Prescribed phrases the document carries only once the spaces are ignored.

    ADR 0006 folds those spaces because a page drawing one word as two text runs
    is a fact about the page, not about the words. The fold is right and the
    check that used it reports ``conforms``, which is also right. What was
    missing is that the reader was never told the fold had done anything, and
    that is precisely the signal that separated the two false findings ADR 0006
    records from genuine ones.

    The phrases come from ``explain``'s scan plans, which quote the constants
    the checks themselves match, so this observer keeps no list of its own.
    """
    # Imported here rather than at the top: `explain` reaches the engine, and
    # the engine reaches this module to collect advisories.
    from .checks import CHECKS, CheckContext
    from .explain import Fold, plan_for

    ctx = CheckContext()
    found: list[Advisory] = []
    for registered in CHECKS:
        if not registered.spec.implemented:
            continue
        plan = plan_for(registered.spec.id, ctx)
        if plan is None:  # pragma: no cover - every implemented check has one
            continue
        for phrase in plan.phrases:
            if phrase.fold is not Fold.SPACE_INSENSITIVE:
                continue
            if contains(doc.normalized, phrase.text):
                continue
            if not contains_ignoring_spaces(doc.normalized, phrase.text):
                continue
            found.append(
                Advisory(
                    code="ADV-BROKEN-PHRASE",
                    observation=(
                        f"The text {phrase.text!r} appears in this document only once "
                        "the spaces are taken out of both sides. The extractor read it "
                        "as more than one run, which is what a subscript or a line "
                        "break looks like from outside."
                    ),
                    where=f"read by {registered.spec.id}",
                )
            )
    return found


def data_years(doc: LabelDocument) -> list[Advisory]:
    """Years the document itself names as the period it covers, when they differ.

    Two places, both the document's own: the year in the title, in the form the
    issued labels use, and a year the document labels as its calendar, reporting
    or data year. This says they disagree. It does not say which is right, and
    no published source tells it which.
    """
    years = sorted(
        {match.group(1) for match in _TITLE_YEAR.finditer(doc.normalized)}
        | {match.group(1) for match in _NAMED_YEAR.finditer(doc.normalized)}
    )
    if len(years) < 2:
        return []
    return [
        Advisory(
            code="ADV-DATA-YEAR-MISMATCH",
            observation=(
                f"This document names {len(years)} different years as the period it "
                f"covers: {', '.join(years)}. Which one is intended is not something "
                "the document settles, and this tool does not pick."
            ),
            where="the title and the years the document labels as its own",
        )
    ]


def textless_pages(doc: LabelDocument) -> list[Advisory]:
    """Pages carrying no text in a document whose other pages carry some.

    A document with no text layer at all is refused outright by ADR 0001, and
    that refusal is the whole point of it. One blank page among readable ones is
    not refused, because the checks read the joined text and find what they need;
    but everything drawn on that page is invisible to every check that ran, and
    the report otherwise gives a reader no way to know a page was empty.
    """
    if doc.page_texts is None or len(doc.page_texts) < 2:
        return []
    blank = [n for n, text in enumerate(doc.page_texts, start=1) if not text.strip()]
    if not blank or len(blank) == len(doc.page_texts):
        return []
    plural = "page" if len(blank) == 1 else "pages"
    numbers = ", ".join(str(n) for n in blank)
    return [
        Advisory(
            code="ADV-TEXTLESS-PAGE",
            observation=(
                f"{len(blank)} of this document's {len(doc.page_texts)} pages yielded no "
                "text at all, while the others did. Whatever is drawn there was not read "
                "by anything in this run."
            ),
            where=f"{plural} {numbers}",
        )
    ]


#: Every observer, in the order their advisories are reported.
OBSERVERS: Final = (broken_phrases, data_years, textless_pages)


def observe(doc: LabelDocument) -> list[Advisory]:
    """Every advisory this document raises.

    Deliberately unguarded, which is the opposite of what
    :func:`power_content_check.engine.run_checks` does with a check. That guard
    exists for one reason: a check that crashed must not become a pass. There is
    no pass here to protect, because an advisory is not a status and reaches no
    exit code, so the only thing a ``try`` around this would buy is a bug in a
    descriptive channel disappearing quietly. Quiet disappearance is the failure
    this channel was built to remove, and it would be a poor start to build the
    channel out of it.

    Observers are pure functions over a document that has already been read.
    None of them opens a file or reaches a network, so an exception here is a
    coding mistake, and a coding mistake that stops the run is one that gets
    fixed.
    """
    return [advisory for observer in OBSERVERS for advisory in observer(doc)]

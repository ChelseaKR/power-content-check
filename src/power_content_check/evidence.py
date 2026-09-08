"""Where in the document a finding was read from.

The tool's own rule, applied to itself
--------------------------------------

This project refuses to report a requirement without a citation into the
published text. It did not apply the same rule to its own findings: a
``conforms`` result said the element was found and never said where, so an
auditor checking that PCL004 really saw "Energy Commission" on page 2 had to
re-extract the document and search it by hand. ``docs/AUDITING.md`` asks the
reader to do exactly that.

An ``Evidence`` block is the citation half of a finding: the page a run was
read from, and the normalised run itself, bounded.

The fence from ADR 0007 holds
-----------------------------

**Nothing here can change a status.** Every function in this module takes text
a check has *already matched* and answers where that text sits. It is never
consulted to decide whether something is present, it has no access to any rule,
and a check that has decided nothing passes nothing to it. Position is
recorded, never decided on. ``tests/test_evidence.py`` asserts that a run with
evidence collection off produces byte-identical statuses and an identical
fingerprint.

The one thing that would break that fence is locating a phrase the check never
matched -- evidence that looks like a citation and is a second, weaker search.
So the caller passes the exact text its own matcher produced (a literal it
compared, or ``match.group(0)``), and a locator that cannot find that text
returns ``None`` rather than the nearest thing it can find. A finding with no
evidence says so; it never says somewhere else.

Four ways a run is located, in order
------------------------------------

1. **A normalised line of a page.** The most legible answer for a person: it is
   what the row of the label says, and it names a page.
2. **A window of a page's whole normalised text.** Needed because normalisation
   joins lines, so a phrase can be matched across a line break that no single
   line contains.
3. **A normalised line of the whole document.** Where there are no pages at all
   -- plain-text input -- this is the readable answer, and it is the same rows
   the row-oriented checks read.
4. **A window of the document's normalised text, with no page.** The join of
   every page can contain a run that no individual page does: the last words of
   one page and the first of the next. That is a real match, and the honest page
   for it is ``None``, not a guess.

Plain-text input has no pages at all, so ``page`` is ``None`` there for every
result. ``None`` means "this run cannot be attributed to a page", and is never
written as page 0 or page 1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .normalize import normalize, normalize_lines

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from .extract import LabelDocument

#: Longest run a report will carry, in characters of normalised text.
#:
#: A label is a page of prose and a table; a report that quoted an unbounded run
#: would carry most of the document into every result, and thirty results would
#: carry it thirty times. 200 characters is comfortably more than any row of a
#: power content label and much less than a page of one. A run cut at this
#: length says so -- see :data:`TRUNCATION_MARKER` -- because a quotation
#: silently shortened is a quotation a reader cannot check.
RUN_CAP = 200

#: Appended (or prepended) to a run that was cut at :data:`RUN_CAP`.
TRUNCATION_MARKER = "…"

_WORD_BOUNDARY = re.compile(r"\s")


@dataclass(frozen=True)
class Evidence:
    """Where one matched run was read from.

    ``page`` is 1-based, and is ``None`` whenever the run cannot be attributed
    to a single page: plain-text input, or a phrase that exists only in the
    join of two pages. ``partial`` marks a run that is the nearest thing the
    check *did* find rather than the thing it was looking for -- it is only
    ever set on a deviation, and only when the check itself identified the run.
    """

    page: int | None
    run: str
    truncated: bool = False
    partial: bool = False
    #: Index of the reconstructed column cell the run was found in, when ADR
    #: 0008's column reading is what supplied it. ``None`` otherwise. Cells are
    #: read from the page-joined document, so a cell carries no page of its own.
    cell_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "run": self.run,
            "truncated": self.truncated,
            "partial": self.partial,
            "cell_index": self.cell_index,
        }


def _bounded(text: str) -> tuple[str, bool]:
    """Cut ``text`` to :data:`RUN_CAP`, marking the cut."""
    if len(text) <= RUN_CAP:
        return text, False
    return text[: RUN_CAP - len(TRUNCATION_MARKER)].rstrip() + TRUNCATION_MARKER, True


def _window(haystack: str, start: int, end: int) -> tuple[str, bool]:
    """A readable run of ``haystack`` around ``[start, end)``.

    The matched text is never dropped: if it alone is longer than the cap it is
    the run, truncated and marked. Otherwise the window is widened evenly on
    both sides and snapped outward to whitespace, so a run never begins or ends
    mid-word.
    """
    matched = haystack[start:end]
    if len(matched) >= RUN_CAP:
        return _bounded(matched)
    slack = RUN_CAP - len(matched)
    left = max(0, start - slack // 2)
    right = min(len(haystack), end + (slack - slack // 2))
    while left > 0 and not _WORD_BOUNDARY.match(haystack[left - 1]):
        left -= 1
    while right < len(haystack) and not _WORD_BOUNDARY.match(haystack[right]):
        right += 1
    run = haystack[left:right].strip()
    prefix = TRUNCATION_MARKER if left > 0 else ""
    suffix = TRUNCATION_MARKER if right < len(haystack) else ""
    bounded, cut = _bounded(f"{prefix}{run}{suffix}")
    return bounded, cut or bool(prefix or suffix)


def _squeeze_map(text: str) -> tuple[str, list[int]]:
    """``text`` with spaces removed, and each kept character's original index.

    ``normalize.contains_ignoring_spaces`` matches with spaces stripped from
    both sides, because a PDF can draw one word as several text runs. A run
    located from the squeezed string alone would be unreadable, so the index
    map carries the match back to the text a person can read.
    """
    kept: list[int] = []
    squeezed: list[str] = []
    for index, char in enumerate(text):
        if char != " ":
            squeezed.append(char)
            kept.append(index)
    return "".join(squeezed), kept


def _find(haystack: str, needle: str, *, ignoring_spaces: bool) -> tuple[int, int] | None:
    """Span of ``needle`` in ``haystack``, both already normalised."""
    if not ignoring_spaces:
        index = haystack.find(needle)
        return None if index < 0 else (index, index + len(needle))
    squeezed_haystack, kept = _squeeze_map(haystack)
    squeezed_needle = needle.replace(" ", "")
    if not squeezed_needle:
        return None
    index = squeezed_haystack.find(squeezed_needle)
    if index < 0:
        return None
    return kept[index], kept[index + len(squeezed_needle) - 1] + 1


def locate(
    doc: LabelDocument,
    matched: str,
    *,
    ignoring_spaces: bool = False,
    partial: bool = False,
) -> Evidence | None:
    """Where ``matched`` was read from, or ``None`` if it cannot be found.

    ``matched`` is text the caller's own matcher produced. It is normalised
    here the same way the document was, so a caller may pass either the
    regulation's spelling or the run its regex returned.
    """
    needle = normalize(matched)
    if not needle:
        return None
    for page_number, page_text in enumerate(doc.page_texts or (), start=1):
        for line in normalize_lines(page_text):
            span = _find(line, needle, ignoring_spaces=ignoring_spaces)
            if span is not None:
                run, truncated = _window(line, *span)
                return Evidence(page=page_number, run=run, truncated=truncated, partial=partial)
        page_normalized = normalize(page_text)
        span = _find(page_normalized, needle, ignoring_spaces=ignoring_spaces)
        if span is not None:
            run, truncated = _window(page_normalized, *span)
            return Evidence(page=page_number, run=run, truncated=truncated, partial=partial)
    for line in doc.normalized_lines:
        span = _find(line, needle, ignoring_spaces=ignoring_spaces)
        if span is not None:
            run, truncated = _window(line, *span)
            return Evidence(page=None, run=run, truncated=truncated, partial=partial)
    span = _find(doc.normalized, needle, ignoring_spaces=ignoring_spaces)
    if span is None:
        return None
    run, truncated = _window(doc.normalized, *span)
    return Evidence(page=None, run=run, truncated=truncated, partial=partial)


def locate_in_cell(doc: LabelDocument, matched: str) -> Evidence | None:
    """Where ``matched`` sits in the reconstructed column reading, or ``None``.

    Reached only from PCL016's geometry branch, which is the one use ADR 0007
    leaves open for position. Cells are rebuilt from the whole document rather
    than page by page, so the evidence names the cell and not a page: claiming
    one would be inventing a fact the reconstruction does not hold.
    """
    needle = normalize(matched)
    if not needle or not doc.cells:
        return None
    for index, cell in enumerate(doc.cells):
        normalized_cell = normalize(cell)
        span = _find(normalized_cell, needle, ignoring_spaces=True)
        if span is not None:
            run, truncated = _window(normalized_cell, *span)
            return Evidence(page=None, run=run, truncated=truncated, cell_index=index)
    return None

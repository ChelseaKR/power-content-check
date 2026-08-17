"""Where on the page a string sits, used for one thing and nothing else.

ADR 0007 assessed positional extraction as the way to decide which contact
detail belongs to whom, and refused it. Coordinates say where a string is;
ownership is a different fact, and turning nearness into ownership means
choosing a distance no published source supplies. That record named the one
honest use for position, reconstructing the columns of a table, and this
module is that use.

The rule this module obeys is narrow, and the narrowness is the point:

* Geometry decides which **cell** a word sits in. It never decides who a value
  belongs to and it never decides whether a requirement is met.
* Nothing produced here can become a deviation. The single check that reads it,
  PCL016, consults it only inside the branch that already reports
  NOT_EVALUATED, so the most this module can do is turn "the tool cannot tell"
  into "the tool found it". A test pins that.
* Every failure mode returns ``None``, which puts the caller back exactly where
  it was before this module existed.

Nothing here is a check, nothing here cites the regulation, and no constant in
this file is a regulatory quantity. See ADR 0008.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .normalize import normalize

#: How far apart two lines of one cell may sit, as a multiple of the taller
#: line's font height.
#:
#: This is an engineering constant chosen by this project. It is NOT a
#: regulatory quantity and no check cites it. It exists to keep a cell local:
#: without it, one page-wide line of prose contains every narrower line on the
#: page and the whole document collapses into a single cell.
#:
#: It is not load bearing. Against the published labels this project has read,
#: every value from 1.5 to 6.0 reconstructs the same headings, because the
#: wrapped lines of one heading sit about 1.3 font heights apart and the next
#: thing down the page is far below that. The value sits in the middle of that
#: plateau rather than at either edge of it.
CELL_LINE_SPACING = 2.0

#: Above this many text spans on one page, the page is not reconstructed.
#:
#: Cell membership compares spans against the spans below them, and the vertical
#: window keeps that near linear on any page laid out like a page. A page that
#: puts thousands of spans on one baseline defeats the window, and this is the
#: bound on how long such a page may cost. A one page label carries a couple of
#: hundred spans, so this is far from anything real; it is a stop, not a
#: threshold, and hitting it yields nothing rather than a partial reading.
MAX_SEGMENTS = 2000


@dataclass(frozen=True)
class Segment:
    """One horizontal run of text on one line, and where it sits.

    ``x0`` and ``x1`` are the left and right edges in PDF user space, ``ty`` is
    the baseline. A segment ends where the page leaves a gap wider than the
    space character the document itself draws, which is how a table cell is
    told from the cell beside it without inventing a width for either.
    """

    ty: float
    x0: float
    x1: float
    height: float
    text: str


def _text_runs(page: Any) -> list[Any]:
    """Every text-showing operation on the page, with its position.

    This reaches into pypdf's layout-mode machinery, which is where the
    per-operation transform survives. ``extract_text`` folds those operations
    into one string per line, which is the fold that loses the column, so the
    public entry point cannot answer the question this module is asking.

    Any failure raises, and :func:`page_cells` turns that into ``None``.
    """
    from pypdf._text_extraction._layout_mode._fixed_width_page import (
        recurse_to_target_op,
        resolve_font,
    )
    from pypdf._text_extraction._layout_mode._text_state_manager import (
        TextStateManager,
    )
    from pypdf.generic import ContentStream

    fonts = page._layout_mode_fonts()
    operations = iter(ContentStream(page["/Contents"].get_object(), page.pdf, "bytes").operations)
    state = TextStateManager()
    runs: list[Any] = []
    for operands, operator in operations:
        if operator in (b"BT", b"q"):
            _groups, shown = recurse_to_target_op(
                operations, state, b"ET" if operator == b"BT" else b"Q", fonts, True
            )
            runs.extend(shown)
        elif operator == b"Tf":
            state.set_font(resolve_font(fonts, operands[0]), operands[1])
        else:
            state.set_state_param(operator, operands)
    return [run for run in runs if run.text.strip()]


def _segments(runs: list[Any]) -> list[Segment]:
    """Group text runs into the horizontal spans a reader would see as cells.

    Runs on one baseline are read left to right and joined while they touch.
    A gap wider than one space character of the run about to be placed starts
    a new segment, because the page positioned that text rather than spacing
    into it. The space width comes from the document's own font metrics, so no
    width is invented here.
    """
    lines: dict[float, list[Any]] = {}
    for run in runs:
        lines.setdefault(round(run.ty, 1), []).append(run)

    segments: list[Segment] = []
    for ty, group in lines.items():
        group.sort(key=lambda run: run.tx)
        start = end = height = 0.0
        text = ""
        for run in group:
            right = max(run.tx, run.displaced_tx)
            if text and run.tx - end > max(run.space_tx, 0.0):
                segments.append(Segment(ty, start, end, height, text))
                text = ""
            if not text:
                start, end, height = run.tx, right, run.font_height
            else:
                end = max(end, right)
                height = max(height, run.font_height)
            text += run.text
        if text:
            segments.append(Segment(ty, start, end, height, text))
    return [segment for segment in segments if segment.text.strip()]


def _nests(a: Segment, b: Segment) -> bool:
    """True when one segment's horizontal extent sits inside the other's.

    Containment rather than overlap, and the difference matters. A heading that
    wraps is centred or aligned inside its own column, so its second line sits
    inside the first line's extent, or the first inside the second. A wide line
    that merely reaches into the next column, a supplier's name spanning most of
    the page for instance, overlaps a heading without containing it, and joining
    on overlap glues that heading to its neighbour. Containment needs no
    fraction, no tolerance and no distance.
    """
    return (a.x0 <= b.x0 and b.x1 <= a.x1) or (b.x0 <= a.x0 and a.x1 <= b.x1)


def _cells(segments: list[Segment]) -> list[str]:
    """Join segments into cells and read each one top to bottom.

    Two segments are in the same cell when one's horizontal extent contains the
    other's and they sit within :data:`CELL_LINE_SPACING` of each other. The
    relation is transitive, so a cell of three lines holds together.

    Both ways of getting this wrong are safe. Joining too much reproduces the
    order the text layer already had, which is the answer the caller already
    has. Joining too little loses a match, and a lost match is NOT_EVALUATED,
    which is what the caller already reports.
    """
    ordered = sorted(segments, key=lambda segment: (-segment.ty, segment.x0))
    parent = list(range(len(ordered)))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    tallest = max((segment.height for segment in ordered), default=1.0)
    reach = CELL_LINE_SPACING * max(tallest, 1.0)
    for index, above in enumerate(ordered):
        for other in range(index + 1, len(ordered)):
            below = ordered[other]
            if above.ty - below.ty > reach:
                break
            if above.ty - below.ty > CELL_LINE_SPACING * max(above.height, below.height, 1.0):
                continue
            if not _nests(above, below):
                continue
            root_a, root_b = find(index), find(other)
            if root_a != root_b:
                parent[root_b] = root_a

    grouped: dict[int, list[Segment]] = {}
    for index, segment in enumerate(ordered):
        grouped.setdefault(find(index), []).append(segment)
    return [
        normalize(" ".join(segment.text for segment in members)) for members in grouped.values()
    ]


def page_cells(page: Any) -> tuple[str, ...] | None:
    """The normalised text of each reconstructed cell, or ``None``.

    ``None`` means the page's geometry could not be recovered: an older or
    newer pypdf that no longer exposes the layout machinery, a content stream
    this code cannot walk, anything at all. The caller treats ``None`` as "no
    geometry" and reports exactly what it reported before this module existed.
    """
    try:
        segments = _segments(_text_runs(page))
    except Exception:
        return None
    if not segments or len(segments) > MAX_SEGMENTS:
        return None
    try:
        return tuple(cell for cell in _cells(segments) if cell)
    except Exception:  # pragma: no cover - defensive; _cells has no failing path
        return None


def document_cells(pages: list[Any]) -> tuple[str, ...] | None:
    """Reconstructed cells across every page, or ``None`` if no page yielded any.

    A page whose geometry could not be recovered contributes nothing rather
    than voiding the pages that could, because a cell is a fact about the page
    it came from.
    """
    found: list[str] = []
    for page in pages:
        cells = page_cells(page)
        if cells:
            found.extend(cells)
    return tuple(found) if found else None

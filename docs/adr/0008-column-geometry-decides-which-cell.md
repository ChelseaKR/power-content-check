# 8. Column geometry decides which cell a word is in, and nothing else

Date: 2026-08-17

## Status

accepted

Takes up the one use ADR 0007 left open for position, and repairs the coverage
loss ADR 0006 accepted. Neither record changes.

## Context

ADR 0006 stopped PCL016 from reporting a deviation it could not support. On the
labels the Energy Commission issues, a column heading too long for its column
wraps onto a second line, and text extraction reads across the wrap rather than
down the column, so the words of the heading beside it arrive in the middle of
this one. "CA Utility Average" extracted as "CA Utility Standard Rate Average"
on one label. A document that carries the heading and a document that lacks it
look the same to a substring test, so the check reports NOT_EVALUATED and says
why.

That was the right answer and it cost real coverage. On the eight labels read
at the time, PCL016 went unevaluated on two. Widening the calibration set to
twenty four made the size of the loss clearer: seven of twenty four, a little
under a third of every label read.

ADR 0007 refused positional extraction for attribution and named the honest
alternative in one sentence: "If it gets built for another reason, column
reconstruction is the honest use for it, not attribution." This is that other
reason, and this record is what holds the build to that sentence.

The danger is obvious and it is the danger this whole project is organised
around. Geometry is a rich signal, and a rich signal invites a tool to say more
than it knows about a document published by a named organisation.

## Decision

`geometry.py` reconstructs the cells of a page. Four things fence it in.

**One: it decides cell membership and nothing else.** A cell is a set of text
segments. The module does not decide who a value belongs to, does not decide
whether a requirement is met, and produces no status. It hands back strings.

**Two: no check can turn it into a deviation.** PCL016 reads it from one place,
`_in_a_reconstructed_cell`, and that helper is reached only from the branch that
already returns NOT_EVALUATED. A document whose text layer does not carry the
words at all is reported as deviating before geometry is consulted at all. So
the most this module can do is turn "the tool cannot tell" into "the tool found
it". `tests/test_geometry.py` pins that both ways: by planting a cell that
spells the rendering into a document that lacks the words and asserting the
deviation stands, and by reading the catalog's own source to assert that one
function reads the field.

**Three: the joins are geometric, not numeric.** Two things are decided.

- *Where a segment ends.* A run of text ends a segment when the gap to the next
  run is wider than one space character in the font the page is about to draw
  with. The width of that space is the document's own font metric. No width is
  invented.

- *Which segments are one cell.* Two segments are one cell when one's
  horizontal extent contains the other's. Containment, not overlap. A heading
  that wraps sits inside its own column, so its second line falls inside the
  first line's extent. A wide line that merely reaches into the next column, a
  supplier's name spanning most of the page for instance, overlaps a heading
  without containing it. Joining on overlap glued that name to the heading
  beside it on one of the twenty four labels and reproduced the interleaving
  this exists to undo. Containment needs no fraction, no tolerance and no
  distance, which is the objection that keeps PCL021 and PCL025 permanent.

**Four: one constant, named as one.** Containment alone is transitive and any
page-wide line of prose contains every narrower line on the page, so the whole
document collapses into a single cell. A cell has to be local. `CELL_LINE_SPACING`
is 2.0 and means "two lines of one cell sit within twice the taller one's font
height". It is an engineering constant, no check cites it, and it is not load
bearing: every value from 1.5 to 6.0 reconstructs the same headings across the
twenty four labels, because the wrapped lines of one heading sit about 1.3 font
heights apart and the next thing down the page is far below that. A test
exercises the plateau rather than asserting it in prose.

**Failing.** Every failure returns `None` and the caller reports exactly what it
reported before this module existed. The positional data comes from inside
pypdf rather than from its public surface, because the public entry point folds
each line into one string, which is the fold that loses the column. A version
bump can therefore take the capability away. It cannot make the tool wrong; it
can only make PCL016 go quiet again, which is the safe failure and also the
silent one, so a test asserts that a real PDF still yields positioned text.

A page carrying more than `MAX_SEGMENTS` text spans is not reconstructed at all.
Cell membership compares spans against the spans below them, and the vertical
window above keeps that near linear on any page laid out like a page; a page
that puts thousands of spans on one baseline defeats the window. The stop is a
bound on how long a hostile document may cost, not a rule about labels: a one
page label carries a couple of hundred spans, and hitting the stop yields
nothing rather than a partial reading.

## Consequences

PCL016 is evaluated on all twenty four published labels this project has read,
where before it was unevaluated on seven of them. The implemented count is
unchanged at eighteen. Nothing here added a check; one check stopped losing
documents, which the count does not show.

The tool does more work per document. Cells are reconstructed for every PDF
whether or not PCL016 needs them, which costs tens of milliseconds on a one page
label. Making it lazy would mean carrying a live page object on
`LabelDocument`, and a document that is data is worth more than the
milliseconds.

Reading a page column by column now exists in the tree, and the next person who
wants it for something else will find it. The fence above is what they have to
answer, and the fence is deliberately about what the output may be used for
rather than about how good the reconstruction is. PCL021 is still permanent and
this record does not reopen it: better cell reconstruction does not tell anyone
whose telephone number is whose.

Both ways of reconstructing wrongly are safe by construction. Joining too much
reproduces the reading order the text layer already had, which is the answer the
caller already has. Joining too little loses a match, and a lost match is
NOT_EVALUATED, which is what the caller already reports.

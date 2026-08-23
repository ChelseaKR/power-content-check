# 11. A scanned label fails closed rather than getting guessed at

Date: 2026-08-22

## Status

accepted

Refuses optical character recognition for this tool, and records the refusal
so it is a decision rather than an omission to be re-raised.

## Context

Extraction reads a PDF's text layer. A scanned label has none: the page is
one picture of text, the extractor returns an empty string, and
`extract.py` treats that as unreadable. Every check reports not evaluated,
the run cannot exit 0, and the report says why in the extraction basis.
`tests/test_fail_closed.py` proves the collision with "nothing wrong" is
refused by construction.

The obvious offer is OCR: run the picture through recognition and check the
text it produces. It would convert some unread documents into checked ones,
which sounds like coverage and is the direction expansion is supposed to go.

It is not coverage, for three reasons that do not depend on how good any
particular recognizer is.

**One: it puts a probabilistic layer inside a deterministic tool.** The
product here is that the same document yields the same findings forever,
and that every finding traces to something the document actually contains.
A recognizer's output is a model's guess at the text. Its errors are
plausible strings that were never on the page, and its confidence scores
say nothing about which guesses mattered. Every finding downstream would
carry that guess inside it while presenting exactly as a finding about the
document.

**Two: errors land in the dangerous direction.** This tool can be wrong in
two ways: it reports a deviation for an element the document carries (false
accusal), or it misses one (false comfort). Recognition errors produce both
today - "lbs" read as "1bs" fails PCL010's unit test; "Energy Commission"
read as "Energy Cornmission" fails PCL004 - and neither failure looks
different from an honest reading. The fail-closed path, whatever it costs
in coverage, never accuses a document of anything on the strength of a
guess.

**Three: attribution.** A finding from this tool is entitled to say "this
text layer lacks the phrase". A finding from recognized text would have to
say "a model believes this picture says", and this project will not attach
its name to the first sentence while meaning the second. The calibration
record faced the same question about artwork and answered it the same way:
where extraction could not see, a human rendered the page and looked.

## Decision

No OCR path in this tool. A document without a text layer is unreadable,
loudly, and stays that way.

If a future need ever justifies reopening this - it has not so far - the
bar is written down now: recognition whose per-character reliability is
bounded and evidenced, run as a separately labelled mode that never mixes
with text-layer results, carrying its own extraction basis wording ("basis:
text as recognized from a picture, which may differ from the document") on
every finding, and gated behind an explicit flag so no caller receives
recognized text while expecting extracted text. Anything less re-opens the
collision this project exists to refuse.

## Consequences

Scanned labels remain unchecked rather than mischecked, and the catalog's
not-evaluated counts stay honest about what was measured.

The artwork documentation (`docs/sources.md`) remains the procedure for a
human who needs to know what an unreadable-looking label carries: enumerate,
measure, render, look.

Nothing else changes. No check, constant or threshold moves.

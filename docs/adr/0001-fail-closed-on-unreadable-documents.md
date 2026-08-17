# 1. Fail closed on unreadable documents

Date: 2026-08-17

## Status

accepted

## Context

The tool reads published labels, most of which are PDFs. Several ordinary
inputs yield no text at all:

- a scanned label, which is an image with no text layer
- an encrypted PDF
- a corrupt or truncated file
- a file that is not a PDF despite its name
- a path that does not exist

Every one of these produces an empty string from a text extractor. So does a
document that has been read perfectly and simply has nothing wrong with it, if
you only look at the count of findings. A checker that runs its rules over an
empty string finds no deviations and, without care, reports the document as
clean.

That is not hypothetical. Exactly this defect, an unreadable document reported
as conforming, was found in a sibling project. The cost of the mistake is high
here in particular: the output is a statement about a named organisation's
published document, and "we found nothing wrong" reads as an endorsement.

The same reasoning applies at the level of a run rather than a document. A run
over zero documents also produces zero findings.

## Decision

Unreadability is decided in one place, `extract.py`, and decided
pessimistically.

1. Extraction returns either a `LabelDocument` or an `UnreadableDocument`. The
   existence of a `LabelDocument` instance is the proof that reading succeeded.
   Checks take a `LabelDocument`, so a check cannot run against a document that
   was never read.

2. `extract()` never raises. Every failure mode returns an
   `UnreadableDocument` with a written reason, because an exception that some
   caller catches loosely is one refactor away from becoming a silent pass.

3. A PDF whose text layer yields fewer than a threshold number of characters is
   unreadable, not sparse. The threshold is an engineering choice, is named as
   such, is configurable, and is cited by no check.

4. An unreadable document produces a not-evaluated result for **every**
   registered check, not an empty result list. An empty list renders as
   "nothing wrong".

5. A check that raises becomes not evaluated, carrying the exception type. It
   never becomes a pass.

6. Exit codes are ordered so that quieter outcomes cannot mask louder ones:
   3 nothing checked, 2 something not evaluated, 1 a deviation, 0 clean. A run
   with an unreadable document cannot exit 0.

7. Zero documents is exit 3 and the words `NOTHING CHECKED`. An empty
   denominator is never a pass.

## Consequences

The property is testable as a hash comparison, and is tested that way in
`tests/test_fail_closed.py`: the tool's conclusions for an unreadable input and
for a clean input must not hash the same. The hash excludes file paths,
timestamps and the tool version, so it compares conclusions rather than inputs.

Exit code 2 becomes the ordinary result for a well formed label, because the
registered checks that enforce nothing always report as not evaluated. Callers
who want "no deviations found" should test for zero `does_not_conform` results
rather than for exit code 0. The README says so.

Some genuinely readable documents will be refused, for instance a real label
that is unusually short. Refusing to judge is the cheaper error.

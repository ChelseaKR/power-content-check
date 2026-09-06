# 13. An advisory channel, fenced off from the rules

Date: 2026-09-06

## Status

Accepted.

## Context

This tool reports only against published requirements. Every check cites one,
and a requirement the tool cannot measure is registered with a reason rather
than dropped (ADR 0002). That discipline is the reason the output is worth
anything.

It also means the tool has been silent about things the calibration set kept
turning up, none of which any requirement addresses:

* a prescribed phrase present in a document only once the extractor's spaces are
  taken out of both sides, which is the fold ADR 0006 introduced and the signal
  that separated its two false findings from genuine ones;
* a data year printed in two places on the same label that disagree;
* a page with no text layer at all in a document whose other pages have one.

Each was noticed by a person reading a label, written into `docs/sources.md` as
prose, and then absent from every report the tool produced. The README says a
finding is a property of a document. So are these, and a report that omits them
is quieter than the reader's own eyes.

The obvious way to surface them is to register checks for them. That is the
wrong way, and the reason is the first paragraph: a check cites a published
requirement, and there is no requirement to cite. A check with an invented
citation would be worse than the silence.

## Decision

A second channel, structurally unable to be the first.

`power_content_check.advisory.Advisory` carries a code, an observation and an
optional `where`. It carries no status, no severity and no citation, and it is
not a `CheckResult`. `ADVISORY_CODES` is closed: `ADV-BROKEN-PHRASE`,
`ADV-DATA-YEAR-MISMATCH`, `ADV-TEXTLESS-PAGE`. An unregistered code raises at
construction, so a fourth advisory arrives in a diff with its reasoning next to
it.

The constructor refuses an observation phrased as a rule. An advisory that said
a label "must" carry something would be a check with none of a check's
obligations, and the refusal makes that a build failure rather than a review
note.

Every advisory carries the same notice, attached by the type rather than written
by whoever raised it: no published requirement covers the observation, it is in
no count, and it is in no exit code.

Nothing here reaches a status, an exit code or a fingerprint. `RunReport.summary`
gains an `advisories` figure, printed beside the three status counts and never
among them. `engine.fingerprint` hashes what the run concluded, and an advisory
concludes nothing, so a regression baseline recorded before this existed stays
valid.

The report renders advisories in their own section and does not hide them behind
`--verbose`. An advisory that only appeared when the reader already suspected
something would be no better than the prose it replaces.

`advisory.observe` is deliberately unguarded, which is the opposite of what
`engine.run_checks` does with a check. That guard exists so a crashing check
cannot become a pass. There is no pass here to protect, so a `try` would buy
only the quiet disappearance of a bug, and quiet disappearance is the failure
this channel exists to remove.

## Consequences

The JSON report gains an `advisories` array on each document and an `advisories`
figure in the summary. Both are additions, so `SCHEMA_VERSION` stays at 1: ADR
0010 makes the shape append only within a version, and nothing here removes a
key, renames one, or changes what a key holds. `tests/test_report.py` pins the
exact key sets, so the addition is asserted rather than assumed.

`ADV-BROKEN-PHRASE` reads its phrases from `explain`'s scan plans, which quote
the constants the checks themselves match. The channel keeps no list of its own,
and the two bindings in `tests/test_explain.py` that hold those plans to
`checks.py` therefore hold this too.

The recorded refusals stay refused. Summing the fuel mix columns against the
displayed total is not an advisory candidate. PCL025's reason is about the
arithmetic, not about which channel carries it, and routing a refused rule
through a channel that carries no citation would be a way of shipping it without
the argument. The same goes for anything in ROADMAP.md's Refusals list: a
refusal is a decision about the statement, and the statement does not change by
being printed under a different heading.

What this does not do: it does not widen what the tool enforces, it cannot make
a run fail, and it cannot make a run pass. A reader who ignores the whole section
gets exactly the report they got before.

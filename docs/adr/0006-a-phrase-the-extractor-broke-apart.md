# 6. A phrase the extractor broke apart is not a phrase the label lacks

Date: 2026-08-17

## Status

accepted

## Context

ADR 0003 settled a question against three published 2024 labels: the two
deviations the tool reported on all three, no telephone number and no words
"Energy Commission", are properties of the documents rather than artefacts of
text extraction. Three labels is a small calibration set to rest a conclusion
on, so five more were fetched: the third of the three investor owned utilities,
a second large municipal utility, a community choice aggregator, an electric
service provider, and a rural cooperative. Eight in total.

The two deviations held on all eight. That is the good half of the result.

The other half is that the wider set produced three deviations that were
false. On one label the footnote prescribed by section 1393.1(l)(2) was
reported absent, and on two labels the separate statewide disclosure required
by section 1393.1(a) was reported absent. All three elements are plainly on
the page. Each label was rendered and looked at to confirm it.

Both failures are the same failure in two costumes: the tool compared a
prescribed phrase against a text layer, and the text layer had the phrase in
it, broken.

**A subscript breaks a word.** The issued labels set the 2 of CO2 as a
subscript. A subscript is a separate text run, so the extractor reports "CO",
a break, then "2", and normalisation turns the break into a space. The
footnote is present, verbatim, and the check missed it by one space.

**A wrapped column heading breaks a phrase.** A heading too long for its
column wraps onto a second line. Extraction reads across the wrap rather than
down the column, so the second line of the heading beside it arrives in the
middle of this one. "CA Utility Average" extracts as "CA Utility Power Mix
Average" on one label and "CA Utility Standard Rate Average" on another. The
heading is present, and the words of the neighbouring column are inside it.

Neither is a property of anyone's label. Both were reported against named
suppliers, which is the harm ADR 0003 exists to prevent, arriving through a
door ADR 0003 did not cover: not content hidden in a picture, but content the
extractor handed over in pieces.

## Decision

The two cases get different answers, because the evidence supports deciding
one and refuses to decide the other.

**Where the split is in the spaces, ignore the spaces.**
`normalize.contains_ignoring_spaces` compares a prescribed phrase against the
document with every space removed on both sides. Where the extractor put its
spaces is a fact about how the page was drawn, not about the words the document
contains. The three footnote checks, PCL013 to PCL015, and the statewide
rendering match in PCL016 use it. Like everything in `normalize`, it only
widens matching, and it does not ignore intervening words: "CA Utility Power
Mix Average" still does not match "CA Utility Average".

**Where the split has other words in it, report neither.** PCL016 now reports
NOT_EVALUATED when every word of an accepted rendering appears but the
rendering does not, and says so in the finding. A document carrying a wrapped
heading and a document missing the heading look the same to a substring test.
The tool is not entitled to pick the accusing one, and the alternative,
allowing some number of intervening words, is a threshold no published source
supplies. NOT_EVALUATED is never a pass and the run still cannot exit 0 on it.

## Consequences

Every one of the eight published labels now reports the same two deviations
and no others, which is what a tool measuring the issued format should do.

PCL016 reports not evaluated on two of the eight. That is a real loss of
coverage and it is the honest one: on those two documents the tool cannot tell
the two explanations apart.

The implemented count is unchanged at eighteen. Nothing here added a check.
Two checks stopped being wrong, which the count does not show, and which is the
limitation of counting checks.

Widening the calibration set is how both of these were found. Three labels
agreed with each other and were wrong together about nothing; eight labels
disagreed enough to expose two bugs. A future reader adding a check should
expect the same, and `scripts/fetch_examples.py` caps itself at five documents
per run for a reason unrelated to that: the cap is about not collecting a
corpus, not about how many labels are enough to trust a conclusion.

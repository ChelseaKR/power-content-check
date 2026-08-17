# 4. One ruleset, and the vintage it fits

Date: 2026-08-17

## Status

accepted

## Context

The tool encodes one ruleset, `ccr-t20-art5@2025-06-18`, and prints its
effective date on every report. It was not established whether that ruleset is
the right one for a label whose data year is 2024. If it is not, every finding
against a 2024 label is measured against a rule that was not in force.

Two dates settle it.

**When the regulations took effect.** The Power Source Disclosure regulations
this tool cites were docketed by the Energy Commission under 21-OIR-01 and are
described by the publisher as effective June 18, 2025.

**When a 2024-data-year label is published.** Section 1393.1(a) scopes a label
to the previous calendar year, and section 1393.1(b)(2) requires the label to
be provided to the Energy Commission by October 1 of each year. A label whose
data year is 2024 is therefore the disclosure due October 1, 2025, which falls
after the effective date.

That is the argument from the text. The three published 2024 labels this
project read agree with it as a matter of fact: each carries a PDF creation
timestamp in September 2025, and each names the California Energy Commission as
its author. They were generated under the ruleset the tool encodes.

The same two dates dispose of the opposite worry, that the tool might be
enforcing rules ahead of their time. Several provisions in this ruleset begin
January 1, 2026, or "in 2026". A label generated in September 2025 was not
subject to them. Those provisions are PCL023 and PCL024, and both are
registered as enforcing nothing.

## Decision

No ruleset version switching. The tool encodes one ruleset and names it.

The report keeps printing `ruleset_id` and `ruleset_effective`, so a reader
checking a label from some other year can see immediately what it was measured
against and decide for themselves.

`docs/sources.md` records the effective date, the docket number, and the
reasoning above, so the question does not have to be reopened from scratch.

## Consequences

For a data year 2024 label, which is what the Energy Commission currently
publishes, the ruleset is the right one and there is nothing to switch between.

For an older label, say one from a data year before 2024, the tool will measure
against a ruleset that came later. It will not warn about this, because it
cannot: a data year is not a publication date, and a document that says 2019 on
it may have been reissued at any time. The printed effective date is what a
reader has, and it is enough to notice the mismatch.

If the regulations are amended, the honest response is a second ruleset with
its own identifier and effective date, chosen explicitly by the caller. Adding
that machinery now, with one ruleset in existence and no second one to switch
to, would be building a mechanism whose correctness nothing could test.

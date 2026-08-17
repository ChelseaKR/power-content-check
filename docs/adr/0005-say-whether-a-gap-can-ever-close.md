# 5. Say whether a registered gap can ever close

Date: 2026-08-17

## Status

accepted

Amends ADR 0002, which decided that requirements the tool does not enforce are
registered anyway with a written reason. It stands. This adds one field to it.

## Context

Registering a requirement the tool does not measure keeps the gap visible. It
also leaves an open question sitting in the catalog. A reader who works through
twelve reasons cannot tell which of them are waiting for someone to do the
work, and which of them are closed for good.

That is not an academic distinction. Reopening a settled question costs the
same effort every time it is reopened, and the reasons are written to be read
once, not reasoned through again.

Two of them turned out to be worth restating after the regulation was reread
against real labels.

**PCL025, the column arithmetic.** The original reason was that extracted text
loses column boundaries, so a mis-parsed column could produce a false finding.
That reason is true but it is the smaller one, and it sounds like something
better parsing would fix. The real obstacle is arithmetic. The label displays
whole percentages, and neither the regulation nor the issued format prescribes
a rounding rule or a tolerance, so a column's components need not add to the
total the label displays. On the three published 2024 labels this project read,
eight of the fourteen columns summed to 99 or 101 against a displayed total of
100, including, on all three, the statewide column the Energy Commission itself
supplies under section 1393.1(a)(3). An equality test would report a deviation
for correctly rounded arithmetic, against named suppliers, on a column those
suppliers did not compute. Any tolerance that suppressed it would be a
threshold this tool invented. Better parsing does not help with that.

**PCL023 and PCL024, the 2026 trigger.** The original reason was that the text
does not settle whether the trigger attaches to a label's publication date or
to its data year. Reading the section settles that much: subdivision (c) places
the obligation on the supplier's act of disclosure, and subdivision (b)(2)
dates that act to October 1 of each year. What does not follow is a way to
apply it, because a label states its data year and not the date it was
disclosed. The ambiguity moved from the regulation to the document.

## Decision

Every unimplemented check carries a `Blocker`, and `CheckSpec.__post_init__`
refuses to construct one without it.

- **PERMANENT**: no version of this tool that reads the document it is handed
  can decide the requirement, because the fact it turns on is not in the
  document, or because deciding it would mean inventing a rule no published
  source supplies. Currently PCL019, PCL020, PCL022, PCL025, PCL026, PCL027,
  PCL028, PCL030.

- **CONDITIONAL**: blocked on something nameable that could change, and the
  reason says what. Currently PCL021, blocked on positional extraction this
  tool has not built; PCL023 and PCL024, blocked on a document that states the
  date the trigger turns on; PCL029, blocked on the issued template carrying a
  fixed rendering of a statement the regulation describes but does not word.

The classification is printed by `power-content-check catalog` and carried in
its JSON. `tests/test_registry.py` pins the permanent set, so moving an
identifier out of it is a deliberate act in a diff with the reason rewritten.

Two requirements that had no entry at all were registered while doing this:
PCL029 for section 1393.1(c)(6), and PCL030 for the third resource group in
section 1393.1(c)(2)(C), whose siblings (A) and (B) both have checks. Silence
about a requirement is the thing ADR 0002 exists to prevent.

## Consequences

The count of registered checks goes from 28 to 30 and the unimplemented count
from 10 to 12. Neither number is a measure of coverage and nothing presents
them as one. The implemented count is unchanged at 18, which is the point:
registering a requirement is not the same as enforcing it, and finding two more
gaps did not close any.

A reader can now answer "why has nobody built this yet" from the catalog alone.

The word "permanent" is a strong claim and is meant to be. It says that no
amount of effort on this tool closes the gap. If that turns out to be wrong for
some check, the pinned set is the place the argument has to be had.

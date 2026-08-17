# 7. Position does not decide who a contact detail belongs to

Date: 2026-08-17

## Status

accepted

Amends ADR 0005, which classified every unimplemented check as permanent or
conditional. That decision stands. This moves one identifier between the two
classes and says why.

## Context

Section 1393.1(c)(4) requires six things: the retail supplier's company name,
phone number and website address, and the name, phone number and website
address of the Energy Commission. PCL001 to PCL005 check for those elements.
None of them checks attribution, which is the further question of which
telephone number belongs to whom and which web address belongs to whom.

PCL021 held that question, registered and enforcing nothing, classified
CONDITIONAL, with positional extraction named as the capability that would
unblock it. Reading where on the page each string sits, the reason said, would
settle it.

It would not.

**Position is a fact the tool can get. Ownership is a different fact.**
Coordinates say a string is here and a name is there. Turning "near" into
"belongs to" means choosing how near counts, and no published source supplies
a distance. That is the same objection that keeps PCL025 permanent: a threshold
this tool invented, applied to someone else's document.

**On the issued format there is nothing to attribute.** Across the eight
published 2024 labels this project has now read, no telephone number appears
anywhere, so the phone half of the requirement has no strings to assign. Each
label carries exactly two web addresses. Which one is the Energy Commission's
follows from its domain, and PCL003 and PCL005 already decide that without
reading a single coordinate. The attribution the document actually supports is
already implemented; what PCL021 would add is attribution the document does not
supply.

**A wrong answer names a supplier.** On these labels the supplier's own web
address sits in a cell with no caption at all, and the Energy Commission's sits
under the words "Want to learn more? Visit". A positional rule would have to
lean on where those two cells usually are. The regulation does not fix their
positions, and a label that swapped them would draw a finding that the
supplier's website address is missing. That is a false finding against a named
utility, produced by the tool's own convention. It is the exact harm this
project is built to refuse.

There is a residual case: a label that prints an owner's name beside a contact
detail. Attribution would then be readable, and would be readable from the
text, not from the geometry. That is the same shape as PCL020, which is already
permanent: presence of the fact on some document does not make the requirement
decidable, because a document that does not state it leaves the tool guessing,
and guessing is the thing being refused.

## Decision

PCL021 is PERMANENT. Its reason says that position was assessed and does not
settle attribution, that the fact is missing from the document rather than from
the tool, and that a proximity rule which guessed wrong would attribute a
contact detail to a named supplier.

The permanent set pinned in `tests/test_registry.py` goes from eight
identifiers to nine. Conditional goes from four to three: PCL023 and PCL024,
blocked on a label from data year 2025 or later, and PCL029, blocked on an
issued template that carries a fixed rendering of the section 1393.1(c)(6)
statement. Eight labels and four of the alternative renderings published beside
them were read while doing this, and none carries such a statement, so that
template does not exist in the 2024 vintage either.

## Consequences

Nobody has to build positional extraction to close PCL021, and nobody should
build it expecting to. If it gets built for another reason, column
reconstruction is the honest use for it, not attribution.

Nine permanent classifications is a strong claim made nine times. The pinned
set is where the argument has to happen, and this record is what moving PCL021
out of it would have to answer.

The other eight permanent classifications were reread against the regulation
text while making this one, and against the wider label set. Three reasons were
sharpened and none changed class. PCL019 now says that the published text
nowhere equates "one place" with one page. PCL020 now says that presence is
visible and absence is not, and that a check which could only ever confirm was
considered and refused. PCL022 now records that the second file the Energy
Commission publishes beside each label is an alternative rendering of the same
label, not the annual resource report the consistency is measured against.

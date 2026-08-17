# 2. Register requirements the tool does not enforce

Date: 2026-08-17

## Status

accepted

## Context

Section 1393.1 contains requirements this tool cannot check. Some need a second
document, such as the supplier's annual resource report. Some turn on a fact
about the supplier's business rather than about the label, such as whether any
customer is served by more than one portfolio. Some turn on a 2026 trigger date
whose applicability the published text does not settle. One is an arithmetic
check that could be attempted, but where a mis-parsed table column would
produce a false finding against a named organisation.

The convenient thing is to leave these out of the catalog. The catalog then
looks complete, every registered check passes, and the gap is communicated by
nothing at all.

That is a form of overclaiming. A reader who sees eighteen checks pass has no
way to learn that ten requirements were never looked at.

## Decision

Requirements the tool does not enforce are registered anyway, with
`implemented=False`, a citation to the source like any other check, and a
written reason.

They appear in every report as not evaluated. They appear in
`power-content-check catalog` marked "REGISTERED, ENFORCES NOTHING".

The reason must be specific. "Not implemented yet" is not a reason. "Whether
any customer is served by a mixture of portfolios is a fact about the
supplier's service, not about the document" is.

`CheckSpec.__post_init__` refuses to construct an unimplemented check with no
reason, and refuses to construct an implemented check that carries one.

## Consequences

The gap between what the regulation requires and what this tool measures is
visible in the tool's own output, not only in prose that a reader may not
reach.

A well formed label exits 2 rather than 0. That is the honest number.

The count of registered checks is not a measure of coverage, and nothing in the
project presents it as one.

If the ambiguity behind PCL023 and PCL024 is later resolved by a published
source, those two become implemented without a renumbering, because they
already hold their identifiers.

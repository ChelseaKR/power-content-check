# 0. Record architecture decisions

Date: 2026-08-17

## Status

accepted

## Context

This project makes a claim about whether a document conforms to a published
requirement. The decisions that shape that claim, what counts as a source, what
happens when a document cannot be read, which requirements are deliberately not
enforced, are the substance of the tool, not implementation detail. A reader
who wants to trust an output needs to be able to find out why it works the way
it does.

Decisions of that kind are easy to lose. They get made once, encoded in a
function, and then reconstructed incorrectly by whoever reads the function next.

## Decision

Architecture decisions are recorded here as numbered Markdown files, in the
style described by Michael Nygard in "Documenting Architecture Decisions".

Each record is immutable once accepted. A decision that no longer holds is
superseded by a new record, and the old one is marked superseded rather than
edited or deleted, so that the reasoning history survives.

Numbers are assigned in sequence and never reused.

Each record carries a status of proposed, accepted, superseded, or deprecated.

## Consequences

There is a written trail for every decision that affects what an output means.

Changing such a decision costs a new record, which is the intended friction.

The records are the place to look before arguing with a design choice, and the
place to add to after winning the argument.

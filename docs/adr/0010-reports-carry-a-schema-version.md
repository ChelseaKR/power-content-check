# 10. Reports carry a schema version

Date: 2026-08-22

## Status

accepted

## Context

The JSON report was designed for humans reading one run and scripts parsing
many. The second reader exists the moment anyone wires this tool into a
pipeline, and for that reader the shape of the report is an interface in
exactly the sense the check identifiers are: something filed against today's
output has to be readable against next year's.

The identifiers already have their guarantee. `tests/test_registry.py` pins
the set, and the changelog records that retiring one is a breaking change.
The report's keys had no equivalent. A key added, renamed or removed would
arrive as a silent KeyError in someone else's script, which is the failure
mode ADR 0002 exists to prevent applied to code instead of requirements:
a gap implied by silence.

Reserving the word "version" needed care, because this project already
versions two other things. The tool version moves with every release and the
ruleset identifier moves with the regulations. Neither tells a consumer
whether `"skipped"` still means what it meant.

## Decision

Every run report carries `schema_version`, starting at 1. It versions the
shape of the output and nothing else.

- Within one version, keys are append only. A new key may appear; no existing
  key may be removed, renamed, retyped, or given a different meaning.
- Removing, renaming, retyping, or remeaning a key bumps the major version
  and is recorded as a breaking change in the changelog, on the same terms as
  retiring a check identifier.
- The version is printed on every report rather than living in the
  documentation, because the report is the thing being parsed.

Enforcement is mechanical. `tests/test_report.py` asserts the exact key sets
of the report, of each document entry, of each result, of the summary and of
a catalog entry, where it previously asserted only a superset. Adding a key
now means touching those tests deliberately, in a diff, which is precisely
the friction the pinned identifier set imposes and for the same reason.

## Consequences

Consumers can branch on `schema_version` instead of guessing. A consumer that
pins version 1 knows its parser holds until this project says otherwise in
words.

The cost is paid by this project first: every interface change starts with a
failed test rather than ending with a surprised user. That is the intended
direction of the friction.

`schema_version` does not appear in the fingerprint, which hashes conclusions
rather than rendering, and does not claim to describe the catalog's text
output, which remains explicitly unversioned terminal formatting.

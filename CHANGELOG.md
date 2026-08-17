# Changelog

All notable changes to this project are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Check identifiers are part of the public interface. A check identifier is never
renumbered and never reused. Retiring a check is a breaking change and will be
recorded as one.

## [Unreleased]

Nothing yet.

## [0.1.0] - 2026-08-17

First cut.

### Added

- A CLI, `power-content-check`, with two commands: `check` and `catalog`.
- 28 registered checks against the Power Content Label format, of which 18 are
  implemented and 10 enforce nothing and report as not evaluated with a written
  reason. Every one of the 28 carries a citation to a published source that was
  fetched and read, with the retrieval date.
- Fail-closed extraction. A document that cannot be read produces a
  not-evaluated result for every registered check, never a conforming one, and
  the run cannot exit 0. Covered by `tests/test_fail_closed.py`, which hashes
  the tool's conclusions for an unreadable input and for a clean one and
  asserts they differ.
- An empty denominator is reported as `NOTHING CHECKED` with exit code 3, not
  as success.
- `--fingerprint`, a hash of a run's conclusions that excludes file paths,
  timestamps and the tool version.
- JSON output carrying the citation for every result.
- A notice reproduced on every report stating that the tool checks conformance
  to a published format, makes no judgment about any supplier's power mix,
  performance or compliance status, does not rank suppliers, and is not
  affiliated with the California Energy Commission or any utility.
- `scripts/fetch_examples.py`, which will cache a small number of published
  labels locally, honouring robots.txt and refusing to fetch in bulk.

### Known gaps

- Ten registered checks enforce nothing. They are listed with reasons in
  `power-content-check catalog`.
- The ruleset is pinned to the regulations effective 2025-06-18. Whether that
  ruleset applies to a label for an earlier data year is a judgment the tool
  does not make; the effective date is printed on every report so the reader
  can make it.
- Two requirements that turn on a 2026 trigger date are registered but not
  enforced, because the published text does not settle whether the trigger
  attaches to a label's publication date or to its data year.

[Unreleased]: https://github.com/ChelseaKR/power-content-check/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ChelseaKR/power-content-check/releases/tag/v0.1.0

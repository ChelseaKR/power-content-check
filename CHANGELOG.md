# Changelog

All notable changes to this project are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Check identifiers are part of the public interface. A check identifier is never
renumbered and never reused. Retiring a check is a breaking change and will be
recorded as one.

## [Unreleased]

### Added

- Every deviation now states the basis on which the tool looked. Extraction
  counts the images a PDF declares, following Form XObjects, and composes one
  sentence from the count: this PDF embeds N images and text inside a picture
  is not read; or it embeds none, so a picture is not the explanation, though
  vector-drawn text would still not be read; or the resources could not be
  enumerated. The sentence heads each document's report, is carried in the
  JSON as `extraction_basis` alongside `image_count`, and is appended to every
  deviation by the constructor that makes one. See `docs/adr/0003`.
- `scripts/inspect_artwork.py`, which prints every image a PDF declares and the
  size at which the page draws it, so that an absence finding can be judged
  against the artwork rather than assumed.
- Every unimplemented check now declares whether its gap is `permanent` or
  `conditional`, shown by `power-content-check catalog` and carried in its
  JSON. `CheckSpec` refuses to construct one without it, and the permanent set
  is pinned in `tests/test_registry.py`. See `docs/adr/0005`.
- PCL029, section 1393.1(c)(6), and PCL030, section 1393.1(c)(2)(C). Both are
  registered and enforce nothing. Both are requirements the catalog previously
  passed over in silence, which is the thing `docs/adr/0002` exists to prevent.
  Registered checks go from 28 to 30 and unimplemented from 10 to 12.
  Implemented stays at 18.

### Changed

- Findings say "does not appear in the extracted text" rather than "in the
  label text", which is the claim the tool is actually entitled to make.
- PCL004 now reports what is present in place of the name: the abbreviation
  "CEC", which the regulation uses but nowhere defines, and any energy.ca.gov
  address. It still does not read either as the name, and section 1391 defines
  the name.
- PCL025's reason is rewritten around the obstacle that actually blocks it.
  Displayed percentages are whole numbers with no rounding rule or tolerance in
  the published text, so a column's components need not add to the total the
  label displays; on the three published 2024 labels this project read, eight
  of fourteen columns summed to 99 or 101 against a displayed 100. Column
  parsing is the smaller problem. The check remains unimplemented and is
  classified permanent.
- PCL023 and PCL024 carry a sharper reason. The trigger attaches to the
  supplier's act of disclosure, which subdivision (b)(2) dates to October 1 of
  each year; what blocks the check is that a label states its data year rather
  than the date it was disclosed.
- PCL021 and PCL027 reasons extended to say what would, and would not, unblock
  them.
- The calibration set went from three published 2024 labels to eight, chosen to
  be unlike each other: three investor owned utilities, two large municipal
  utilities, a community choice aggregator, an electric service provider and a
  rural cooperative. The two deviations the first three reported hold on all
  eight. The column arithmetic result holds too, at fourteen of thirty three
  columns rather than eight of fourteen, with the statewide column one off its
  displayed total on every label read.
- Prescribed phrases are matched with the spaces removed on both sides, through
  `normalize.contains_ignoring_spaces`. A subscript is a separate text run, so
  the CO2 in the footnote prescribed by section 1393.1(l)(2) extracted with a
  space inside the word and PCL014 reported a footnote absent from a label that
  carries it verbatim. Intervening words are still not ignored.
- PCL016 reports not evaluated, rather than a deviation, when every word of an
  accepted rendering appears but the rendering does not. A column heading that
  wraps extracts with the words of the heading beside it inside it, and that is
  indistinguishable from an absent heading by substring match. It reported a
  missing statewide disclosure on two labels that carry one.
- PCL021 is reclassified from conditional to permanent. Positional extraction,
  the capability its reason named, answers where a string sits and not who it
  belongs to, and turning nearness into ownership is a threshold no published
  source supplies. The permanent set pinned in `tests/test_registry.py` goes
  from eight identifiers to nine and conditional from four to three. See
  `docs/adr/0007`.
- PCL019, PCL020, PCL022 and PCL029 reasons sharpened after rereading the
  regulation text and the wider label set. None changed class.

### Documented

- `docs/adr/0006`, what a wider calibration set showed, and how the tool now
  handles a prescribed phrase that extraction broke apart.
- `docs/adr/0007`, why position does not decide who a contact detail belongs
  to, and the reread of the other permanent classifications that went with it.
- `docs/sources.md` lists all eight calibration labels, records that the Energy
  Commission publishes an alternative rendering of each label beside it which
  does name the Energy Commission in full, and records that no label read
  carries any statement of the section 1393.1(c)(6) requirement.
- `docs/adr/0003`, how the artwork question was resolved for the three
  calibration labels and what the tool now says in general.
- `docs/adr/0004`, why one ruleset is the right one for a data year 2024 label
  and why there is no version switching.
- `docs/adr/0005`, the permanent and conditional classification.
- `docs/sources.md` records the docket number and effective date of the
  regulations, the artwork resolution, the ruleset vintage reasoning, and the
  column arithmetic result.

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
  can make it. Settled for data year 2024 in the unreleased entry above.
- Two requirements that turn on a 2026 trigger date are registered but not
  enforced, because the published text does not settle whether the trigger
  attaches to a label's publication date or to its data year. Restated more
  precisely in the unreleased entry above.

[Unreleased]: https://github.com/ChelseaKR/power-content-check/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ChelseaKR/power-content-check/releases/tag/v0.1.0

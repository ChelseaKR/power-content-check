# Changelog

All notable changes to this project are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Check identifiers are part of the public interface. A check identifier is never
renumbered and never reused. Retiring a check is a breaking change and will be
recorded as one.

## [Unreleased]

### Added

- Five checks registered by a completeness sweep that read sections 1391
  through 1394 and PUC 398.4 end to end on 22 August 2026 and diffed every
  content-shaped obligation against the catalog. All five enforce nothing:
  PCL031 marketing claim consistency (permanent, needs the advertisement),
  PCL032 promotional materials inclusion (permanent, distribution is not in
  the distributed file), PCL033 single label for general customers
  (permanent, needs the offering list), PCL034 grandfathered emissions
  exclusion identified (permanent, on PCL020's visible-absence asymmetry),
  and PCL035 footnote secondary group percentage (conditional, travels with
  the PCL023 and PCL024 trigger question). Registered checks go from 30 to
  35; implemented stays at 18.
- Section 1393.1(a)(3) renames the statewide quantity for 2026 onward,
  "California's total loss-adjusted load". That phrasing joins the accepted
  renderings for PCL016, cited from the regulation itself ahead of any label
  carrying it.
- The extraction basis now counts painted vector shapes beside declared
  images, so an absence finding states whether artwork of any enumerable kind
  could be hiding the element. A page that declares no image and paints no
  shape is the strongest position an absence can be reported from, and the
  sentence says so. No check reads either count; a test reads the catalog's
  source to hold that. See `docs/adr/0012`.
- Property tests over generated inputs, holding the ADRs' prose invariants
  mechanically: normalisation folds only its declared character classes and
  is idempotent; space-insensitive matching finds a phrase under any spacing
  extraction invents and never under an inserted word; cell reconstruction
  loses and duplicates nothing, and every segment survives whole inside the
  cell that took it.
- Hostile-input tests: seeded, deterministic mutations of valid label PDFs -
  truncations, bit flips, spliced junk - asserting that no mutation crashes
  extraction or yields a result set that does not account for every
  registered check. The fail-closed guarantee now holds against damaged
  inputs as well as crafted ones.
- `scripts/check_regressions.py`, for contributors with a local fetch cache:
  records each cached label's fingerprint into an uncommitted baseline beside
  the cache, then proves on demand that the current tree concludes about
  every cached document exactly what the recorded tree did. Fingerprints
  exclude paths, timestamps, versions and digests by design, so this compares
  conclusions rather than bytes.
- Multi-page PDFs are now held by fixtures rather than assumed: fuel rows
  split across a page boundary reach the checks through the ordinary page
  join, a heading wrapped at a page break still reads in order without
  geometry, and a reconstructed cell never contains text drawn on two
  different pages, because cells are facts about the page they came from.
- `schema_version` on every JSON report, starting at 1. It versions the shape
  of the output: within a version keys are append only, and removing,
  renaming or retyping one is recorded as a breaking change, on the same
  terms as retiring a check identifier. See `docs/adr/0010`.

### Fixed

- PCL003, PCL004 and PCL005 read the domain half of an email address as a
  website address, because `_DOMAIN` ran over the raw text and an address's
  domain is domain shaped. A label whose only contact was
  `billing@example-utility.example.com` reported CONFORMS on PCL003, which
  is a pass the check was not entitled to on a document carrying no website
  address at all. Email addresses are now taken out of the text before the
  website matcher reads it. Conclusions about all ten cached published
  labels are unchanged.

- PCL018 (displayed column totals) pooled every matching total row's values
  into one undifferentiated list, so a deviation could no longer be traced
  to the specific row that produced it once more than one total row was
  present. Each row is now checked and cited on its own; a deviation names
  the exact row text it came from.

### Changed

- The calibration set went from twenty four published 2024 labels to thirty
  four, in two capped fetch invocations, chosen for supplier types the set
  lacked: a small city municipal utility, a large and a third community
  choice aggregator, a second electric service provider, a small mountain
  district, a bi-state rural cooperative, a second irrigation district, a
  port district, a very small rural cooperative, and a mid-sized municipal
  utility. The standing result holds on all ten: the same two deviations,
  nothing unevaluated beyond the registered checks, PCL016 evaluated
  everywhere, and every image drawn at forty six points or smaller. Recorded
  with URLs in `docs/sources.md`.
- Python 3.14 joins the tested and declared set: the CI matrix runs the gate
  on 3.12, 3.13 and 3.14, and the classifiers say so. The locked dependency
  set needed no change.
- The coverage floor moves from 90 percent to 96, where the suite now measures
  97.2. The floor is configured in `pyproject.toml` and stated in
  CONTRIBUTING; it moves only when what it excludes has been argued with.
- `hypothesis` joins the dev dependency group for the property tests. It is a
  test-only dependency; the package's runtime dependency set is unchanged at
  one.
- The tests now pin the exact key sets of the JSON report, each document
  entry, each result, the summary and a catalog entry, where they previously
  pinned only a superset. A change to any of those shapes fails a test here
  before it fails a consumer's parser.
- Exit code precedence is pinned by explicit tests, including the shadowing
  that holds today: because twelve registered checks always report as not
  evaluated, NOT_EVALUATED beats NONCONFORMANCE on every run over a readable
  document and exit code 1 is unreachable until a conditional check
  implements. That is the documented ordinary result; the tests hold it so
  that implementing a conditional check surfaces deliberately.

### Documented

- `docs/ROADMAP.md`, the expansion roadmap: nine tracks sequenced by the
  events that unblock them, and the refusals recorded with their reasons.
- `docs/adr/0010`, why reports carry a schema version and what moves it.
- `docs/adr/0011`, the refusal of optical character recognition: a document
  without a text layer fails closed rather than getting guessed at, with the
  bar any future recognition path would have to clear written down.
- `docs/adr/0012`, why the basis sentence counts what the page paints, and
  why no threshold converts that count into a judgment.
- CONTRIBUTING gains an upgrade policy for pypdf, the only runtime
  dependency, whose layout machinery `geometry.py` reads from below the
  public surface.

## [0.1.0] - 2026-08-18

First release. A deterministic conformance checker for California Power Content
Labels: it reads a published label and reports which prescribed elements it can
find, which it cannot, and which it is unable to judge. It makes no judgment
about any supplier's power mix, performance or compliance status, and it is not
affiliated with the California Energy Commission or any utility. One entry,
because no earlier tag exists: the first cut and the work recorded against it
before any tag was cut ship together.

### Added

- A CLI, `power-content-check`, with two commands: `check` and `catalog`.
- 30 registered checks against the Power Content Label format, of which 18 are
  implemented and 12 enforce nothing and report as not evaluated with a written
  reason. Every one of the 30 carries a citation to a published source that was
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
- Column reconstruction, in `geometry.py`. A page is read down its columns as
  well as across its lines, so a column heading that wraps onto a second line
  can be put back together. Text is grouped into the horizontal spans a reader
  would see, and two spans are one cell when one's horizontal extent contains
  the other's and they sit within `CELL_LINE_SPACING` of each other. Position
  decides cell membership and nothing else, one check reads the result, and it
  reads it only inside the branch that reports not evaluated, so nothing
  reconstructed here can become a deviation. Every failure returns nothing and
  leaves the caller where it was. See `docs/adr/0008`.
- The report names the files in a directory that are not a format this tool
  reads, in the text output and as `skipped` in the JSON. They are in no count,
  and a directory holding nothing else still reports `NOTHING CHECKED` and
  exits 3. Dropping them in silence left a reader with no way to know that the
  Energy Commission publishes a second rendering of each label beside it. See
  `docs/adr/0009`.

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
- The calibration set went from eight published 2024 labels to twenty four of
  the ninety one published, adding a fourth investor owned utility and a
  multi-state one, five more municipal utilities, three more community choice
  aggregators, a second electric service provider, a second rural cooperative,
  two irrigation districts, a transit district and a university system. The two
  deviations hold on all twenty four. No label read carries a telephone number,
  none names the Energy Commission in full, and one carries the mixed portfolio
  footnote of section 1393.1(f).
- PCL016 is evaluated on all twenty four published labels read. It was
  unevaluated on seven of them, because the wrapped column heading of
  `docs/adr/0006` is common rather than rare, and reading the page down its
  columns recovers the heading on every one. The refusal it added is intact:
  where the reconstruction does not put a rendering back together either, the
  check still reports not evaluated and now says which of the two it tried.
- PCL020, PCL021, PCL025 and PCL029 reasons carry the figures from the wider
  set. The statewide column that the Energy Commission supplies sums to 101
  against a displayed total of 100 on all twenty four labels. The fourteen of
  thirty three per-column count is now scoped explicitly to the eight labels it
  was measured on, rather than restated across a set where it was not.

### Documented

- `docs/adr/0006`, what a wider calibration set showed, and how the tool now
  handles a prescribed phrase that extraction broke apart.
- `docs/adr/0007`, why position does not decide who a contact detail belongs
  to, and the reread of the other permanent classifications that went with it.
- `docs/adr/0008`, the one use ADR 0007 left open for position, and the four
  things that fence it in.
- `docs/adr/0009`, why the spreadsheet the Energy Commission publishes beside
  each label is not this tool's subject. Three answers were set out and the
  narrowest was taken: the tool keeps one document as its subject, does not
  read the workbook, and never treats two files as one label. Read out to text
  and checked, each of the four workbooks read produces seven deviations rather
  than two, five of which are true of a data extract and misleading about a
  disclosure.
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

### Known gaps

- Twelve registered checks enforce nothing. They are listed with reasons in
  `power-content-check catalog`.
- The ruleset is pinned to the regulations effective 2025-06-18. Whether that
  ruleset applies to a label for an earlier data year is a judgment the tool
  does not make; the effective date is printed on every report so the reader
  can make it. Settled for data year 2024; see `docs/adr/0004`.
- Two requirements that turn on a 2026 trigger date are registered but not
  enforced, because the published text does not settle whether the trigger
  attaches to a label's publication date or to its data year. Restated more
  precisely under PCL023 and PCL024 in Changed above.

[Unreleased]: https://github.com/ChelseaKR/power-content-check/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ChelseaKR/power-content-check/releases/tag/v0.1.0

# Calibration census

The README and `docs/sources.md` publish four figures about the calibration set:
thirty four labels read, the same two checks and only those two deviating on
every one of them, fifteen checks conforming on every one, and seventeen checks
evaluable without a supplier name on the command line.

`census.json` is where the evidence behind those figures belongs: per registered
check, on how many labels it conformed, deviated and went unevaluated, plus the
digests of the labels counted. No supplier name, no file name, no path and no
URL is in it. That is what lets it be published: it is a per-check record, never
a per-supplier one, so it cannot be read as a ranking and it redistributes no
label.

## `census.json` is not committed yet

While it is absent, the four figures rest on a note typed by hand from a run
nobody else can repeat. This file exists so that state is stated rather than
silent, and `tests/test_calibration_census.py` fails if it is removed while the
census is still missing.

Writing it needs the local label cache, which git excludes and which this
repository will never carry, so it cannot be generated in CI or by a
contributor. On the machine holding the cache:

```bash
uv run python scripts/check_regressions.py census --vintage 2024
```

`--vintage` is required and is not guessed. Which label year was fetched is a
fact about the fetch; the cached bytes do not say it, and a default would
publish a guess as a measurement.

The command refuses rather than writes when the cache cannot produce an honest
census: a document with no content digest, or the same digest twice, which would
publish a labels-read figure larger than the number of labels actually read.

## What holds it once it lands

Nothing in `tests/test_calibration_census.py` needs the cache except one method,
`TestTheCensusMatchesTheCache`, which regenerates the census and requires the
committed file to be what comes out. Everything else runs everywhere:

- the published figures are pinned to their literal values and to the sentences
  they are written out in, so editing "thirty four" in the README fails today,
  with no census and no cache;
- the comparison between published figures and census is a pure function driven
  from synthetic censuses on every run, with a positive control and four
  negative ones, so its failing branch executes rather than waiting for a bad
  census to exist;
- once `census.json` is committed, the real pair goes through that same
  function, and a repeated digest or a check whose outcomes do not cover the
  labels is refused.

## What the census deliberately does not record

The artwork enumeration state per batch, which `docs/sources.md` records in
prose. Whether artwork was enumerated and placed for a batch is a fact about a
manual procedure run with `scripts/inspect_artwork.py`, not something the cache
or a run over it can report, so deriving it would mean inventing it. It stays in
prose until there is a machine-readable record of the procedure itself.

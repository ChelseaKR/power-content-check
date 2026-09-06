# power-content-check

A deterministic conformance checker for California Power Content Labels.

California's Power Source Disclosure program requires every retail electricity
supplier to disclose, once a year, the fuel mix and greenhouse gas emissions
intensity of each electricity portfolio it sells. The disclosure goes on a
Power Content Label, and the label's contents are prescribed in regulation.
This tool reads one of those labels and reports which prescribed elements it
can find, which it cannot, and which it is unable to judge.

**Status:** Pre-release. `pyproject.toml` and `CITATION.cff` declare version
`0.1.0` and no tag has been cut, so nothing has been released: no `v0.1.0` tag,
no GitHub Release, no package-registry publication, nothing you can install by
version. `CHANGELOG.md` records the work prepared under that number.
`tests/test_release_claims.py` reads `git tag --list` and fails if this stops
being said here while it stays true.

## What this tool does not do

It checks conformance to a published format. **It makes no judgment about a
supplier's power mix, its performance, or its compliance status.** It does not
rank suppliers, it produces no leaderboard, and it says nothing about whether
any energy source is good or bad. Structural conformance only.

**This project is not affiliated with, endorsed by, or approved by the
California Energy Commission or any utility.**

Under the regulation, the Energy Commission generates the label on a supplier's
behalf, or supplies a template, and the supplier may not alter the format. A
deviation this tool reports is therefore a property of a document. It is not
evidence of anything a named supplier did, and it is not a compliance
determination, which only the Energy Commission can make.

## Install

Requires Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/ChelseaKR/power-content-check
cd power-content-check
uv sync --locked
```

## Usage

```bash
# check one label
uv run power-content-check check path/to/label.pdf

# name the supplier so the company-name check can run
uv run power-content-check check label.pdf --supplier-name "Example Utility"

# machine readable
uv run power-content-check check label.pdf --json

# every registered check, with the requirement each one cites
uv run power-content-check catalog

# show the text one check scanned, and where the match failed
uv run power-content-check explain label.pdf PCL012
```

Accepts `.pdf` and `.txt`. A directory is expanded to the supported files
inside it, and anything else in that directory is named at the end of the
report so that you know what was not read.

The JSON report carries a `schema_version` (currently 1). Within a version,
keys are append only; removing or changing one is a breaking change and moves
the version. See [docs/adr/0010](docs/adr/0010-reports-carry-a-schema-version.md).

That last part matters for one file in particular. The Energy Commission
publishes a spreadsheet beside every label, an alternative rendering of the
same disclosure. This tool does not read it, deliberately, and
[docs/adr/0009](docs/adr/0009-the-second-file-is-not-this-tools-subject.md)
is the argument for that rather than an omission.

The tool is offline. It opens the files you name and nothing else. No network
call, no telemetry, no account, no configuration file, no cache.

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | every document was readable and every implemented check conformed |
| 1 | at least one check found a deviation from the prescribed format |
| 2 | at least one check could not be evaluated, including any document that could not be read |
| 3 | nothing was checked |
| 64 | usage error |

Higher codes win. A run that both checked nothing and found a deviation reports
the louder of the two, never the quieter.

Note that exit code 2 is the ordinary result for a well formed label, because
seventeen registered checks enforce nothing and always report as not evaluated.
That is deliberate. See below.

### Things noticed that no requirement covers

The tool reports only against published requirements, and calibration kept turning
up facts about labels that no requirement addresses: a prescribed phrase present
only once the extractor's spaces are ignored, a data year printed in two places
that disagree, a page with no text layer in a document whose other pages have one.
Those used to live as prose in `docs/sources.md` and as silence in the report.

They now have a channel of their own, and the channel is fenced so it cannot
become a back door for rules. An advisory carries no status, no severity and no
citation; the code space is closed to `ADV-BROKEN-PHRASE`,
`ADV-DATA-YEAR-MISMATCH` and `ADV-TEXTLESS-PAGE`; an observation phrased as an
obligation is refused at construction; and nothing here reaches a status, an
exit code or a fingerprint, so a regression baseline recorded before advisories
existed is still valid. See
[docs/adr/0013](docs/adr/0013-an-advisory-channel-fenced-off-from-the-rules.md).

The recorded refusals stay refused. Summing the fuel mix columns against the
displayed total is not an advisory candidate: PCL025's reason is about the
arithmetic, not about which channel carries it.

### Showing the work behind one check

A deviation is a claim about extracted text. `explain` prints the text the
check read, the literal or pattern it looked for, whether each one matched,
and where the nearest candidate span stopped agreeing with the phrase.

```sh
power-content-check explain LABEL.pdf PCL010
power-content-check explain LABEL.pdf PCL010 --json
```

It decides nothing new. The status it prints comes from the same function
`check` runs, over a registry holding the one named check, so the conclusion is
identical by construction rather than by agreement. Its exit code is the code
that one conclusion implies on the table above, and an unregistered identifier
is a usage error.

Near miss reporting is descriptive and threshold free: it reports the longest
run of characters over which the document and the phrase agree, anchored on the
phrase's first character. There is no cut off above which a near miss becomes a
match, so nothing here can turn into a lenient matcher. For a regular
expression it says whether the pattern matched and quotes what it matched; it
does not invent a nearest span, because "how close did this text come to
matching a pattern" has no answer this tool is entitled to give.

This is what distinguishes a genuine deviation from a phrase the extractor
broke apart. On a label whose CO2e is set with a subscript 2, the output shows
`co 2e` in the document, names the space as the character where the phrase
diverged, and reports that the space insensitive fold matched it anyway.

### Comparing two reports

A report is a set of statements about a document, so two reports can be compared
and the difference is another set of statements about that document.

```sh
power-content-check check label.pdf --json > before.json
# change a matcher, or read the supplier's reissued label
power-content-check check label.pdf --json > after.json
power-content-check diff before.json after.json
```

For each check whose status moved, `diff` prints both statuses and the finding
sentence on each side; beside them it prints any document fact that moved, such
as readability, page count or the extraction basis, because a deviation found on
a document read as two pages is not the same evidence as one found on a document
read as five. `--jsonl` emits one object per change, sorted, so two runs produce
identical bytes. Documents are matched by path, or by `sha256` with `--by-hash`
when the paths differ and the bytes do not.

Its exit codes are its own: `0` nothing moved, `3` something moved, `64` the two
reports cannot be compared. `check` and `diff` answer different questions and
neither code set is read across them.

Three things it will not do:

- **A check present on one side only is reported as added or removed, never as a
  status move.** Registering a check makes it appear in the later report with a
  status; calling that a move would report a conclusion changing when nothing
  about the document did.
- **Two reports at different `schema_version` values are refused, with both
  versions named.** The shape is append only within a version (ADR 0010), not
  across versions, so diffing them could attribute a schema change to the label.
- **No direction is named.** A move from `does_not_conform` to `conforms` prints
  with both sides and no adjective. These are document facts, and none of them is
  a statement about a supplier.

`scripts/check_regressions.py compare --explain` uses the same comparison to name
which check moved on which cached label, rather than only that a fingerprint did.
It refuses, in words, when the baseline predates the stored reports: explaining
nothing must not read like nothing having moved.

## Two rules this tool is built around

### A document it could not read is never reported as conforming

A scanned label, an encrypted PDF, a corrupt file, a file with no text layer:
each of these yields an empty string from a text extractor, and an empty string
looks exactly like a document with nothing wrong. The tool refuses that
collision. An unreadable document produces a not-evaluated result for every
registered check, and the run cannot exit 0.

`tests/test_fail_closed.py` proves it by hashing the tool's conclusions for an
unreadable input and for a clean one and asserting the hashes differ. The hash
excludes file paths, timestamps and the tool version, so it compares what the
tool concluded rather than what it was handed.

### Checking zero labels is not success

Point the tool at an empty directory and it exits 3 and prints `NOTHING
CHECKED`. An empty denominator is never a pass.

## What the tool can see, and what it says about it

Extraction reads a PDF's text layer. A label can also carry content as artwork,
and artwork is invisible to a text extractor. So every deviation this tool
reports is the absence of something from extracted text, which is a smaller
claim than absence from the document, and the tool is worded to make the
smaller claim.

Each report opens with what the tool was able to look at, and the same sentence
is appended to every deviation, so a finding quoted on its own still carries
it:

```
Basis: the text layer of this PDF, which also embeds 7 images and paints 2
vector shapes. Text that is drawn inside a picture or as a vector outline is
not read.
```

The sentence carries two counts: the images a page declares and the vector
shapes it paints. For a PDF with neither, and where a search of the content
streams also finds no image drawn inline, the sentence says so plainly, which
is the strongest position an absence can be reported from: a picture is not an
available explanation. Where either count cannot be taken, or where an inline
image is present or cannot be ruled out, it says that instead of printing
zero.

`scripts/inspect_artwork.py` prints every image a PDF declares, including those
reached through a Form XObject, and the size at which the page draws it, with
the form's own transform composed in. That is the same set the checker counts,
so you can judge whether a missing element could plausibly be inside one. Where any doubt remains, render the page and look at
it. `docs/sources.md` records that being done for the first eight published
labels this project calibrated against, and what it showed.

### A phrase the extractor broke apart is not a phrase the label lacks

Artwork is one way a text extractor loses content. Handing it over in pieces is
another. A subscript is a separate text run, so the CO2 in the footnote
prescribed by section 1393.1(l)(2) extracts with a space inside the word; a
column heading too long for its column wraps, and extraction reads across the
wrap, so the heading beside it arrives in the middle of this one.

Both produced deviations against published labels that plainly carry the
element. Prescribed phrases are now matched with the spaces removed on both
sides, which ignores where the extractor put its spaces without ignoring what
sits between the words. See
[docs/adr/0006](docs/adr/0006-a-phrase-the-extractor-broke-apart.md).

### A heading that wrapped is read down its column instead

Refusing to decide the wrapped heading was right and it cost coverage: the
statewide disclosure check went unevaluated on seven of the twenty four
published labels read.

So the page is now read column by column before that check gives up. Text is
grouped into the horizontal spans a reader would see, and two spans are one
cell when one's horizontal extent contains the other's and they sit close
enough together to be lines of one cell. That puts a wrapped heading back
together, and the check is evaluated on all thirty four.

Position is used to decide which cell a word is in, and for nothing else. It is
consulted only inside the branch that reports not evaluated, so the most it can
do is turn "the tool cannot tell" into "the tool found it". It cannot produce a
deviation, and a test holds that. See
[docs/adr/0008](docs/adr/0008-column-geometry-decides-which-cell.md).

## Which ruleset, for which year

The tool encodes one ruleset and prints its identifier and effective date on
every report.

For the labels the Energy Commission currently publishes, which cover data year
2024, that ruleset is the one in force: section 1393.1(b)(2) requires a label
to be provided by October 1 of each year, so a 2024 label is the disclosure due
October 1, 2025, after the regulations took effect on June 18, 2025.

For a label from an earlier data year the tool will measure against a later
ruleset, and it will not warn you, because a data year is not a publication
date. The printed effective date is what you have. There is no version
switching, and building it with one ruleset in existence would be building a
mechanism nothing could test.

## Grounding

Every check cites the published requirement it enforces, and the citation
travels with the check into the JSON output and the `catalog` command. Nothing
here is written from memory. The sources are listed in
[docs/sources.md](docs/sources.md), each with the URL it was fetched from and
the date it was read.

If you came here to verify this tool rather than to use it,
[docs/AUDITING.md](docs/AUDITING.md) is the entry point: how to audit a check
against the source it cites, how to reproduce a finding by hand, what the tool
refuses to conclude and why, and how to catch an implemented check that cannot
fail.

Each check declares a basis:

- **regulation text**: the regulation enumerates the element in words.
- **template format**: the element is part of the label format the Energy
  Commission itself issues. Two checks are on this basis and both say so.

### 18 checks are implemented

Contact details, the twelve fuel type categories, the two resource groups and
the RPS-eligible subcategory, the emissions intensity units, retired unbundled
RECs, the unspecified power annotation, the three prescribed footnotes, the
separate statewide disclosure, the data year, and the displayed column totals.

### 17 checks are registered and enforce nothing

They appear in every report as not evaluated, with a written reason. They are
in the catalog rather than absent from it because a requirement this tool does
not measure should be visible, not implied by silence.

Each one also says whether the gap can ever close:

- **permanent**, for thirteen of them. No version of this tool that reads the
  document it is handed can decide the requirement, because the fact it turns
  on is not in the document, or because deciding it would mean inventing a rule
  no published source supplies. Needing the supplier's annual resource report
  as a second input is one. Needing to know whether a portfolio was negotiated
  under private agreement is another. So is adding up a column of whole
  percentages that were rounded, against a total the label displays, with no
  rounding rule or tolerance in the published text to compare against. So is
  saying which of two contact details belongs to whom, on a document that does
  not say. So is deciding a marketing claim's consistency, which needs the
  advertisement the claim was made in.

- **conditional**, for four of them, where the reason names what would unblock
  it: a document that does not exist yet.

Run `uv run power-content-check catalog` for the full list with reasons, and
see [docs/adr/0005](docs/adr/0005-say-whether-a-gap-can-ever-close.md).
PCL021 moved from conditional to permanent once the capability it named,
reading where on the page each string sits, was assessed and found to answer a
different question than the one it is blocked on. See
[docs/adr/0007](docs/adr/0007-position-does-not-decide-ownership.md).

Neither count measures coverage, and finding two more gaps did not close any.
The number of implemented checks is the one that moves when the tool gets
better.

## Examples

No published label is committed to this repository. The test fixtures are
synthetic: they imitate the shape of the issued format and carry no real
supplier's figures.

`scripts/fetch_examples.py` will fetch a small number of published labels into
a local, ignored cache if you want to exercise the tool against real documents.
It honours robots.txt, rate limits itself, and refuses to fetch in bulk. Twenty
four of the ninety one published labels have been read this way, and three of
the checks are the way they are because of what a wider set showed that a
narrower one did not. On all thirty four the same two checks, and only those
two, report a deviation. Which is a fact about the rendering the Energy
Commission issues, not about thirty four suppliers.

`scripts/inspect_artwork.py` reports the artwork on a PDF page. Neither script
is part of the package and neither is invoked by the CLI, which is offline.

## Development

```bash
make verify
```

That runs lint, formatting, strict type checking, the test suite against its
coverage floor, and the security scanners. It is the gate.

## Standards Conformance

| Standard | State |
| --- | --- |
| Responsible-Tech Framework | Applies |
| Code Quality | Applies |
| Security & Supply-Chain | Applies |
| CI/CD | Applies |
| Release & Versioning | Applies, not met. Version `0.1.0` is declared in `pyproject.toml` and `CITATION.cff`, no tag has been cut, and nothing has been released. `tests/test_release_claims.py` derives that from `git tag --list` rather than restating it: it fails if the declared version is neither tagged nor disclosed as untagged in the status line or this row, if another file restates a different version, if `CITATION.cff` carries a `date-released` without a tag naming it, or if `CHANGELOG.md` dates a section for a version nothing was tagged for |
| Observability | Applies |
| Performance | Applies |
| Accessibility | N/A (no human-facing rendered surface; output is a terminal stream and JSON) |
| Internationalization | N/A (English-only operator output over an English-only source document) |
| AI Evaluation | N/A (deterministic text matching; no model is called, ever) |
| Documentation | Applies |
| Quality & Metrics | Applies |
| AI Development Measurement | Applies |
| Incident Response | Applies |
| Data Governance | Applies |

## License

Apache-2.0. See [LICENSE](LICENSE).

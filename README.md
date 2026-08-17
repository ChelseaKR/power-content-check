# power-content-check

A deterministic conformance checker for California Power Content Labels.

California's Power Source Disclosure program requires every retail electricity
supplier to disclose, once a year, the fuel mix and greenhouse gas emissions
intensity of each electricity portfolio it sells. The disclosure goes on a
Power Content Label, and the label's contents are prescribed in regulation.
This tool reads one of those labels and reports which prescribed elements it
can find, which it cannot, and which it is unable to judge.

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
```

Accepts `.pdf` and `.txt`. A directory is expanded to the supported files
inside it.

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
twelve registered checks enforce nothing and always report as not evaluated.
That is deliberate. See below.

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
Basis: the text layer of this PDF, which also embeds 7 images. Text that is
drawn inside a picture is not read.
```

For a PDF with no images at all, the sentence says so, which is a stronger
position to report an absence from. It still notes that text drawn as vector
paths would not be read either, because the count measures images and nothing
more.

`scripts/inspect_artwork.py` prints every image a PDF declares and the size at
which the page draws it, so you can judge whether a missing element could
plausibly be inside one. Where any doubt remains, render the page and look at
it. `docs/sources.md` records that being done for the eight published labels
this project calibrated against, and what it showed.

### A phrase the extractor broke apart is not a phrase the label lacks

Artwork is one way a text extractor loses content. Handing it over in pieces is
another. A subscript is a separate text run, so the CO2 in the footnote
prescribed by section 1393.1(l)(2) extracts with a space inside the word; a
column heading too long for its column wraps, and extraction reads across the
wrap, so the heading beside it arrives in the middle of this one.

Both produced deviations against published labels that plainly carry the
element. Prescribed phrases are now matched with the spaces removed on both
sides, which ignores where the extractor put its spaces without ignoring what
sits between the words. Where other words are inside the phrase, the tool
reports not evaluated rather than choosing between "absent" and "wrapped". See
[docs/adr/0006](docs/adr/0006-a-phrase-the-extractor-broke-apart.md).

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

Each check declares a basis:

- **regulation text**: the regulation enumerates the element in words.
- **template format**: the element is part of the label format the Energy
  Commission itself issues. Two checks are on this basis and both say so.

### 18 checks are implemented

Contact details, the twelve fuel type categories, the two resource groups and
the RPS-eligible subcategory, the emissions intensity units, retired unbundled
RECs, the unspecified power annotation, the three prescribed footnotes, the
separate statewide disclosure, the data year, and the displayed column totals.

### 12 checks are registered and enforce nothing

They appear in every report as not evaluated, with a written reason. They are
in the catalog rather than absent from it because a requirement this tool does
not measure should be visible, not implied by silence.

Each one also says whether the gap can ever close:

- **permanent**, for nine of them. No version of this tool that reads the
  document it is handed can decide the requirement, because the fact it turns
  on is not in the document, or because deciding it would mean inventing a rule
  no published source supplies. Needing the supplier's annual resource report
  as a second input is one. Needing to know whether a portfolio was negotiated
  under private agreement is another. So is adding up a column of whole
  percentages that were rounded, against a total the label displays, with no
  rounding rule or tolerance in the published text to compare against. So is
  saying which of two contact details belongs to whom, on a document that does
  not say.

- **conditional**, for three of them, where the reason names what would unblock
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
It honours robots.txt, rate limits itself, and refuses to fetch in bulk. Eight
published labels have been read this way, and two of the checks are the way
they are because of what the eighth showed that the third did not.

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
| Release & Versioning | Applies |
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

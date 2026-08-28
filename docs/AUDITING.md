# Auditing this tool

This document is for someone verifying the tool rather than using it. It
assumes you do not trust it, which is the right posture: it makes claims
about documents that people are required by regulation to publish, and the
only thing that makes such a claim worth anything is that you can check it.

It is an entry point, not a second copy of the reasoning. Where a question
was decided, this points at the decision rather than restating it, because a
restatement drifts from the decision and the drift is invisible.

Two things are worth knowing before anything else, and both are in the
README's opening: this project is not affiliated with, endorsed by, or
approved by the California Energy Commission, and nothing it emits is a
compliance determination. Only the Energy Commission makes those.

## 1. Audit a check against the source it cites

Every check carries a citation, and the citation carries the quote it was
built from. Nothing in the catalog is a rule this project wrote; if you find
one, that is the most serious defect you can report.

Print the whole catalog with the requirement each check cites:

```sh
power-content-check catalog
```

Or take one check and go straight to its source:

```sh
power-content-check catalog --json | python -c "
import json, sys
for entry in json.load(sys.stdin):
    if entry['id'] == 'PCL012':
        print(entry['citation']['locator'])
        print(entry['citation']['source_url'])
        print(entry['citation']['quote'])
"
```

The audit is then a reading task, and it is the one that matters most:
**open the URL, find the locator, and read whether the quote is transcribed
and whether the check's `what_it_looks_for` is narrower than the quote.**
A check that looks for more than its quote requires is enforcing something
invented. A check that looks for less is honest and under-powered, which is
a different and much smaller problem.

Every catalog entry carries the same keys:

```
['basis', 'blocker', 'citation', 'id', 'implemented', 'title', 'unimplemented_reason', 'what_it_looks_for']
```

`basis` says which kind of source the check rests on, and there are exactly
two:

```
['regulation_text', 'template_format']
```

`regulation_text` means the regulation enumerates the element in words.
`template_format` means the element is part of the format the Energy
Commission itself issues, which section 1393.1(i) says a supplier may not
alter. Anything that is neither is not a check.

Which documents were read, which yielded a citation, and which were read and
grounded nothing, is recorded in [sources.md](sources.md). That last
category is there on purpose, so a later reader can tell a gap from ground
that was never covered.

## 2. Reproduce a finding by hand

```sh
power-content-check check LABEL.pdf --verbose --supplier-name "Some Utility"
```

Every line of the report is meant to be checkable without the tool. A
finding names what was looked for, and the detail beneath it names both the
requirement and what the tool could see of the document. To reproduce one:

1. **Read the finding as a claim about extracted text**, not about the
   document and never about the supplier. "The words 'Energy Commission' do
   not appear in the extracted text" is a smaller claim than "the label does
   not name the Energy Commission", and the smaller one is deliberately the
   one on the page. [adr/0003](adr/0003-report-what-the-tool-could-see.md).
2. **Read the extraction basis sentence** on the deviation. It says how much
   of the document the tool could see, which is what tells you whether an
   absence means anything at all. See section 4 below.
3. **Find the cited text yourself** by the route in section 1.
4. **Open the label and look**, which is the step no amount of tooling
   replaces and which the calibration record itself used.

To compare two runs without comparing timestamps and paths:

```sh
power-content-check check LABEL.pdf --fingerprint
```

The fingerprint hashes the run's conclusions and excludes paths, timestamps,
versions and digests, so two trees agreeing on a fingerprint agree about
what they concluded.

## 3. What a status means, and what it can never become

A result carries exactly one of three statuses, and there are no others:

```
['conforms', 'does_not_conform', 'not_evaluated']
```

If you see a status table anywhere claiming more than these three, it is
wrong. You can settle it in one command:

```sh
power-content-check check tests/fixtures/deficient_label.txt --json | python -c "
import json, sys
report = json.load(sys.stdin)
print(sorted({r['status'] for r in report['documents'][0]['results']}))
"
```

**`not_evaluated` can never resolve to a pass.** That is the load-bearing
guarantee of the whole tool, and it is worth attacking directly, because a
tool that quietly turned "I could not tell" into "conforms" would be worse
than nothing. It is argued in
[adr/0001](adr/0001-fail-closed-on-unreadable-documents.md) and held in
`tests/test_fail_closed.py`: an unreadable document produces a
`not_evaluated` result for every registered check rather than an empty list,
and any exception a check raises is converted to `not_evaluated` rather than
swallowed.

The exit codes follow the same rule. Higher wins, so a run that checked
nothing cannot report as a run that found nothing:

| code | meaning |
| --- | --- |
| 0 | every document was readable and every implemented check conformed |
| 1 | at least one check found a deviation |
| 2 | at least one check could not be evaluated, including an unreadable document |
| 3 | nothing was checked; an empty denominator is never a pass |
| 64 | usage error |

Note what follows from that today: because registered-but-unimplemented
checks always report `not_evaluated`, code 2 shadows code 1 on every run
over a readable document. That is the documented ordinary result, not a
defect, and `tests/test_cli.py` holds it deliberately so that implementing a
conditional check surfaces there first.

## 4. What the extraction basis does and does not cover

Extraction reads a PDF's text layer. Content present only as artwork is not
in that layer, so an absence finding is worth exactly as much as your
confidence that the element was not drawn as a picture. The tool does not
ask you to take that on faith: every deviation carries a sentence saying
what the pages declare and what they paint.

- **Images declared and shapes painted** are counted and reported, with an
  enumeration failure printed as unknown rather than as zero. No check reads
  either count; they qualify what an absence means and decide nothing.
  [adr/0012](adr/0012-the-basis-counts-what-the-page-paints.md).
- **OCR is refused**, and the refusal is argued rather than assumed. Its
  output is a model's guess at text, which would put a probabilistic layer
  inside a tool whose value is that it contains none. A scanned label fails
  closed, loudly, and a human renders the page and looks at it. The ADR also
  writes down the bar anything reopening this would have to clear.
  [adr/0011](adr/0011-no-recognition-of-pictures.md).
- **A phrase the extractor broke apart** is not a phrase the label lacks.
  Prescribed footnote text is matched with the spaces removed on both sides,
  because a subscript in the issued rendering split "CO2" into two runs.
  [adr/0006](adr/0006-a-phrase-the-extractor-broke-apart.md).
- **Column geometry** is used for one narrow thing, deciding which cell a
  word sits in, and is consulted only inside the branch that reports
  `not_evaluated`, so it can never produce a deviation.
  [adr/0008](adr/0008-column-geometry-decides-which-cell.md).

## 5. What the tool refuses to conclude

Each of these was considered and refused for a reason that still holds.
Reopening one means overturning its reason, not resubmitting the idea. The
full list is under Refusals in [ROADMAP.md](ROADMAP.md); the ones an auditor
is most likely to expect to find and not find are:

- **Who a contact detail belongs to.** PCL002, PCL003 and PCL005 count
  contact details; nothing attributes one to a supplier. Nearness is not
  ownership, and turning it into ownership means choosing a distance, which
  is a threshold no published source supplies.
  [adr/0007](adr/0007-position-does-not-decide-ownership.md).
- **Whether the fuel mix columns add up.** The label displays whole
  percentages and nothing published prescribes a rounding rule or a
  tolerance, so correctly rounded arithmetic fails an equality test and any
  tolerance would be invented. PCL018 checks the total the label itself
  displays; PCL025 is registered and enforces nothing, and says why.
- **The spreadsheet published beside each label.** It is an alternative
  rendering, not the label, and checking it produces five misleading
  deviations out of seven.
  [adr/0009](adr/0009-the-second-file-is-not-this-tools-subject.md).
- **Anything comparative about named suppliers.** No rankings, scorecards or
  leaderboards. The tool reports which prescribed elements a document
  carries.

## 6. Audit the gaps, not just the checks

Seventeen of the thirty five registered checks enforce nothing, and that is
a designed outcome rather than a backlog.
[adr/0002](adr/0002-register-unenforced-requirements.md) argues why a
requirement the tool cannot measure is registered and reported as
`not_evaluated` instead of being left out: a catalog that omitted them would
look complete, and the gap would be communicated by silence.

Each carries a `blocker`, and there are exactly two kinds:

```
['conditional', 'permanent']
```

`permanent` means no version of this tool that reads the document it is
handed can decide the requirement. `conditional` means the reason names
something that could change. The distinction exists so a later reader can
stop reopening the permanent ones.
[adr/0005](adr/0005-say-whether-a-gap-can-ever-close.md).

The audit here is to read `unimplemented_reason` and ask whether it is a
reason or an excuse. "Not implemented yet" would be an excuse. "Whether any
customer is served by a mixture of portfolios is a fact about the supplier's
service, not about the document" is a reason.

```sh
power-content-check catalog --json | python -c "
import json, sys
for entry in json.load(sys.stdin):
    if not entry['implemented']:
        print(entry['id'], entry['blocker'], entry['unimplemented_reason'][:80])
"
```

## 7. Audit an implemented check for the ability to fail

The inverse of section 6, and the one an auditor is best placed to do. A
registered check that enforces nothing announces itself in every report. An
implemented check that cannot reach its deviation branch does not: it
reports `conforms` on every document anyone tries, including the ones it
exists to notice, and nothing in the catalog or the coverage number tells it
apart from a check that works.

Take a check, read its citation, and construct the document it should
deviate on **from the cited text rather than from the code**, so that the
construction cannot inherit the code's own assumption. Then run the tool on
it. If it reports `conforms`, you have found the most serious kind of defect
this tool can carry.

This is Track J in [ROADMAP.md](ROADMAP.md), which records the method and
what it has found so far.

## 8. The calibration record, and extending it

Published labels are read to confirm that the checks fire correctly on real
documents rather than only on synthetic fixtures. No label is committed to
this repository and none will be; the record lives in prose and hashes in
[sources.md](sources.md), which says which labels were read, in what
batches, chosen how, and what each batch confirmed or contradicted.

Test fixtures are synthetic. They imitate the shape of the issued format and
carry no real supplier's figures.

To read published labels yourself:

```sh
python scripts/fetch_examples.py     # honours robots.txt, rate limits, refuses bulk runs
python scripts/inspect_artwork.py    # enumerate and place the artwork on a page
```

Widening happens in deliberate, diverse batches rather than in bulk, because
the point of the set is judgment and not a coverage statistic. If you have a
local cache, prove that a change moves no conclusion about a real label:

```sh
python scripts/check_regressions.py record    # once, to write the baseline
python scripts/check_regressions.py compare   # before pushing
```

The baseline is written beside the cache and is not committed. It is a fact
about one machine's cache, not about the project.

## 9. Reproduce the gate

```sh
uv sync --locked
make verify
```

That is exactly what CI runs: lint, formatting, strict type checking, the
test suite against its coverage floor, and the security scanners. Read its
exit code rather than the tail of its output.

The tool makes no network calls at runtime. `make verify` does, because
`pip-audit` resolves advisories, and the fetch scripts do, because fetching
is what they are for. Neither is the CLI, and a code path reaching the
network from inside the package is a defect worth reporting.

# Roadmap

This document records where the project intends to go, what each step is
waiting on, and what has been considered and refused. It is event-driven
rather than date-driven: most of what constrains this tool is outside it,
and the calendar matters only where the calendar is the fact that matters
(the annual publication of labels, and the effective dates of regulations).

Every item below is bounded by the commitments the tool already makes, which
are recorded in the ADRs and enforced in code:

- Every check cites a published requirement that was fetched and read. No
  check enforces a rule this project wrote.
- Findings describe documents, never suppliers. Nothing here is a compliance
  determination.
- Fail closed. What cannot be evaluated is reported as such and can never
  resolve to a pass.
- Offline, deterministic, no model called, ever.

An expansion that would break one of these is not on this roadmap, however
useful it would be. Several such expansions are listed under *Refusals* at
the end, so that they are recorded rather than re-proposed every few months.

---

## Track A - The two 2026-trigger checks (PCL023, PCL024)

**Status: waiting on an external event, expected within weeks of this
writing.**

Sections 1393.1(c) and 1393.1(c)(7) attach new disclosure duties to a 2026
trigger. Both requirements are registered and enforce nothing, classified
conditional, because the published text does not settle whether the trigger
attaches to the date a label was disclosed or to its data year, and because
no label from data year 2025 or later existed to calibrate against.

The event that unblocks both: the Energy Commission publishing labels for
data year 2025. Under section 1393.1(b)(2) those are due October 1, 2026.

Steps, in order:

1. **Read the first published data year 2025 labels** through
   `scripts/fetch_examples.py`, one at a time, under the usual limits.
2. **Settle the trigger question in an ADR** (`docs/adr/0010`). Either the
   total-power-content section appears on labels whose title says 2026, or
   it does not, and whichever way the issued renderings answer it becomes
   the documented basis for the derivation. If the renderings answer it
   inconsistently or not at all, both checks stay registered and the ADR
   says why.
3. **If the derivation holds**: implement PCL023 and PCL024, move them out
   of the conditional set, pin the change in `tests/test_registry.py`, and
   record it in the changelog as an increase in the implemented count.
4. **Calibrate against the wider 2025-vintage set** as it accumulates under
   Track B, since a check built on three labels is how false findings got
   into this tool the first time (see `docs/adr/0006`).

This is the largest single increase in the implemented count available to
the project: two checks, both fully specified by published text, blocked on
a document that does not exist yet.

## Track B - Widen the calibration set to the full published set

**Status: ongoing, no blocker.**

Twenty four of the ninety one published 2024 labels have been read. Each
widening so far paid for itself: the set going from three to eight exposed
two places where the tool reported an element absent from a label that
carries it, and both fixes are now core behavior (`docs/adr/0006`,
`docs/adr/0008`).

Steps:

1. **Widen in diversity-first batches**, as before: pick the labels least
   like the ones already read (supplier type, size, geography), not the
   next ones on the list. Fetch through `scripts/fetch_examples.py`, which
   honours robots.txt, rate limits itself, and refuses bulk runs.
2. **Do the artwork enumeration and placement measurement** for each new
   batch (`scripts/inspect_artwork.py`), and render pages only where doubt
   remains. Record what was done and what was not, as `docs/sources.md`
   already distinguishes for the first eight and the sixteen after them.
3. **Record the result per batch in `docs/sources.md`**: which checks
   deviate, which went unevaluated, whether the standing two deviations
   hold. A batch that contradicts the standing result is more important
   than one that confirms it, and gets an ADR if it changes tool behavior.
4. **When the data year 2025 set publishes**, start the same process on the
   new vintage. First questions for that vintage: does the statewide
   column still sum off its displayed total, does any label carry the
   section 1393.1(c)(6) statement (which would begin to unblock PCL029),
   and do the 2026-trigger elements appear (Track A).

No label is committed to the repository, and none will be. The calibration
record lives in prose and hashes, not in binary fixtures.

## Track C - A second ruleset, when one exists

**Status: deliberately deferred. Activation trigger: a regulation amendment,
or a second vintage whose expectations differ.**

The tool encodes one ruleset and prints its identifier and effective date on
every report. Building multi-ruleset switching while exactly one ruleset
exists would build a mechanism nothing could test, which is the reasoning
recorded in `docs/adr/0004`. That reasoning does not expire, but the
condition it describes will eventually arrive: the regulations were amended
once already in 2025, and the program is young enough that another revision
is plausible.

What happens then:

1. An ADR defining how a report names its ruleset, how a caller could pin
   or inspect one, and what happens when a document's vintage cannot be
   established (the answer will be: the tool measures against what it says
   it measured against, and prints it, exactly as now).
2. The ruleset identifier moves from a constant into a registry, with the
   existing ruleset as its first entry, and `tests/test_registry.py` pins
   both.
3. Check identifiers stay stable across rulesets. A check that means
   something different under a later ruleset gets a new identifier, and the
   old one retires, per the changelog's breaking-change rule.

Until then there is nothing to build, and this roadmap does not pretend
otherwise.

## Track D - A completeness sweep of the source corpus

**Status: not started. No blocker.**

Thirty requirements are registered, drawn mostly from section 1393.1. What
has never been done systematically is the reverse pass: read the whole
operative corpus end to end and enumerate every requirement, so that the
catalog's completeness is demonstrated rather than accumulated.

Scope: sections 1391 through 1394 of the regulations, plus Public Utilities
Code section 398.4, which is cited today only through the chain of
authority and never on its own.

Method:

1. Enumerate every obligation the corpus addresses to the content of a
   label, distinguishing them from obligations addressed to supplier
   conduct (timing, posting, reporting), which this tool cannot see.
2. Diff that enumeration against the thirty registered identifiers.
3. Register anything content-shaped that is missing, as PCL031 onward,
   with the usual citation and a permanent-or-conditional declaration.
4. Where the sweep finds nothing missing, say so in `docs/sources.md`
   with the date of the reread, so the next reader knows the negative
   result was looked for rather than assumed. Absence is easier to miss
   than presence, which is the same reason the *Not consulted* section of
   `docs/sources.md` exists.

One candidate worth attention during the sweep: whether anything in
PUC 398.4 describes label content in terms the regulation does not, since
a statutory basis would be a third value for `Basis` if one exists.

## Track E - Extraction honesty

**Status: partially started; individual items below.**

Extraction is where the tool's claims are made, so refinements here change
what the tool is entitled to say rather than how many things it finds.

### E1. Multi-page labels

Extraction already joins all pages of a PDF, and `page_count` travels with
every report. What does not exist is a synthetic multi-page fixture proving
that checks behave sensibly when a label's rows straddle a page boundary -
in particular that a wrapped heading reconstruction is attempted per page,
not across one. Small fixture, one test, closes a question before a real
two-page label asks it.

### E2. Vector-drawn text

The basis sentence already concedes that text drawn as vector paths is not
read. What could tighten this: counting the page's path-painting operators
the way `count_images` counts images, so the sentence can distinguish "this
page draws almost nothing but text" from "this page carries heavy vector
artwork". Same discipline as ADR 0003 - the count qualifies what an absence
finding means, it never decides one. An ADR first; the code is small once
the claim is settled.

### E3. OCR

Assessed as refused, and worth recording as an ADR rather than leaving it
to be re-litigated. The short case: OCR output is a model's guess at text,
which would put a probabilistic layer inside a tool whose value is that it
contains none, and would attach the tool's name to readings it cannot
attribute to the document. A scanned label fails closed today, loudly, and
a human renders the page and looks at it - which is the resolution the
calibration record itself used. Revisit only if someone produces an OCR
path whose errors are bounded and attributable, and then as a separately
labelled extraction mode with its own basis wording, never silently.

### E4. pypdf upgrade policy

pypdf is the only runtime dependency and extraction is the safety-critical
surface. Adopt an explicit policy: upgrades are their own commits, run the
full gate plus the cached-label fingerprint harness (Track H3) before and
after, and record the version bump in the changelog. Cheap to write down
now, and it makes every future upgrade boring instead of brave.

## Track F - Interface contracts

**Status: not started. No blocker.**

The JSON report is consumed by things other than humans the moment anyone
scripts this tool, so its shape is a public interface and should be treated
like the check identifiers already are.

1. **Schema versioning.** Add a `schema_version` field to the run report
   (start it at 1), so a consumer can tell a changed report from a broken
   one. Document the field in the README next to the exit codes.
2. **Contract tests.** Pin the exact top-level keys of the JSON report and
   the catalog output in a test, the way `tests/test_registry.py` pins
   identifiers. Any key added or removed then fails a test instead of a
   stranger's script.
3. **Machine-readable catalog.** `catalog --json`, emitting the same
   `CheckSpec` dicts the reports carry, so the gap analysis the catalog
   enables can be scripted without parsing terminal formatting.
4. **Exit-code contract.** Already documented and tested; extend the tests
   to cover the precedence combinations explicitly rather than incidentally.

## Track G - Distribution

**Status: not started. No blocker.**

Installation today is clone-plus-uv, which suits auditors and excludes
everyone else. Publishing to PyPI widens the audience without changing the
artifact: same wheel hatchling already builds, same offline guarantee,
since the tool gains no network behavior from being installable.

1. **Trusted publishing from the existing release workflow**, which already
   verifies the tag, reruns the gate at the tagged commit, and separates
   read authority from write authority. PyPI publishing is one more
   constrained job behind the same gate, not a new pipeline.
2. **Build provenance attestation** on the published artifacts.
3. **A `--version` flag**, which a packaged CLI needs and a git checkout
   never did.
4. **Python 3.14 support**: extend the CI matrix and classifiers once the
   locked dependencies confirm clean on it. `requires-python` is already
   `>=3.12`, so this is confirmation work, not compatibility work.
5. Keep the README's install section honest in both worlds: uv-from-git
   remains the auditable path, PyPI the convenient one.

## Track H - Test infrastructure

**Status: not started. No blocker.**

1. **Raise the coverage floor.** It stands at 90 percent. The modules where
   the remaining slack lives are the ones that decide what the tool can
   see. Raise to 95, then examine what is excluded before raising again;
   the point is that the number moves only when the exclusions have been
   argued with, not for the number.
2. **Property tests for the invariants the ADRs assert.** Two in particular
   are stated in prose and enforced nowhere mechanically:
   - Geometry can turn "cannot tell" into "found it" and can never produce
     a deviation (ADR 0008). A hypothesis test over generated span layouts
     holds for arbitrary inputs, not just hand-built ones.
   - Space-insensitive matching ignores where the extractor put spaces and
     never what sits between words. Property: `contains_ignoring_spaces`
     is true exactly when the words appear in order, for generated word
     sequences and generated space insertions.
3. **A cached-label regression harness.** A script, not part of the
   package, that runs the checker over whatever the local fetch cache
   holds and compares the `--fingerprint` output per document against a
   locally recorded expectation file. New contributors without the cache
   never notice it; anyone with the cache catches, before pushing, any
   change that alters a conclusion about a real label. Fingerprints
   exclude paths, timestamps and version by design, which is what makes
   them usable here.
4. **Malformed-PDF fuzzing**, light: generate truncated and mutated PDFs,
   assert only that every run exits 2 or 3 and never 0. The fail-closed
   property is currently proven on crafted inputs; this proves it on
   hostile ones.

## Track I - Documentation and community

**Status: continuous.**

1. **Keep this roadmap honest.** When an item's blocking event arrives or
   an item is refused, update this file in the same commit as the work or
   the refusal. A stale roadmap misstates the project worse than none.
2. **Anticipated ADRs**, so their numbers do not get assigned twice:
   0010 the 2026 trigger derivation (Track A); 0011 schema versioning
   policy (Track F); 0012 the OCR refusal (Track E3); the second-ruleset
   ADR when triggered (Track C).
3. **Auditor-facing documentation**: a short document aimed at someone
   verifying this tool rather than using it - how to reproduce a finding
   by hand, how to audit the catalog against the sources, what the tool
   refuses to conclude and why. Much of it exists across the ADRs and
   `docs/sources.md`; it wants collecting under one entry point.
4. **Outreach, with the affiliation line carried intact.** The tool is
   useful to researchers and to suppliers checking documents they were
   issued. Any sharing of it repeats, verbatim, the disclaimer that this
   project is not affiliated with or endorsed by the Energy Commission,
   and never summarizes findings about named suppliers.

---

## Sequencing

| When | What | Track |
| --- | --- | --- |
| Now | Interface contracts, test infrastructure, distribution, completeness sweep | F, H, G, D |
| Now | Extraction honesty items that need no external event | E1, E2, E3, E4 |
| After 2026-10-01, as data year 2025 labels publish | Trigger ADR, then PCL023 and PCL024; new-vintage calibration begins; watch for anything that unblocks PCL029 | A, B |
| On any regulation amendment | Second-ruleset ADR and registry | C |
| Continuously | Calibration batches toward ninety one; roadmap and ADR upkeep | B, I |

Tracks F, G and H are ordered before Track A's implementation phase on
purpose: the contract tests, the fingerprint harness and the widened
calibration set all make the moment the trigger checks land safer, and none
of them is waiting on anything.

## Refusals

Recorded so they stay decided. Each has been considered; each is refused
for a reason that still holds; reopening one means overturning its reason,
not resubmitting the idea.

- **Rankings, scorecards, leaderboards.** The tool reports which prescribed
  elements a document carries. Aggregating that into comparative judgment
  about named suppliers is the thing the README disclaims in its opening
  paragraphs.
- **Reading the spreadsheet published beside each label.** Decided in
  `docs/adr/0009`: it is an alternative rendering, not the label, and
  checking it produces five misleading deviations out of seven.
- **Bulk fetching of published labels.** `fetch_examples.py` rate limits
  and refuses bulk runs. Widening happens in deliberate, diverse batches,
  because the point of the set is judgment, not coverage statistics.
- **Positional attribution of contact details.** Settled in
  `docs/adr/0007`; nearness is not ownership, and no published source
  supplies a threshold. Column geometry (ADR 0008) took the one use of
  position that was defensible and fenced it.
- **Summing fuel mix columns against the displayed total.** PCL025's
  reason: whole percentages with no published rounding rule mean correctly
  rounded arithmetic fails an equality test, and any tolerance would be
  invented. The statewide column the Energy Commission itself supplies is
  off its displayed total on all twenty four labels read.
- **Any large language model anywhere in the pipeline.** Determinism is
  the product. Also settled empirically by the standards table: there is
  no AI surface to evaluate.

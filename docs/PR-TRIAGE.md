# Pull request triage

A read-only pass over the six open pull requests, made on 28 August 2026
against `origin/main` at `f81ff21`. Every claim below that could be checked
by running something was checked by running it. The last section separates
what was verified from what is taken on trust.

## The headline correction

**`main` is green.** It was reported red, from a semantic merge conflict that
interleaved two test classes into an unterminated docstring. The mechanism is
real and the description of it is accurate. The location is not: it is on
**PR #28's head branch**, not on `main`.

On `origin/main` at `f81ff21`:

| Evidence | Result |
| --- | --- |
| CI run 33139878623 (`CI`, push, `f81ff21`) | success |
| CI run 33139878615 (`Security scans`, push, `f81ff21`) | success |
| `ruff check .` over the archived tree | All checks passed |
| `ruff format --check .` | 47 files already formatted |
| `python -m pytest` | 374 passed |
| `python -m py_compile tests/test_checks.py` | exit 0 |

`tests/test_checks.py` on `main` is 448 lines and parses. Nothing needs
unbreaking before the queue can move.

The remedy was described as a push to PR #28's branch. That part is right. It
is the blast radius that was wrong: no other pull request inherits this red,
because it never reached `main`.

## The real syntax error, and where it lives

Branch `fix/ascii-digit-classes` at `3022f405`, which is PR #28's head.

```
invalid-syntax: Simple statements must be separated by newlines or semicolons
   --> tests/test_checks.py:393:8
    |
391 |     address as a website would report CONFORMS on a document that deviates.
392 | def _arabic_indic(text: str) -> str:
393 |     """Rewrite ASCII digits as ARABIC-INDIC DIGIT ZERO through NINE.
    |        ^^^^^^^
```

CPython reports the same defect from the other end:

```
  File "tests/test_checks.py", line 396
    stays ASCII and the linter's ambiguous-character rule does not have to be
                              ^
SyntaxError: unterminated string literal (detected at line 396)
```

`ruff check .` finds 108 errors on that branch, and pytest cannot collect
`tests/test_checks.py` at all. The CI log for run 33139871804 shows the same
first line under `uv run ruff check .`, so the local reproduction and the
remote failure are the same event.

### What actually happened

Line 391 is the last line of the prose in
`TestAWebAddressIsNotAnEmailAddress`'s docstring. Line 392 inserts
`def _arabic_indic` **before** that docstring's closing `"""`. So the class
docstring ends at the opening quotes of `_arabic_indic`'s docstring on line
393, and the remaining prose becomes bare code.

The damage goes past the docstring. The rebase collapsed two classes into
one:

- `TestAWebAddressIsNotAnEmailAddress` keeps only its opening line.
- Its `_doc` and `_run` helpers and all six of its tests now sit inside
  `TestDigitsTheToolCanActuallyRead`.
- `TestDigitsTheToolCanActuallyRead`'s own `_run` body was lost. All that
  survives of it is a dangling `return result.status, result.finding` at line
  469, stranded after the last test of the class that absorbed it.

### The two contributing branches

`TestAWebAddressIsNotAnEmailAddress` arrived with PR #26, merged as `b328bbf`.
`TestDigitsTheToolCanActuallyRead` is PR #28's own new class. PR #28's
merge base is `b328bbf`, so #28 was rebased onto #26 after #26 landed, and
the rebase interleaved two class bodies that were both appended to the end of
the same file. Each branch was green alone. Git produced no conflict markers,
because from its point of view both sides simply added lines at the end.

This is the "two pull requests appending to the end of the same file" hazard,
already fired once.

### The remedy, verified but not pushed

PR #29 carries an undamaged copy of exactly the block PR #28 mangled.
Rebuilding `tests/test_checks.py` as `main`'s intact 448 line file followed by
lines 415 to 506 of `tests/test_checks.py` from `origin/fix/pcl018-decimal-totals`
gives a clean tree: `ruff check` passes, `ruff format --check` passes, and 399
tests pass. `checks.py` and `tests/test_repo_hygiene.py` on #28 are already
correct and need no change.

This was reproduced in a scratch directory only. Nothing was pushed to #28.

## The queue

| PR | Title | Base | Real merge state | CI reality | Recommendation |
| --- | --- | --- | --- | --- | --- |
| #32 | The usage code the tool publishes, and five checks that could not fail | `main` | CLEAN, merges clean | Green, current | merge |
| #31 | docs: collect the auditor's entry point, and pin it to the tool | `main` | CLEAN, merges clean | Green, current | merge |
| #29 | fix: compare the total the label displays, not its nearest double (PCL018) | `main` | DIRTY, conflicts with `main` | Green, but on a two commit stale base | merge after rebase |
| #28 | fix: a pattern must not match digits the code cannot read | `main` | MERGEABLE, but merges a broken tree | Red on its own merits | needs work |
| #27 | fix: a bracket is not part of the requirement (PCL012) | `main` | CLEAN, merges clean | Green, but blind to the defect | needs work |
| #25 | deps: bump ruff from 0.16.3 to 0.16.4 | `main` | CLEAN, merges clean | Green, but stale by four commits | merge |

Group counts: two ready to merge as they stand (#31, #32), one ready with an
independent verification noted (#25), one needing a rebase (#29), two needing
a push before they are mergeable (#27, #28). One is red (#28), and its red is
entirely its own.

### #32, audit: checks that could not fail

Six commits. Two behavioural fixes and an audit that hunts tests unable to go
red.

The CLI returned argparse's exit code 2 for a usage error while
`ExitCode.USAGE_ERROR`, the README table at line 79, and the `--help` epilog
all published 64. Code 2 is also this tool's code for "at least one check
could not be evaluated", so a caller reading the published table could not
tell the two apart. Verified: the README table does say `| 64 | usage error |`
and the enum does define it. The fix overrides only `ArgumentParser.error`, so
`--help` and `--version` still exit 0.

`scripts/check_regressions.py compare` diffed the intersection of cache and
baseline but reported `len(current)`, so an empty intersection printed
"N documents conclude exactly as recorded" and exited 0, naming a count of
documents not one of which had been compared. Three open pull requests quote
that line as evidence, so its truthfulness is load-bearing for review here.

The audit findings are real and I confirmed both:

- `tests/test_hostile_inputs.py` carried `MUTATIONS = 120` while `_mutations`
  returned 23, and nothing read the constant.
- `assert len(conforms) < len(CHECKS)` could not fail. Seventeen of the
  thirty five registered checks enforce nothing and always report
  NOT_EVALUATED, so the left side has a ceiling of 18 against a right side of
  35, with a measured maximum of 8 over the mutation set.

Correctness: good. Reverting `cli.py` and `scripts/check_regressions.py` to
their `main` versions makes 9 of its new tests fail, so they are falsifiable
rather than decorative. Merged with `main` the tree is clean under ruff and
437 tests pass.

**merge**

### #31, docs: the auditor's entry point

Adds `docs/AUDITING.md` and `tests/test_auditing_doc.py`, which pins the
document to the tool rather than proofreading it: enumerations compared
against the model as exact reprs, every relative link and check identifier
and quoted repository path resolved, and the commands the document gives an
auditor executed rather than read. It supersedes closed PR #24, which listed
five result statuses where `model.py` defines three.

Correctness: good. Merged with `main` the tree is clean under ruff and 395
tests pass.

One coupling worth knowing about rather than fixing:
`test_the_counts_of_registered_and_unimplemented_checks` hardcodes
`len(CHECKS) == 35 and len(unimplemented) == 17` and requires the literal
phrase "Seventeen of the thirty five registered checks" in the document. That
is a deliberate tripwire, and its failure message says so. It does mean any
future pull request that registers a check must update `docs/AUDITING.md` in
the same commit.

**merge**

### #29, PCL018 decimal totals

`_PERCENT` places no limit on the digits after the point, and a double cannot
hold twenty of them. `float("99.999999999999999999") == 100.0` is True, which
I confirmed, so a displayed total that is not one hundred was reported as a
pass. Reading the figures as `Decimal` compares the figure the label
displays, and by value rather than by representation, so 100, 100.0 and
100.00 all still conform.

Correctness: good. Reverting only the `Decimal` change makes its three new
tests fail, and the eleven controls pass in both states.

Two things about this branch are not what its description says.

First, the body says "Stacked on #28 (`fix/ascii-digit-classes`), which is
its base". It is not.
`git merge-base --is-ancestor origin/fix/ascii-digit-classes origin/fix/pcl018-decimal-totals`
returns false. The two branches share merge base `f5c0736`, which is PR #20,
two commits behind `main`. What #29 actually carries is `cdcde9c9`, a
parallel earlier revision of the same digit class change that #28 carries as
`3022f405`. Same content, different base, made before PR #26 landed. So #29
is a cumulative snapshot by content and not by ancestry, and its `checks.py`
does not contain the `_EMAIL` pattern that #26 added.

Second, it conflicts with `main` today, in `CHANGELOG.md` and
`tests/test_checks.py`, and it conflicts with every other open pull request
in either order. The `tests/test_checks.py` conflict is the same end of file
region whose silent resolution broke #28. Here git does flag it, so a human
resolves it deliberately.

The rebase should drop the duplicated digit class commit, leaving only the
PCL018 decimal change. Do it after #28 lands, so the duplicate falls out
against an already applied change rather than being resolved by hand twice.

**merge after rebase**

### #28, ASCII digit classes

The defect is real and worth fixing. Python's `\d` matches every Unicode
decimal digit, and everything downstream of `_PERCENT`, `_PHONE` and
`_YEAR_TITLE` reads ASCII only. A telephone number in another numeral system
matched `_PHONE`, the ASCII only strip reduced it to the empty string, and
the empty string then counted as one of the two distinct numbers section
1393.1(c)(4) lists. PCL002 reported a pass on a document from which one
number had been read.

Correctness of the intent: good. Reverting `checks.py` makes six of its tests
fail, five behavioural and one from the repository scan, which names
`checks.py` lines 44, 47 and 58 exactly.

Correctness of the branch as it stands: it does not parse. See the section
above for the exact error and the verified remedy.

Note also that `tests/test_repo_hygiene.py` on this branch conflicts with
#32's changes to the same file in either merge order, because both append a
class at the end of it. Rebasing #28 after #32 lands resolves both problems
in one pass, and this time the conflict is one git reports.

**needs work**: rebase onto `main` after #32 lands, and restore
`tests/test_checks.py` so that `TestAWebAddressIsNotAnEmailAddress` keeps its
closing `"""` and its own helpers and tests, with `_arabic_indic` and
`TestDigitsTheToolCanActuallyRead` following it as separate top level
definitions. Lines 415 to 506 of the same file on `origin/fix/pcl018-decimal-totals`
are an undamaged copy of that block.

### #27, PCL012 annotation punctuation

The opening parenthesis was optional and the closing one was not, so the
pattern only ever matched an annotation ending in a literal `)`.
`Unspecified Power - primarily fossil fuels` matched nothing and fell through
to the branch reporting that the display is not annotated anywhere, which is
a false deviation against a document saying exactly what section 1393.1(c)(7)
asks. The subdivision prescribes no punctuation, unlike subdivision (l), so
the bracket was a rule this tool wrote.

The repair is careful about the looseness that dropping the bracket invites:
the group name is tested against the start of what follows "primarily" rather
than searched for inside it, so "primarily imported power from fossil fuels"
does not read as the fossil fuels group.

Correctness of the code: good. Reverting `checks.py` makes 7 of its 13 tests
fail. Merged with `main` the tree is clean under ruff and 384 tests pass.

**The problem is in the changelog, and no linter can see it.** The hunk lands
in the middle of an existing bullet. In the actual merge result, the
PCL003, PCL004 and PCL005 entry now ends:

```
  website matcher reads it. Conclusions about all ten cached published
- PCL012 (unspecified power annotation) required a closing parenthesis that
```

The email bullet is truncated mid sentence, and the new PCL012 bullet takes
over the orphaned "labels are unchanged." line as its own ending. Both
bullets are wrong and CI is green, because nothing reads prose for sense.

This is not the released section hazard. Every hunk in this queue lands under
`## [Unreleased]`, and `## [0.1.0]` does not begin until line 160. It is the
same end of file and adjacent text pressure that broke #28, showing up in
Markdown instead of Python.

**needs work**: reposition the changelog bullet so the PCL003, PCL004 and
PCL005 entry regains its closing "labels are unchanged." line and the PCL012
entry begins as its own bullet after it. The source change needs nothing.

### #25, ruff 0.16.3 to 0.16.4

`uv.lock` only, 19 lines each way, all of them the ruff entry.

Its green CI ran on 24 August 2026 against `f5c0736`, which is four commits
behind current `main`. That green proves nothing about today's tree, and a
ruff minor bump can introduce lint rules that turn a previously clean tree
red. So this was checked rather than assumed: ruff 0.16.4 was fetched and run
directly.

| Tree | `ruff check` | `ruff format --check` |
| --- | --- | --- |
| `origin/main` | passed | 47 files formatted |
| merged with #31 | passed | 49 files formatted |
| merged with #32 | passed | 51 files formatted |
| merged with #27 | passed | 47 files formatted |
| #29 head | passed | 47 files formatted |

`uv.lock` and `pyproject.toml` are untouched on `main` since #25's base, so
the lockfile diff still applies exactly. Safe to take as it stands.

**merge**

## Stacks

There are none. All six pull requests target `main`, and no branch is based
on another's head. **No open pull request would auto-close if any other
merged and its branch were deleted.**

What does exist is content overlap, which is not the same thing:

```
origin/main (f81ff21) GREEN
|
+-- #25  dependabot/uv/ruff-0.16.4      uv.lock only         no overlap
+-- #27  fix/pcl012-annotation-...      PCL012               no code overlap
+-- #31  docs/auditing-entry-point      docs and its tests   no overlap
|
+-- #32  audit/checks-that-cannot-fail  --+
+-- #28  fix/ascii-digit-classes  BROKEN  +-- all three append a class to the
+-- #29  fix/pcl018-decimal-totals STALE -+   end of tests/test_repo_hygiene.py
                                              or tests/test_checks.py

#29 contains a duplicate of #28's change:
    #28  3022f405  based on b328bbf (#26)   damaged by that rebase
    #29  cdcde9c9  based on f5c0736 (#20)   intact, but older
    Same content. Neither is an ancestor of the other.
```

The cumulative snapshot antipattern is present in a mild form: #29 delivers
#28's change as well as its own. It does not have the usual consequence,
because #29 is not a rebased superset sitting on top of #28. Merging #29
alone would deliver both changes and leave #28 showing a non empty but
redundant diff, which a squash merge would not auto-close.

### Conflict matrix

Computed with `git merge-tree --write-tree`, and for the ordered pairs by
building the first merge with `git commit-tree` and merging the second onto
it. This is independent of what the GitHub API reports.

| | vs #25 | vs #27 | vs #28 | vs #29 | vs #31 | vs #32 |
| --- | --- | --- | --- | --- | --- | --- |
| #25 | | clean | clean | conflict | clean | clean |
| #27 | clean | | clean | conflict | clean | clean |
| #28 | clean | clean | | conflict | clean | **conflict** |
| #29 | conflict | conflict | conflict | | conflict | conflict |
| #31 | clean | clean | clean | conflict | | clean |
| #32 | clean | clean | **conflict** | conflict | clean | |

`#28` against `#32` conflicts in `tests/test_repo_hygiene.py` in **either**
order. `#29` conflicts with `main` itself, and therefore with everything.

## Order of operations

`main` does not need unbreaking, so the queue can start with the merges that
are ready. The order below was simulated end to end, merging trees in
sequence and running ruff 0.16.4 and the full suite at each step.

1. **#25**, the ruff bump. First, so every later gate runs on the version the
   lockfile pins. No regeneration step: `uv.lock` is untouched on `main`
   since its base, and the diff still applies.

2. **#31**, the auditing document. Independent of everything.

3. **#27**, PCL012, **after its changelog bullet is repositioned**. The code
   needs nothing. Do not merge it before that push: the fix is a prose edit
   that CI cannot demand.

4. **#32**, the audit pass. Before #28 and #29, because it is clean against
   `main` today and both of the others must be rebased anyway. Merging it
   first means the `tests/test_repo_hygiene.py` collision is resolved once,
   by the branch that has to move regardless.

   Verified to here: `ruff check` and `ruff format --check` clean under ruff
   0.16.4, 468 tests pass.

5. **#28**, after the author pushes the `tests/test_checks.py` repair and
   rebases onto the new `main`. **This is the regeneration step in the
   sequence.** The rebase must be reviewed by eye and not accepted on a green
   check alone, because the current damage was produced by exactly this
   operation and git reported no conflict when it happened. Read the class
   boundaries in `tests/test_checks.py` before merging.

   Verified with the repair applied: clean under ruff, 493 tests pass.

6. **#29**, rebased last. The rebase should drop the duplicated digit class
   commit against #28's already applied change, leaving only the PCL018
   decimal fix, roughly eight lines of source. Its `CHANGELOG.md` and
   `tests/test_checks.py` conflicts must be resolved by hand.

   Verified with the decimal change applied: clean under ruff, 501 tests
   pass.

Merges needing a changelog reposition: **#27 only**. No other hunk in the
queue lands inside a released section or inside an existing bullet.

Merges needing a regeneration step: **#28 and #29**, both rebases, and #28's
is the one where the previous attempt at the same operation produced the
defect that made it red.

## Verified, and taken on trust

### Verified by running it

- `main` at `f81ff21` is green: two successful CI runs on that SHA, ruff check
  and format clean over the archived tree, 374 tests passing, and
  `tests/test_checks.py` compiling.
- The syntax error is on `fix/ascii-digit-classes` and not on `main`. Exact
  ruff and CPython messages quoted above, reproduced locally and matched
  against CI run 33139871804.
- The two contributing branches, from the merge base of #28 being `b328bbf`,
  which is the merge of #26.
- The structural damage beyond the docstring, by comparing the class and
  method layout of `tests/test_checks.py` across `main`, #28 and #29.
- The remedy for #28 produces a clean tree: 399 tests pass, ruff clean.
- #29 is not stacked on #28, by `git merge-base --is-ancestor` returning
  false, and their shared merge base being `f5c0736`.
- Every conflict and every clean merge in the matrix, by `merge-tree` and
  `commit-tree`, independent of the GitHub API.
- Every pull request's tests are falsifiable, by reverting each source change
  and re-running only that pull request's new tests. Failures observed: #27
  seven of thirteen, #28 six, #29 three, #32 nine. **No vacuous or
  unfalsifiable test was found in any open pull request.**
- #32's two audit claims about `main`: `MUTATIONS = 120` against a function
  returning 23, and `len(conforms) < len(CHECKS)` having a ceiling of 18
  against 35.
- #32's exit code claim, against the README table and the `ExitCode` enum.
- `float("99.999999999999999999") == 100.0` is True and
  `Decimal("100.00") != 100` is False, which is what #29 rests on.
- #27's changelog corruption, read out of the actual merge result rather than
  inferred from the diff.
- The ruff 0.16.4 bump is safe, by fetching that exact version and running it
  against `main` and every merge result.
- The full merge sequence, simulated tree by tree with the gate run at each
  step.

### Taken on trust

- That the CI workflow's gate is the same set as `make verify`. The
  `Makefile` and `ci.yml` agree on the tools, but bandit and pip-audit were
  not run here, so "green" below means ruff plus pytest, not the security
  scanners.
- The regulatory readings. That section 1393.1(c)(7) prescribes no
  punctuation while subdivision (l) sets its footnote out verbatim, and that
  section 1393.1(c)(4) lists two telephone numbers, are quoted from the pull
  requests and from citations already in the tree. No published source was
  fetched for this triage, and per the repository's own first rule they
  should be read before either fix is accepted on that reasoning.
- That conclusions about the ten cached published labels are unchanged. Every
  pull request claims this and `scripts/check_regressions.py` is the
  mechanism, but the cache is uncommitted by design and was not available
  here. Note that #32 exists partly because that script could report a pass
  having compared nothing, so for #27, #28 and #29, all of which predate it,
  the claim rests on a script whose reassurance was not yet trustworthy.
- Coverage floor and mypy strict results, neither of which was run.
- That the calibration counts, 35 registered and 17 unimplemented, are
  correct. #31's test asserts them, so they are pinned; they were not
  independently recounted from the regulation.

# Improvement plan

Working document for an audit pass over this repository. Nothing here is
committed: every change described below is left unstaged in the working tree,
because commit permission was withheld for this pass. That also means this
file is the only durable record of what was done, so it is kept current as
work proceeds.

## Standing constraints for this pass

- No commit, no push, no pull request, no repository settings change. Nothing
  that moves HEAD, the index, or the working tree's tracked state.
- The working tree sits at `f5c0736`, two commits behind `origin/main`
  (`b328bbf` "an email address is not a website address" (#26) and `f81ff21`
  "say what the record supports, and say what it does not" (#30)). Those two
  are therefore NOT present locally. Nothing in this pass touches what they
  changed, so the diff should rebase onto `origin/main` cleanly, but that
  rebase is an owner action.
- Four of the five open pull requests already carry fixes. Nothing here
  duplicates them.
- Never invent a requirement, a threshold, or a citation. Where a claim needs
  a published source and none was found, the claim is not made.

## Where the open work already sits

| Issue | Classification | Covered by |
| --- | --- | --- |
| #21 PCL018 float equality | real defect, verified | PR #29 (stacked on #28) |
| #15 PCL012 closing paren | real defect, verified | PR #27 |
| #13 PCL023/PCL024 for data year 2025 | aspiration, externally blocked | none, and correctly so |
| #12 widen the calibration set | aspiration, ongoing | none |
| #11 auditor entry point | missing feature (docs) | PR #31 |
| #10 PyPI trusted publishing | aspiration, owner action first | none |

PR #25 is a dependabot ruff bump and carries no project code.

Because every filed defect already has an open fix, the work in this pass is
the work nobody filed: the CI failure, and a hunt for checks that cannot fail.

## CI

One failure in the last twenty runs: run 33139871804, CI on PR #28's merge
ref. Diagnosed in phase 0 below. Not an upstream advisory; the security
workflow passed on the same commit. No gate is waived, silenced or narrowed
anywhere in this pass.

## Phases

### Phase 0. Diagnose the CI failure (no code change here)

`refs/pull/28/merge` (`101dce7`) does not parse. Both `main` (through #26) and
`fix/ascii-digit-classes` (#28) append a new test class to the end of
`tests/test_checks.py`, immediately after `class TestGhgUnits`. Git auto
merged the two additions by interleaving them, with no conflict markers: #26's
`class TestAWebAddressIsNotAnEmailAddress` opens a docstring that is never
closed, #28's `_arabic_indic` helper and `class TestDigitsTheToolCanActuallyRead`
land inside it, and #26's test methods end up as the body of #28's class. Ruff
reports `invalid-syntax` at `tests/test_checks.py:411` and the Lint step exits
1 on all three Python versions.

This is a textbook silent auto-merge, not a defect in either branch: PR #28
passed CI at 03:21 against the older main and failed at 03:46 against the
newer one, having not changed. The remedy is on the PR branch and needs a
push, so it is escalated rather than attempted. Status: **blocked, escalated.**

### Phase 1. A documented exit code the tool never returns

`ExitCode.USAGE_ERROR = 64` is declared in `model.py`, tabulated in the README
exit-code table, printed in the CLI's own `--help` epilog, and given a meaning
in `report._exit_meaning`. The tool never returns it. Every usage error exits
2, which is argparse's default, and the two tests that cover usage errors
assert 2, so they pin the behaviour against its own published contract instead
of holding it to it. Fix: make the parser honour the code the tool documents.

### Phase 2. An assertion whose ceiling is unreachable

`tests/test_hostile_inputs.py::test_no_mutation_lets_a_document_read_as_clean_without_checks`
asserts `len(conforms) < len(CHECKS)`. Seventeen of the thirty five registered
checks enforce nothing and always report NOT_EVALUATED, so the left side has a
ceiling of 18 against a right side of 35. Measured maximum over the mutation
set is 8. The assertion cannot fail, in this catalog or any catalog with a
single unimplemented check. Replace it with the invariant it was reaching for,
in a form that can go red.

### Phase 3. Two mutation loops with no denominator

Both tests in `tests/test_hostile_inputs.py` `continue` past every unreadable
mutant. If a pypdf bump made every mutant unreadable, both would pass having
asserted nothing, silently. Measured today: 12 of 23 and 13 of 23 mutants are
readable. Assert the denominator, the way `test_repo_hygiene` already does for
its file list and `test_fail_closed` does for the empty run.

Also: `MUTATIONS = 120` in that module is unused and untrue. `_mutations`
yields 23.

### Phase 4. The security-gate guard cannot see the way a gate is actually silenced

`test_no_security_gate_is_silenced` scans workflow lines and fires only when a
muting token and a tool name occur on the same line. The ordinary way to
silence a step is `continue-on-error: true` on its own line under the step,
which the guard cannot see. It also globs `*.yml` only, and never opens the
`Makefile`, where `make verify`'s own bandit and pip-audit invocations live.
Widen it to the step, to both YAML suffixes, and to the Makefile.

### Phase 5. The lockfile guard only forbids one spelling

`test_dependencies_are_installed_from_the_lockfile` asserts `uv sync --frozen`
is absent and never asserts `uv sync --locked` is present, so a workflow that
dropped to a bare `uv sync` passes. Assert the positive.

### Phase 6. The dash gate never opens the extensionless files

`tracked_text_files()` selects on suffix, so `Makefile` and `CODEOWNERS` are
never scanned, while `scripts/check_no_dashes.py`, which pre-commit runs, has
no suffix filter at all. The two disagree about scope and the one test that
compares them only compares two temporary files. Bring the named extensionless
files into scope.

### Phase 7. A regression script that can report a pass having compared nothing

`scripts/check_regressions.py compare` computes `changed` over the intersection
of current and recorded digests. When that intersection is empty it prints
"N documents conclude exactly as recorded" and exits 0, naming a count of
documents none of which were compared. Three of the open PRs quote this
script's output as evidence that no published conclusion moved, so its
truthfulness is load bearing for review. Make an empty comparison say so and
refuse to pass.

### Phase 8. Stale counts in prose that describes the tool

`tests/test_cli.py::TestPrecedence` says "the twelve checks that enforce
nothing"; there are seventeen. Correct it.

### Phase 9. A refusal the README publishes and nothing enforced

`scripts/fetch_examples.py` is the one thing here that touches the network,
and the README claims it "honours robots.txt, rate limits itself, and refuses
to fetch in bulk". CONTRIBUTING lists bulk fetching among the things this
project will not accept. No test referenced the script at all, so the cap
could have been raised, the robots.txt call deleted, the fail-closed treatment
of an unreadable robots.txt inverted, or the pause dropped, with every gate
still green. Tested offline, with the script's own `urlopen` replaced and the
replacement asserting that no test reaches the network.

### Phase 10. The offline claim itself

The README's headline safety claim, "The tool is offline. It opens the files
you name and nothing else. No network call, no telemetry, no account, no
configuration file, no cache", was enforced nowhere. An `import
urllib.request` inside a check function would have passed lint, types, bandit
and the whole suite. The package's own imports are now read off the source
with `ast`, function-local imports included, because this codebase writes most
of its imports inside functions and a rule that read only the top of each file
would have missed the one place a network call would plausibly be written.

### Phase 11. `set +e` with nothing that reads the code

CI turns errexit off in one step, correctly, so that it can read the exit code
of a run expected to be non-zero. Delete the line that compares it and the
step runs the tool and ignores the answer, still green. That pairing is now
asserted, and so is the existence of the step it protects, since a rule about
how a step is written buys nothing if the step can simply go.

## What was considered and not done

- **A `set +e` block parser.** A YAML-aware rule scoped to the individual step
  would be more precise than the file level one written in phase 11. PyYAML is
  not a dependency, adding it means relocking, and a hand written block
  splitter is itself fragile, which is the wrong property for a gate. The file
  level rule has no blind spot; it is only coarse.
- **Anything in issues #10, #12 and #13.** Blocked outside the repository,
  see the report below.
- **Anything covered by PRs #27, #29 and #31.** Duplicating an open fix is
  worse than leaving it.

## Running log

- Read README, CONTRIBUTING, the twelve ADRs' index, both gate scripts, all
  three workflows, all of `src/`, all of `tests/`. No `CLAUDE.md` exists in
  this repository.
- Baseline `make verify`: exit 0, 369 passed, coverage 96.64 percent against a
  floor of 96.
- Verified issue #15 empirically: three unparenthesised annotations that carry
  the required words all report `does_not_conform`. The issue's reproduction is
  accurate.
- Verified issue #21 empirically: `Total 99.999999999999999999%` reports
  `conforms`. The issue's reproduction is accurate.
- Diagnosed the CI failure from the run log and the merge ref's file content.
- Phases 1 through 11 executed. Phase 0 is diagnosed and escalated; it cannot
  be executed here because the remedy is a push to PR #28's branch.
- Final `make verify < /dev/null`: exit 0. 432 tests, up from 369. Coverage
  96.65 percent against the floor of 96. Lint, format, mypy strict over 30
  files, bandit and pip-audit all clean.
- Every guard added or repaired was broken deliberately, watched fail, and
  restored. Nineteen break results are recorded in the report that accompanies
  this file. Where a guard replaced one that could not fail, the old guard was
  also run against the same break, to show it stayed green.
- No gate was waived, silenced, narrowed or given an exception anywhere in
  this pass.

## Merge notes for whoever lands this

- `tests/test_repo_hygiene.py` is also touched by PRs #28 and #29, which each
  append a class to the end of the file. This pass edits the module header and
  `TestWorkflowHardening`, and appends `TestTheMakefileGate`. That last
  addition will conflict textually with #28's appended `TestDigitClasses`.
  Both are wanted; the resolution is to keep both classes.
- `CHANGELOG.md` is touched by everything. The Unreleased "Fixed" entries
  added here sit above the existing PCL018 entry and are independent of it.
- Nothing in this pass touches `src/power_content_check/checks.py`, which is
  where PRs #27, #28 and #29 all work, or `docs/`, where #31 works, beyond
  this new file under `docs/plans/`.

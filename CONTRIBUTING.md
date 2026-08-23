# Contributing

## The one rule that outranks the rest

**Never invent a required field, a format rule, a threshold, or a citation.**

Every check enforces something a published document actually says, and carries
a citation to it. A conformance checker that cites an invented requirement is
worse than no checker at all, because conformance is precisely the claim it is
making. If you cannot find the requirement in a published source, the check
does not get written. Register it as unimplemented with an honest reason
instead. That is what ten of the current checks are.

## Getting set up

```bash
uv sync --locked
make verify
```

`make verify` runs lint, formatting, strict type checking, the test suite
against its coverage floor, and the security scanners. It must exit 0 before
anything is pushed. CI runs the same gate.

## Adding a check

1. **Find the requirement.** Fetch the source yourself. Read the operative
   sentence. Do not work from memory or from a summary.

2. **Record the source** in `src/power_content_check/citations.py` if it is not
   already there, with its URL, its publisher, its effective date if it has
   one, and the date you retrieved it. Add it to `docs/sources.md` too, with a
   note on what it yielded.

3. **Take the next identifier.** Identifiers are permanent. Never renumber,
   never reuse. `tests/test_registry.py` pins the full set and the full
   title map, so adding a check means appending to both.

4. **Choose a basis honestly.**
   - `REGULATION_TEXT` when the regulation enumerates the element in words.
   - `TEMPLATE_FORMAT` when the element is part of the format the California
     Energy Commission issues rather than a sentence of regulatory text.

   If it is neither, you do not have a check yet.

5. **Quote the source, do not paraphrase it.** The `quote` field is transcribed
   from the document. Trim at a sentence boundary if it is long. Never reword.

6. **Decide what happens when you cannot tell.** A check that cannot measure
   something returns `NOT_EVALUATED`. It never returns `CONFORMS` as a default.

7. **Write the finding as a statement about the document.** Not about the
   supplier. "The words 'Energy Commission' do not appear in the label text" is
   the right register. Anything that reads as an accusation is not.

8. **Test both directions**, and test that prose cannot satisfy a check that is
   about a row of a table. There are existing examples in
   `tests/test_checks.py::TestNarrowMatching`.

## Registering a check that enforces nothing

This is a first-class outcome, not a failure. Use `_registered_only` and write
a specific reason. "Not implemented yet" is not a reason. "Whether any customer
is served by a mixture of portfolios is a fact about the supplier's service,
not about the document" is.

## Things this project will not accept

- Ranking suppliers, scoring them against each other, or producing a
  leaderboard.
- Any output that reads as a compliance determination. Only the California
  Energy Commission can make one.
- Editorial content about anyone's energy sources.
- Copy implying endorsement by, affiliation with, or approval from the Energy
  Commission or any utility.
- Copy implying users, adopters, downloads, or production scale.
- Bulk fetching of published labels.
- Committing a published label into the repository. Test fixtures are
  synthetic.
- Em dashes and en dashes.

## Style

- Format and lint with ruff. Type check with mypy in strict mode.
- Coverage floor is 90 percent and the complexity ceiling is 10. Both are
  configured in `pyproject.toml`.
- Comments explain why, not what.

## Upgrading pypdf

pypdf is the only runtime dependency and extraction is the safety-critical
surface, so its upgrades get their own commit and are never folded into work
that touches checks.

1. Bump the floor in `pyproject.toml` and relock. One dependency, one commit,
   a message that names the version.
2. Run `make verify`. The gate covers the fail-closed properties, but note
   what it cannot cover: `geometry.py` reads pypdf's layout machinery from
   below its public surface precisely because the surface folds lines (see
   ADR 0008), so a version bump can take column reconstruction away. That
   failure mode is safe - PCL016 goes back to not evaluated - but it is also
   silent, which is why a test asserts positioned text still yields on a real
   PDF. If that test fails, stop: either pin the previous version or fix
   forward, never delete the test.
3. Record the bump in the changelog under Changed, even though it is only a
   floor move. Consumers of the lockfile are entitled to know it moved.

## Commits and pull requests

Describe the change by what it does. Keep the changelog's Unreleased section
current in the same commit as the change it describes.

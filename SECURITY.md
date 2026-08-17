# Security policy

## Reporting a vulnerability

Report privately through
[GitHub security advisories](https://github.com/ChelseaKR/power-content-check/security/advisories/new).

Please do not open a public issue for a vulnerability.

Expect an acknowledgement within seven days and an assessment within thirty.
There is no bounty.

## Supported versions

The most recent release is the supported one. This project is at 0.x, so a fix
may arrive as a minor version rather than a patch.

## What this tool touches

Understanding the attack surface is short work, because there is very little of
it.

- **Network.** None. The CLI makes no network call of any kind. There is no
  telemetry, no update check, no crash reporting, no account, and no remote
  configuration. `scripts/fetch_examples.py` is the single exception, is not
  part of the package, is never invoked by the CLI, and only fetches URLs you
  pass to it.
- **Filesystem.** Read only, and only the paths given on the command line.
  Nothing is written except what is printed to standard output.
- **Execution.** No subprocess is spawned. No code from an input document is
  evaluated.
- **Credentials.** None are read, stored, or needed.

## Threat model

The realistic risks are:

1. **A malformed or hostile PDF.** Parsing is done by `pypdf`, a pure Python
   library. A crafted document could attempt resource exhaustion or trigger a
   parser bug. Extraction is wrapped so that any failure becomes an unreadable
   verdict rather than a traceback, but running the tool on untrusted documents
   in a sandbox with a memory limit is still the sensible posture.

2. **A wrong answer presented confidently.** For a conformance checker this is
   the more serious failure, because the output is a claim about whether a
   document meets a published requirement. Two properties address it directly,
   and both are tested:

   - A document the tool could not read is reported as not evaluated, never as
     conforming.
   - Checking zero documents exits 3 and prints `NOTHING CHECKED`, rather than
     reporting success against an empty denominator.

   A finding that cites a requirement the source does not contain would be a
   defect of the same class. Report it the same way.

## Supply chain

- Dependencies are locked in `uv.lock` and installed with `uv sync --locked`.
- Every GitHub Action is pinned to a full commit SHA with the version in a
  trailing comment.
- Workflows declare a top-level least-privilege `permissions:` block; only the
  release publishing job holds `contents: write`, and that job never checks out
  a working tree.
- `pip-audit`, `bandit` and `gitleaks` run on every push and pull request and
  weekly on a schedule. None of them is allowed to swallow a failure.

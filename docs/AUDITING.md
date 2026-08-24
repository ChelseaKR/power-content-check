# Auditing Guide

This document is for an auditor, researcher, or contributor verifying the findings
emitted by `power-content-check`. It explains how the tool evaluates a Power
Content Label, how to reproduce any finding by hand, how to audit the catalog
against its primary legal sources, and what conclusions the tool deliberately
refuses to make.

---

## 1. Core Operating Principles

This tool is built around structural conformance, deterministic evaluation, and
strict adherence to source regulations. Every finding is governed by the
following invariants:

1. **Every check cites a primary requirement**: No rule is invented. Every check in
   `src/power_content_check/checks.py` links to a specific subdivision in the
   regulations (20 CCR § 1391 et seq. or PUC § 398.4) via `citations.py`.
2. **Properties of documents, not suppliers**: Findings describe structural elements
   present or absent in a specific document. The tool does not evaluate compliance,
   does not assess supplier performance, and does not score or rank suppliers.
3. **Fail closed**: If a document cannot be read or parsed safely, the tool reports
   an unreadable error and refuses to emit passes. An unverified element is never
   assumed clean (see `docs/adr/0001-fail-closed-on-unreadable-documents.md`).
4. **Deterministic and offline**: No network calls during checking, no heuristics,
   and no machine learning / probabilistic models. Identical input bytes produce
   identical JSON/terminal reports.

---

## 2. Reproducing a Finding by Hand

To verify any finding reported by `power-content-check` against a physical or PDF
label, follow these steps:

### Step A: Extract Document Text and Structure
Run the CLI inspection command or extract plain text from the PDF:
```bash
# Get machine-readable check results with citation pointers
uv run power-content-check check path/to/label.pdf --json

# List the full catalog of registered requirements
uv run power-content-check catalog --json
```

### Step B: Inspect the Cited Authority
1. Identify the check code in the report (e.g. `PCL001`, `PCL007`, `PCL012`).
2. Locate the citation in `src/power_content_check/citations.py` and
   `docs/sources.md`.
3. Open the primary regulation text (20 CCR § 1393.1) and read the exact statutory
   mandate.

### Step C: Verify Extraction and Normalization
1. Check whether the element is present as text within the PDF stream.
2. Review Unicode normalization: text matching folds case and normalizes
   whitespace (`normalize.py`), but does not invent missing words.
3. For tabular values (such as fuel mix percentages or emissions metrics), check
   column alignment:
   - The tool groups tokens by spatial coordinates into rows and columns
     (`geometry.py` and `docs/adr/0008-column-geometry-decides-which-cell.md`).
   - Confirm that the number appears within the bounding box / horizontal interval
     of the corresponding fuel category.

---

## 3. Auditing the Catalog Against Sources

Every check belongs to one of three categories defined in `docs/sources.md` and
`docs/adr/0005-say-whether-a-gap-can-ever-close.md`:

- **Implemented**: Fully evaluated against the document text or tabular geometry.
- **Conditional**: The requirement depends on conditions not yet active or
  resolvable (e.g. 2026-trigger provisions under 20 CCR § 1393.1(c), tracked in
  `docs/ROADMAP.md` Track A).
- **Permanent Gap**: The requirement cannot be verified from the four corners of a
  single label PDF alone (e.g., verifying whether a supplier mailed the label to
  all customers under 20 CCR § 1393.1(a), or comparing promotional materials under
  PUC § 398.4).

To audit catalog completeness:
- Compare `src/power_content_check/checks.py` against `docs/sources.md` (Primary
  Regulations section).
- Check `tests/test_registry.py` to confirm that all 35 registered checks are
  accounted for and that no check is added without a valid citation.

---

## 4. Understanding Evaluation States

The tool outputs five distinct check statuses:

| Status | Meaning | Resolves to Pass? |
| --- | --- | --- |
| `pass` | The required element or structure was found in the document. | Yes |
| `deviation` | A prescribed requirement was expected but is absent or mismatched. | No |
| `not_evaluated` | The check is registered but cannot be evaluated from this PDF alone. | No |
| `conditional` | The rule applies only under specific triggers not present here. | No |
| `error` | Extraction or document parsing failed. | No |

### Why "Not Evaluated" Never Resolves to Pass
As documented in `docs/adr/0001-fail-closed-on-unreadable-documents.md` and
`docs/adr/0005-say-whether-a-gap-can-ever-close.md`, silence is not evidence of
compliance. If the tool lacks the data or technical surface to verify a rule
(such as promotional consistency or off-document marketing), it emits
`not_evaluated`. The report summary explicitly tracks unevaluated checks so an
auditor knows which items require separate human verification.

---

## 5. Extraction Honesty and Basis Disclosures

Every report includes an **extraction basis sentence** that states exactly what the
tool was able to observe in the PDF.

### A. Vector Shapes and Declared Images
- The basis records the count of declared image XObjects and painted vector
  shapes (`docs/adr/0012-the-basis-counts-what-the-page-paints.md`).
- A high number of painted shapes or raster images indicates that portions of the
  document may be rendered as graphics rather than structured text.

### B. OCR Refusal
- The tool strictly **refuses** Optical Character Recognition (OCR)
  (`docs/adr/0011-no-recognition-of-pictures.md`).
- OCR introduces probabilistic guesses into an otherwise deterministic tool. If a
  label is scanned or baked into a bitmap, the tool fails closed and reports the
  absence of extractable text rather than guessing characters.

---

## 6. What the Tool Refuses to Conclude

Auditors must note the boundaries established across the architecture decisions:

1. **No Supplier Ranking or Scorecards**: The tool does not compare utilities or
   rank clean energy portfolios (`README.md`).
2. **No Positional Contact Attribution**: A phone number or URL is evaluated for
   existence, but not attributed to a specific entity based merely on geometric
   proximity (`docs/adr/0007-position-does-not-decide-ownership.md`).
3. **No Unofficial Spreadsheets**: The tool evaluates only the official label PDF,
   not auxiliary spreadsheets (`docs/adr/0009-the-second-file-is-not-this-tools-subject.md`).
4. **No Re-rounding or Tolerances**: The tool does not adjust published figures or
   invent rounding tolerances when checking percentage totals (`PCL025`).

---

## 7. Calibration Record and Extending the Set

The tool is calibrated against real California Power Content Labels fetched from
the Energy Commission's public docket:

- The calibration methodology and results for each batch are recorded in
  `docs/sources.md`.
- To extend the calibration set, use `scripts/fetch_examples.py` (which obeys
  rate limits and robots.txt) and inspect geometry using `scripts/inspect_artwork.py`.
- Regression baselines are maintained via `scripts/check_regressions.py` to ensure
  no parser adjustment quietly alters conclusions on previously calibrated labels.

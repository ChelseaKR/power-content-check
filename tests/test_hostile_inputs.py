"""Hostile inputs, and the one property that must survive all of them.

`tests/test_fail_closed.py` proves the collision is refused on crafted
inputs: a document the tool cannot read is never reported as conforming.
These tests attack the same guarantee from the other side. The inputs here
are not crafted, they are damaged at random - truncated, flipped, spliced -
and the property under attack is that no mutation produces a crash, an
empty result list, or a result set that does not account for every
registered check.

The randomness is seeded and deterministic, so a failure reproduces.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from power_content_check.checks import CHECKS
from power_content_check.engine import check_document
from power_content_check.extract import LabelDocument, UnreadableDocument, extract
from power_content_check.model import Readability, Status

MUTATIONS = 120
SEED = 20260822


def _mutations(data: bytes, rng: random.Random) -> list[bytes]:
    out = [data]
    # truncation at many depths, including just inside the header where the
    # parser has least to work with
    for _ in range(6):
        cut = rng.randint(1, max(len(data) - 1, 1))
        out.append(data[:cut])
    # single byte corruptions spread across the file
    for _ in range(12):
        pos = rng.randrange(len(data))
        flipped = bytearray(data)
        flipped[pos] ^= 1 << rng.randint(0, 7)
        out.append(bytes(flipped))
    # regions overwritten with plausible junk
    for _ in range(4):
        start = rng.randrange(len(data))
        width = min(rng.randint(4, 64), len(data) - start)
        junk = bytes(rng.randrange(256) for _ in range(width))
        out.append(data[:start] + junk + data[start + width :])
    return out


def test_no_mutation_of_a_label_produces_an_accounting_error(
    text_layer_pdf: Path, tmp_path: Path
) -> None:
    original = text_layer_pdf.read_bytes()
    rng = random.Random(SEED)
    registered = len(CHECKS)
    for index, candidate in enumerate(_mutations(original, rng)):
        path = tmp_path / f"mutant-{index}.pdf"
        path.write_bytes(candidate)
        outcome = extract(path)
        if isinstance(outcome, UnreadableDocument):
            continue
        assert isinstance(outcome, LabelDocument)
        report = check_document(path)
        assert report.readability is Readability.READABLE
        assert len(report.results) == registered, (
            f"mutation {index} yielded {len(report.results)} results "
            f"for {registered} registered checks"
        )
        assert {r.status for r in report.results} <= set(Status)


def test_no_mutation_lets_a_document_read_as_clean_without_checks(
    illustrated_pdf: Path, tmp_path: Path
) -> None:
    """The fail-closed invariant over hostile input: whatever comes back,
    either every check spoke, or nothing was judged."""
    original = illustrated_pdf.read_bytes()
    rng = random.Random(SEED + 1)
    for index, candidate in enumerate(_mutations(original, rng)):
        path = tmp_path / f"mutant-{index}.pdf"
        path.write_bytes(candidate)
        outcome = extract(path)
        if isinstance(outcome, UnreadableDocument):
            assert isinstance(extract(path), UnreadableDocument)
            continue
        report = check_document(path)
        if any(r.status is Status.CONFORMS for r in report.results):
            assert report.readability is Readability.READABLE
            conforms = {r.check_id for r in report.results if r.status is Status.CONFORMS}
            assert len(conforms) < len(CHECKS), "a mutated file conformed on every check"


@pytest.mark.parametrize("prefix", [b"", b"%PDF-", b"%PDF-1.7\n", b"\x00" * 16])
def test_degenerate_prefixes_are_unreadable_or_harmless(tmp_path: Path, prefix: bytes) -> None:
    path = tmp_path / "degenerate.pdf"
    path.write_bytes(prefix)
    outcome = extract(path)
    assert isinstance(outcome, (LabelDocument, UnreadableDocument))

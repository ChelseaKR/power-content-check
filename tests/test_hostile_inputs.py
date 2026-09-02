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

from power_content_check.checks import CHECKS, implemented_checks
from power_content_check.engine import check_document
from power_content_check.extract import LabelDocument, UnreadableDocument, extract
from power_content_check.model import Readability, Status

SEED = 20260822

#: How many mutants of each shape ``_mutations`` produces, beside the one
#: unmutated copy it starts with.
#:
#: Written here rather than inline because the module used to carry
#: ``MUTATIONS = 120`` while ``_mutations`` returned 23, and nothing read the
#: constant, so the file overstated its own strength with no gate on the
#: claim. These three are the numbers the function uses, and
#: :func:`test_the_mutation_set_is_the_size_this_module_claims` holds them to
#: what it returns.
TRUNCATIONS = 6
BIT_FLIPS = 12
SPLICES = 4
MUTATION_COUNT = 1 + TRUNCATIONS + BIT_FLIPS + SPLICES

#: Below this many readable mutants, a run of these tests has stopped
#: exercising the property rather than passing it.
#:
#: Every assertion below sits inside a loop that skips a mutant the extractor
#: refuses, which is correct: an unreadable mutant is the safe outcome and
#: there is nothing to check about it. But it also means that if a pypdf
#: upgrade made pypdf refuse every damaged file, both tests would pass having
#: asserted nothing at all, and would keep passing, silently. That is the
#: failure this floor exists to catch, and it is the same reason
#: ``test_repo_hygiene`` counts its files and ``test_fail_closed`` refuses an
#: empty run.
#:
#: The two fixtures yield 12 and 13 readable mutants as this is written, so
#: the floor sits well below the observed figure and well above zero. It is a
#: bound on vacuity, not a measurement of extraction quality, and no published
#: source supplies it.
MIN_READABLE = 5


def _mutations(data: bytes, rng: random.Random) -> list[bytes]:
    out = [data]
    # truncation at many depths, including just inside the header where the
    # parser has least to work with
    for _ in range(TRUNCATIONS):
        cut = rng.randint(1, max(len(data) - 1, 1))
        out.append(data[:cut])
    # single byte corruptions spread across the file
    for _ in range(BIT_FLIPS):
        pos = rng.randrange(len(data))
        flipped = bytearray(data)
        flipped[pos] ^= 1 << rng.randint(0, 7)
        out.append(bytes(flipped))
    # regions overwritten with plausible junk
    for _ in range(SPLICES):
        start = rng.randrange(len(data))
        width = min(rng.randint(4, 64), len(data) - start)
        junk = bytes(rng.randrange(256) for _ in range(width))
        out.append(data[:start] + junk + data[start + width :])
    return out


def test_the_mutation_set_is_the_size_this_module_claims(text_layer_pdf: Path) -> None:
    """The constant describes the function, rather than sitting beside it."""
    generated = _mutations(text_layer_pdf.read_bytes(), random.Random(SEED))
    assert len(generated) == MUTATION_COUNT


def test_no_mutation_of_a_label_produces_an_accounting_error(
    text_layer_pdf: Path, tmp_path: Path
) -> None:
    original = text_layer_pdf.read_bytes()
    rng = random.Random(SEED)
    registered = len(CHECKS)
    readable = 0
    for index, candidate in enumerate(_mutations(original, rng)):
        path = tmp_path / f"mutant-{index}.pdf"
        path.write_bytes(candidate)
        outcome = extract(path)
        if isinstance(outcome, UnreadableDocument):
            continue
        assert isinstance(outcome, LabelDocument)
        readable += 1
        report = check_document(path)
        assert report.readability is Readability.READABLE
        assert len(report.results) == registered, (
            f"mutation {index} yielded {len(report.results)} results "
            f"for {registered} registered checks"
        )
        assert {r.check_id for r in report.results} == {c.spec.id for c in CHECKS}
    assert readable >= MIN_READABLE, (
        f"only {readable} of {MUTATION_COUNT} mutants were readable, so this test "
        "asserted almost nothing; see MIN_READABLE"
    )


def test_no_mutation_lets_a_document_read_as_clean_without_checks(
    illustrated_pdf: Path, tmp_path: Path
) -> None:
    """The fail-closed invariant over hostile input: whatever comes back,
    either every check spoke, or nothing was judged.

    The count this used to assert, ``len(conforms) < len(CHECKS)``, could not
    fail. Seventeen of the thirty five registered checks enforce nothing and
    always report NOT_EVALUATED, so the left side has a ceiling of eighteen
    against a right side of thirty five, and the measured maximum over this
    mutation set is eight. It would have stayed unfalsifiable under any
    catalog holding one unimplemented check.

    What it was reaching for is held here instead, as membership rather than
    as a count: a check that enforces nothing never reports CONFORMS, whatever
    damage was done to the file. That has a reachable boundary, so breaking
    the engine's unimplemented branch turns it red.
    """
    original = illustrated_pdf.read_bytes()
    rng = random.Random(SEED + 1)
    enforcing = {c.spec.id for c in implemented_checks()}
    readable = 0
    judged = 0
    for index, candidate in enumerate(_mutations(original, rng)):
        path = tmp_path / f"mutant-{index}.pdf"
        path.write_bytes(candidate)
        outcome = extract(path)
        if isinstance(outcome, UnreadableDocument):
            assert isinstance(extract(path), UnreadableDocument)
            continue
        readable += 1
        report = check_document(path)
        conforms = {r.check_id for r in report.results if r.status is Status.CONFORMS}
        if conforms:
            judged += 1
            assert report.readability is Readability.READABLE
            assert conforms <= enforcing, (
                f"mutation {index}: {sorted(conforms - enforcing)} report CONFORMS "
                "while enforcing nothing"
            )
    assert readable >= MIN_READABLE, (
        f"only {readable} of {MUTATION_COUNT} mutants were readable, so this test "
        "asserted almost nothing; see MIN_READABLE"
    )
    assert judged >= MIN_READABLE, (
        f"only {judged} readable mutants produced a CONFORMS at all, so the branch "
        "under test barely ran"
    )


@pytest.mark.parametrize("prefix", [b"", b"%PDF-", b"%PDF-1.7\n", b"\x00" * 16])
def test_degenerate_prefixes_are_unreadable_or_harmless(tmp_path: Path, prefix: bytes) -> None:
    path = tmp_path / "degenerate.pdf"
    path.write_bytes(prefix)
    outcome = extract(path)
    assert isinstance(outcome, (LabelDocument, UnreadableDocument))

"""The ADRs' prose invariants, held over generated inputs.

Two guarantees so far live only in hand-built tests and documentation:
normalisation widens matching without changing which words are there, and
cell reconstruction loses nothing that was drawn. These properties hold
them over hundreds of generated cases each, because an invariant that is
stated in an ADR and enforced nowhere is a wish.
"""

from __future__ import annotations

import re
import unicodedata

from hypothesis import given, settings
from hypothesis import strategies as st

from power_content_check.geometry import Segment, _cells
from power_content_check.normalize import (
    _DASHES,
    _DOUBLE_QUOTES,
    _SINGLE_QUOTES,
    _SPACES,
    contains_ignoring_spaces,
    normalize,
)

#: Letters for the needle under construction. Disjoint from the filler
#: alphabet below, so a word slipped between two needle words cannot
#: recreate the needle by accident.
NEEDLE_LETTERS = "abc"
FILLER_LETTERS = "xyz"

words = st.lists(st.text(alphabet=NEEDLE_LETTERS, min_size=2, max_size=5), min_size=2, max_size=6)
filler = st.text(alphabet=FILLER_LETTERS, min_size=2, max_size=5)

#: The spacings extraction might hand back where the document put none.
GAPS = ("", " ", "  ", "\t", "\n", "\u00a0")
gap = st.sampled_from(GAPS)


class TestNormalizeProperties:
    @given(st.text(max_size=300))
    def test_normalizing_twice_is_normalizing_once(self, text: str) -> None:
        assert normalize(normalize(text)) == normalize(text)

    @given(
        st.text(
            alphabet=st.sampled_from(
                "".join(
                    char
                    for char in "abcXYZ019" + _SPACES + _DASHES + _SINGLE_QUOTES + _DOUBLE_QUOTES
                    if unicodedata.normalize("NFKC", char) == char
                )
            ),
            max_size=120,
        )
    )
    def test_folding_is_confined_to_the_declared_classes(self, text: str) -> None:
        """Normalisation is allowed to fold exactly the character classes it
        declares: spaces, dashes, quotes, case, and nothing else. Squeezed of
        whitespace and the two quote characters it normalises to, the output
        is the input's alphanumeric skeleton and no more. The alphabet is
        restricted to NFKC-stable characters because NFKC runs first and may
        rewrite a declared class member into something else entirely, which
        is a fact about the order of operations, not about this property."""
        skeleton = re.sub(r"[^0-9a-zA-Z]+", "", text).lower()
        folded = normalize(text).replace(" ", "").replace("'", "").replace('"', "")
        assert folded == skeleton


class TestSpaceInsensitiveMatching:
    @settings(max_examples=200)
    @given(needle_words=words, data=st.data())
    def test_any_spacing_between_characters_still_matches(
        self, needle_words: list[str], data: st.DataObject
    ) -> None:
        """A subscript, a wrapped heading, a column pad: wherever the extractor
        puts spaces inside these words, the phrase is still found."""

        def spread(text: str) -> str:
            return data.draw(gap).join(data.draw(gap).join(char) for char in text.split())

        noisy = data.draw(filler) + " " + " ".join(spread(w) for w in needle_words)
        assert contains_ignoring_spaces(normalize(noisy), " ".join(needle_words)), (
            f"needle {needle_words} hidden by {noisy!r}"
        )

    @settings(max_examples=200)
    @given(needle_words=words, data=st.data())
    def test_a_word_between_two_needle_words_still_does_not_match(
        self, needle_words: list[str], data: st.DataObject
    ) -> None:
        """The other direction of the same guarantee: intervening words are
        never ignored. Only the spaces are."""
        middle = len(needle_words) // 2
        broken = [*needle_words[:middle], data.draw(filler), *needle_words[middle:]]
        haystack = normalize(" ".join(broken))
        assert not contains_ignoring_spaces(haystack, " ".join(needle_words))


segments = st.lists(
    st.tuples(
        st.floats(min_value=400, max_value=760),  # baseline
        st.floats(min_value=10, max_value=500),  # left edge
        st.floats(min_value=2, max_value=120),  # width
        st.integers(min_value=4, max_value=18),  # font height
        st.text(alphabet="abcdefghij ", min_size=1, max_size=12),  # text
    ),
    min_size=1,
    max_size=40,
)


def _segment(row: tuple[float, float, float, int, str]) -> Segment:
    ty, x0, width, height, text = row
    return Segment(ty=ty, x0=x0, x1=x0 + width, height=float(height), text=text)


class TestCellReconstructionProperties:
    @given(rows=segments)
    def test_reconstruction_loses_and_duplicates_nothing(
        self, rows: list[tuple[float, float, float, int, str]]
    ) -> None:
        """Every character drawn goes into exactly one cell. Squeezed, the
        cells' combined text equals the segments' combined text, whatever the
        geometry did with grouping."""
        segs = [_segment(row) for row in rows]
        cells = _cells(segs)
        drawn = sum(len(re.sub(r"\s+", "", s.text)) for s in segs)
        recovered = sum(len(re.sub(r"\s+", "", c)) for c in cells)
        assert drawn == recovered
        assert len(cells) <= len(segs)

    @given(rows=segments)
    def test_every_segment_survives_whole_inside_some_cell(
        self, rows: list[tuple[float, float, float, int, str]]
    ) -> None:
        """Grouping joins whole segments; it never edits one. Plain lowercase
        letters survive normalisation untouched, so each segment's text must
        appear contiguously in the cell that took it."""
        segs = [_segment(row) for row in rows]
        cells = [_squeezed(c) for c in _cells(segs)]
        for s in segs:
            wanted = _squeezed(s.text)
            assert any(wanted in cell for cell in cells), f"{s.text!r} not in any cell"


def _squeezed(text: str) -> str:
    return re.sub(r"\s+", "", text)

"""Normalisation must widen matching, never narrow it."""

from __future__ import annotations

from power_content_check.normalize import (
    contains,
    contains_ignoring_spaces,
    normalize,
    normalize_lines,
)


class TestNormalize:
    def test_ampersand_becomes_and(self) -> None:
        assert normalize("Biomass & Biogas") == "biomass and biogas"
        assert normalize("Coal & Petroleum") == "coal and petroleum"

    def test_hyphenation_folds(self) -> None:
        assert normalize("Zero-Carbon") == "zero carbon"
        assert normalize("firmed-and-shaped") == "firmed and shaped"

    def test_typographic_quotes_fold(self) -> None:
        assert normalize("\u201cUnbundled RECs\u201d") == '"unbundled recs"'
        assert normalize("California\u2019s") == "california's"

    def test_non_breaking_space_folds(self) -> None:
        nbsp = "\u00a0"
        assert normalize(f"100{nbsp}%") == "100 %"

    def test_runs_of_whitespace_collapse(self) -> None:
        assert normalize("Solar      14%\n\n  65%") == "solar 14% 65%"

    def test_case_folds(self) -> None:
        assert normalize("2024 POWER CONTENT LABEL") == "2024 power content label"

    def test_the_issued_rendering_matches_the_regulation_wording(self) -> None:
        """The point of the ampersand rule, stated as a test."""
        assert normalize("Biomass & Biogas") == normalize("Biomass and biogas")
        assert normalize("Coal & Petroleum") == normalize("Coal and petroleum")


class TestNormalizeLines:
    def test_blank_lines_are_dropped(self) -> None:
        assert normalize_lines("a\n\n  \nb") == ["a", "b"]

    def test_each_line_is_folded_separately(self) -> None:
        assert normalize_lines("Solar  14%\nWind  4%") == ["solar 14%", "wind 4%"]


class TestContains:
    def test_needle_is_normalised_too(self) -> None:
        assert contains(normalize("Coal & Petroleum 0%"), "Coal and petroleum")

    def test_absent_needle(self) -> None:
        assert not contains(normalize("Solar 14%"), "Geothermal")


class TestContainsIgnoringSpaces:
    """A subscript, a ligature or a kerned pair splits one word into two runs."""

    def test_a_split_word_still_matches(self) -> None:
        extracted = normalize("figures exclude biogenic CO\n2 and emissions")
        assert contains_ignoring_spaces(extracted, "biogenic CO2 and emissions")

    def test_a_word_that_is_genuinely_missing_does_not_match(self) -> None:
        extracted = normalize("figures exclude emissions")
        assert not contains_ignoring_spaces(extracted, "biogenic CO2 and emissions")

    def test_intervening_words_are_not_ignored(self) -> None:
        """It ignores where the spaces are, not what sits between the words."""
        extracted = normalize("CA Utility Power Mix Average")
        assert not contains_ignoring_spaces(extracted, "CA Utility Average")

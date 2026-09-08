"""Where a finding was read from, and the fence around it.

Two things are being tested and they pull in opposite directions. The evidence
block has to be *real*: a page and a run a reader can go and look at. And it
has to be *inert* -- unable to change any status, count or exit code. The second
half is the one that could rot quietly, so it is asserted mechanically rather
than reasoned about: the same documents are run with collection on and off and
the statuses, findings, counts, exit code and fingerprint are compared.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import LABEL_LINES, synthetic_label_pdf, synthetic_multipage_pdf
from power_content_check.checks import CheckContext
from power_content_check.engine import check_document, check_paths, fingerprint
from power_content_check.evidence import (
    RUN_CAP,
    TRUNCATION_MARKER,
    Evidence,
    locate,
    locate_in_cell,
)
from power_content_check.extract import LabelDocument, extract
from power_content_check.model import Status
from power_content_check.report import render_json, render_text

#: The conforming fixture's total row, verbatim, so a variant of it can be built
#: without retyping a line whose column padding is load-bearing.
TOTAL_ROW = "Total" + " " * 47 + "100%" + " " * 9 + "100%" + " " * 16 + "100%"


def _read(path: Path) -> LabelDocument:
    document = extract(path)
    assert isinstance(document, LabelDocument), "the fixture must be readable"
    return document


def _variant(tmp_path: Path, source: Path, old: str, new: str) -> Path:
    """The conforming label with one substitution, and still long enough to read.

    Built from the real fixture rather than written fresh, because a two-line
    file falls below the extractor's 200-character floor and arrives as
    *unreadable* -- which produces NOT_EVALUATED for every check and a test that
    passes or fails for reasons that have nothing to do with evidence.
    """
    text = source.read_text(encoding="utf-8")
    assert old in text, f"the fixture no longer carries {old!r}"
    path = tmp_path / "variant.txt"
    path.write_text(text.replace(old, new), encoding="utf-8")
    return path


class TestAConformingResultSaysWhereItLooked:
    def test_every_conforming_result_carries_a_run(self, conforming_label: Path) -> None:
        report = check_document(
            conforming_label, CheckContext(supplier_name="Example Municipal Utility District")
        )
        conforming = [r for r in report.results if r.status is Status.CONFORMS]

        # A floor. If the catalog or the fixture drifts so that nothing conforms,
        # the loop below would pass over an empty list and prove nothing.
        assert len(conforming) >= 15
        for result in conforming:
            assert result.evidence is not None, f"{result.check_id} conformed and cited nothing"
            assert result.evidence.run
            assert result.evidence.partial is False

    def test_a_pdf_result_names_the_page_it_was_read_from(self, text_layer_pdf: Path) -> None:
        report = check_document(text_layer_pdf, CheckContext(supplier_name="Example Municipal"))
        cited = [r for r in report.results if r.evidence is not None]

        assert len(cited) >= 8
        assert all(r.evidence is not None and r.evidence.page == 1 for r in cited)

    def test_the_run_contains_the_phrase_the_check_looked_for(self, conforming_label: Path) -> None:
        report = check_document(conforming_label, CheckContext())
        runs = {r.check_id: r.evidence.run for r in report.results if r.evidence is not None}

        assert "energy commission" in runs["PCL004"]
        assert "renewables and zero carbon resources" in runs["PCL007"]
        assert "rps eligible renewables" in runs["PCL008"]
        assert "fossil fuels" in runs["PCL009"]
        assert "greenhouse gas emissions intensity" in runs["PCL010"]
        assert "2025 power content label" in runs["PCL017"]
        assert runs["PCL018"].startswith("total 100%")
        # PCL006 cites the first fuel category in the regulation's own order that
        # was found, which is subparagraph (A).
        assert "biomass and biogas" in runs["PCL006"]

    def test_a_not_evaluated_result_never_carries_evidence(self, conforming_label: Path) -> None:
        # A check that could not run scanned nothing, so there is no run to cite.
        report = check_document(conforming_label, CheckContext())
        not_evaluated = [r for r in report.results if r.status is Status.NOT_EVALUATED]

        assert not_evaluated, "the fixture must reach at least one not-evaluated result"
        assert all(r.evidence is None for r in not_evaluated)

    def test_an_unreadable_document_cites_nothing_anywhere(self, image_only_pdf: Path) -> None:
        report = check_document(image_only_pdf, CheckContext())

        assert report.results, "an unreadable document still produces a result per check"
        assert all(r.evidence is None for r in report.results)


class TestADeviationCitesTheNearestThingOrNothing:
    def test_an_absence_carries_no_evidence(self, tmp_path: Path, conforming_label: Path) -> None:
        # PCL007's deviation is that a phrase is not there. An absence has no
        # position, and inventing one would be the defect this whole block is
        # supposed to close.
        path = _variant(
            tmp_path, conforming_label, "Renewables and Zero-Carbon Resources", "Clean Resources"
        )
        report = check_document(path, CheckContext())
        result = next(r for r in report.results if r.check_id == "PCL007")

        assert result.status is Status.DOES_NOT_CONFORM
        assert result.evidence is None

    def test_a_near_miss_is_cited_and_marked_partial(
        self, tmp_path: Path, conforming_label: Path
    ) -> None:
        # The abbreviation is present and the name the regulation asks for is not.
        path = _variant(
            tmp_path, conforming_label, "California Energy Commission", "California CEC"
        )
        report = check_document(path, CheckContext())
        result = next(r for r in report.results if r.check_id == "PCL004")

        assert result.status is Status.DOES_NOT_CONFORM
        assert result.evidence is not None
        assert result.evidence.partial is True
        assert "cec" in result.evidence.run

    def test_the_row_a_total_deviation_is_about_is_cited_and_is_not_partial(
        self, tmp_path: Path, conforming_label: Path
    ) -> None:
        path = _variant(tmp_path, conforming_label, TOTAL_ROW, TOTAL_ROW.replace("100%", "99%", 1))
        report = check_document(path, CheckContext())
        result = next(r for r in report.results if r.check_id == "PCL018")

        assert result.status is Status.DOES_NOT_CONFORM
        assert result.evidence is not None
        # Not a near miss: this row is exactly what the finding is about.
        assert result.evidence.partial is False
        assert "99%" in result.evidence.run


class TestTheFenceFromAdr0007:
    """Position is recorded, never decided on."""

    @pytest.fixture
    def documents(
        self, tmp_path: Path, conforming_label: Path, deficient_label: Path
    ) -> list[Path]:
        return [
            conforming_label,
            deficient_label,
            synthetic_label_pdf(tmp_path / "label.pdf"),
        ]

    def test_statuses_and_findings_are_identical_with_collection_off(
        self, documents: list[Path]
    ) -> None:
        with_evidence = check_paths(documents, CheckContext(supplier_name="Example"))
        without = check_paths(
            documents, CheckContext(supplier_name="Example", collect_evidence=False)
        )

        def conclusions(report: object) -> list[tuple[str, str, str, str | None]]:
            return [
                (document.path, result.check_id, result.status.value, result.detail)
                for document in report.documents  # type: ignore[attr-defined]
                for result in document.results
            ]

        assert conclusions(with_evidence) == conclusions(without)
        assert with_evidence.exit_code == without.exit_code
        assert [d.counts for d in with_evidence.documents] == [d.counts for d in without.documents]

    def test_the_fingerprint_is_identical_with_collection_off(self, documents: list[Path]) -> None:
        with_evidence = check_paths(documents, CheckContext(supplier_name="Example"))
        without = check_paths(
            documents, CheckContext(supplier_name="Example", collect_evidence=False)
        )

        assert fingerprint(with_evidence) == fingerprint(without)

    def test_collection_off_really_removes_it(self, documents: list[Path]) -> None:
        # The pair above would hold vacuously if evidence were never collected in
        # the first place, so the difference is asserted directly.
        with_evidence = check_paths(documents, CheckContext(supplier_name="Example"))
        without = check_paths(
            documents, CheckContext(supplier_name="Example", collect_evidence=False)
        )

        assert any(r.evidence is not None for d in with_evidence.documents for r in d.results)
        assert all(r.evidence is None for d in without.documents for r in d.results)


class TestTheLocatorRefusesToGuess:
    def test_text_the_document_does_not_hold_is_not_located(self, text_layer_pdf: Path) -> None:
        # The one way an evidence block could stop being evidence is by finding
        # the nearest thing instead of the thing. It returns nothing instead.
        assert locate(_read(text_layer_pdf), "a phrase this label does not carry") is None

    def test_an_empty_needle_is_not_located(self, text_layer_pdf: Path) -> None:
        assert locate(_read(text_layer_pdf), "   ") is None

    def test_a_run_split_by_a_subscript_is_found_when_spaces_are_ignored(
        self, tmp_path: Path, conforming_label: Path
    ) -> None:
        # The extractor reports a subscript as its own text run, so "CO2e" arrives
        # as "CO 2 e". The literal search must miss it and the space-ignoring one
        # must find it, or the footnote checks would cite nothing on a real label.
        path = _variant(tmp_path, conforming_label, "lbs of CO2e emitted", "lbs of CO 2 e emitted")
        document = _read(path)

        assert locate(document, "CO2e") is None
        found = locate(document, "CO2e", ignoring_spaces=True)
        assert found is not None
        assert "co 2 e" in found.run

    def test_a_cell_reading_names_the_cell_and_no_page(self, wrapped_heading_pdf: Path) -> None:
        document = _read(wrapped_heading_pdf)
        found = locate_in_cell(document, "ca utility average")

        assert found is not None
        assert found.cell_index is not None
        # Cells are rebuilt from the whole document, so claiming a page would be
        # inventing a fact the reconstruction does not hold.
        assert found.page is None

    def test_a_cell_reading_refuses_what_no_cell_holds(self, wrapped_heading_pdf: Path) -> None:
        assert locate_in_cell(_read(wrapped_heading_pdf), "not in any cell") is None

    def test_a_document_with_no_cells_locates_nothing_in_one(self, conforming_label: Path) -> None:
        document = _read(conforming_label)
        assert document.cells is None
        assert locate_in_cell(document, "total") is None


class TestPagesAndTheirAbsence:
    def test_a_second_page_is_reported_as_the_second_page(self, tmp_path: Path) -> None:
        # The label's own lines, split across two pages. Enough text to be read at
        # all, and each phrase on exactly one page so the answer is checkable.
        # Case-insensitively: the label also says "Unspecified Power (primarily
        # fossil fuels)", and leaving that on page one would put the phrase on
        # both pages and make the answer meaningless.
        front = tuple(line for line in LABEL_LINES if "fossil fuels" not in line.lower())
        path = synthetic_multipage_pdf(
            tmp_path / "two_pages.pdf",
            [(front, ()), (("Fossil Fuels  Natural Gas 30%  Coal and Petroleum 3%",), ())],
        )
        report = check_document(path, CheckContext())
        by_id = {r.check_id: r for r in report.results}

        assert by_id["PCL017"].evidence is not None
        assert by_id["PCL017"].evidence.page == 1
        assert by_id["PCL009"].evidence is not None
        assert by_id["PCL009"].evidence.page == 2

    def test_a_run_that_exists_only_across_a_page_break_has_no_page(self, tmp_path: Path) -> None:
        # "fossil fuels" is on neither page: page one ends with "fossil" and page
        # two begins with "fuels". The join is what carries it, and the honest
        # page for that is none -- not page 1, and not page 2.
        # Case-insensitively: the label also says "Unspecified Power (primarily
        # fossil fuels)", and leaving that on page one would put the phrase on
        # both pages and make the answer meaningless.
        front = (
            *(line for line in LABEL_LINES if "fossil fuels" not in line.lower()),
            "Fossil",
        )
        path = synthetic_multipage_pdf(
            tmp_path / "split.pdf",
            [(front, ()), (("Fuels  Natural Gas 30%",), ())],
        )
        report = check_document(path, CheckContext())
        result = next(r for r in report.results if r.check_id == "PCL009")

        assert result.status is Status.CONFORMS
        assert result.evidence is not None
        assert result.evidence.page is None
        assert "fossil fuels" in result.evidence.run

    def test_plain_text_input_has_no_pages_and_says_so(self, conforming_label: Path) -> None:
        report = check_document(conforming_label, CheckContext())
        cited = [r for r in report.results if r.evidence is not None]

        assert cited, "the fixture must produce at least one cited result"
        assert all(r.evidence is not None and r.evidence.page is None for r in cited)


class TestTheRunIsBounded:
    def test_a_long_run_is_cut_and_says_so(self, tmp_path: Path, conforming_label: Path) -> None:
        # One total row far longer than the cap. The cut has to be visible, or a
        # reader compares a shortened quotation against the document and finds a
        # mismatch the tool never disclosed.
        columns = " ".join(["100%"] * 120)
        path = _variant(tmp_path, conforming_label, TOTAL_ROW, f"Total {columns}")
        report = check_document(path, CheckContext())
        result = next(r for r in report.results if r.check_id == "PCL018")

        assert result.evidence is not None
        assert result.evidence.truncated is True
        assert result.evidence.run.endswith(TRUNCATION_MARKER)
        assert len(result.evidence.run) <= RUN_CAP

    def test_a_short_run_is_neither_cut_nor_marked(self, conforming_label: Path) -> None:
        report = check_document(conforming_label, CheckContext())
        result = next(r for r in report.results if r.check_id == "PCL017")

        assert result.evidence is not None
        assert result.evidence.truncated is False
        assert TRUNCATION_MARKER not in result.evidence.run

    def test_no_run_anywhere_exceeds_the_cap(self, conforming_label: Path) -> None:
        report = check_document(conforming_label, CheckContext(supplier_name="Example Municipal"))

        for result in report.results:
            if result.evidence is not None:
                assert len(result.evidence.run) <= RUN_CAP


class TestTheReport:
    def test_json_carries_the_block_and_its_keys(self, conforming_label: Path) -> None:
        payload = json.loads(render_json(check_paths([conforming_label])))
        cited = [r for d in payload["documents"] for r in d["results"] if r["evidence"] is not None]

        assert cited
        for block in (r["evidence"] for r in cited):
            assert set(block) == {"page", "run", "truncated", "partial", "cell_index"}

    def test_json_carries_a_null_block_rather_than_omitting_the_key(
        self, conforming_label: Path
    ) -> None:
        payload = json.loads(
            render_json(check_paths([conforming_label], CheckContext(collect_evidence=False)))
        )
        results = [r for d in payload["documents"] for r in d["results"]]

        assert results
        # The key is always present. A consumer that reads report-v1 can tell
        # "nothing was cited" from "this producer had no such concept" only if the
        # key is there to be null.
        assert all("evidence" in r and r["evidence"] is None for r in results)

    def test_the_text_report_shows_it_only_when_verbose(self, conforming_label: Path) -> None:
        report = check_paths([conforming_label])

        assert "Read from" not in render_text(report, verbose=False)
        assert "Read from" in render_text(report, verbose=True)

    def test_the_text_report_names_a_near_miss_as_one(
        self, tmp_path: Path, conforming_label: Path
    ) -> None:
        path = _variant(
            tmp_path, conforming_label, "California Energy Commission", "California CEC"
        )

        assert "Nearest match read from" in render_text(check_paths([path]), verbose=True)

    def test_the_text_report_says_no_single_page_rather_than_guessing_one(self) -> None:
        line = render_text.__globals__["_render_evidence"](
            Evidence(page=None, run="fossil fuels", truncated=False)
        )

        assert "no single page" in line

    def test_the_text_report_names_a_column_cell(self) -> None:
        line = render_text.__globals__["_render_evidence"](
            Evidence(page=None, run="ca utility average", truncated=False, cell_index=4)
        )

        assert "column cell 4" in line


def test_the_label_fixture_still_carries_the_phrases_these_tests_cite() -> None:
    """A floor under the whole module.

    Several assertions above look for a phrase inside a located run. If the
    shared fixture stopped carrying that phrase, every one of them would be
    asserting something about a document that no longer says it, and the failure
    would look like a locator bug.
    """
    joined = "\n".join(LABEL_LINES).lower()

    for phrase in (
        "renewables and zero-carbon resources",
        "rps eligible renewables",
        "fossil fuels",
        "greenhouse gas emissions intensity",
        "2024 power content label",
        "total 100%",
        "biomass and biogas",
    ):
        assert phrase in joined, f"the shared PDF fixture no longer carries {phrase!r}"

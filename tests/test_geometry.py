"""Reading a page column by column, and the fence around doing so.

ADR 0007 refused position for attribution and left one use open: putting the
lines of a wrapped column heading back in the cell they belong to. ADR 0008
built that. These tests hold the fence rather than the feature: the feature is
that a heading is recovered, and the fence is that nothing recovered this way
can ever become a deviation against a document.
"""

from __future__ import annotations

from pathlib import Path

import pypdf
import pytest

from power_content_check.checks import BY_ID, CheckContext
from power_content_check.extract import LabelDocument, extract
from power_content_check.geometry import (
    CELL_LINE_SPACING,
    Segment,
    _cells,
    _nests,
    document_cells,
    page_cells,
)
from power_content_check.model import Status
from power_content_check.normalize import normalize


def _minimal_pdf(path: Path, content: bytes) -> Path:
    """One page carrying exactly the content stream given, and nothing else."""
    from conftest import _pdf, _stream

    path.write_bytes(
        _pdf(
            [
                b"<< /Type /Catalog /Pages 2 0 R >>",
                b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                (
                    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
                    b"/Resources << /Font << /F1 5 0 R >> >> >>"
                ),
                _stream("", content),
                b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            ]
        )
    )
    return path


def _read(path: Path) -> LabelDocument:
    document = extract(path)
    assert isinstance(document, LabelDocument)
    return document


def _pcl016(document: LabelDocument) -> tuple[Status, str]:
    run = BY_ID["PCL016"].run
    assert run is not None
    result = run(document, CheckContext())
    return result.status, f"{result.finding} {result.detail or ''}"


class TestReadingDownAColumn:
    def test_a_wrapped_heading_is_lost_reading_across_the_page(
        self, wrapped_heading_pdf: Path
    ) -> None:
        """The artefact this exists to repair, shown before it is repaired.

        The text layer holds every word of the heading and holds them in the
        wrong order, because extraction reads across the wrap.
        """
        document = _read(wrapped_heading_pdf)
        assert "ca utility" in document.normalized
        assert "average" in document.normalized
        assert "ca utility average" not in document.normalized

    def test_the_heading_survives_reading_down_the_column(self, wrapped_heading_pdf: Path) -> None:
        assert "ca utility average" in (_read(wrapped_heading_pdf).cells or ())

    def test_the_neighbouring_heading_survives_too(self, wrapped_heading_pdf: Path) -> None:
        """Both columns reconstruct, not just the one the check asks about."""
        assert "2024 example power mix" in (_read(wrapped_heading_pdf).cells or ())

    def test_the_check_recovers_the_rendering(self, wrapped_heading_pdf: Path) -> None:
        status, text = _pcl016(_read(wrapped_heading_pdf))
        assert status is Status.CONFORMS
        assert "column read down the page" in text

    def test_a_plain_text_input_has_no_geometry(self, conforming_label: Path) -> None:
        """There are no coordinates in a text file, and none are invented."""
        assert _read(conforming_label).cells is None


class TestTheFence:
    """Geometry may confirm. It may never accuse."""

    def test_scattered_words_still_report_nothing(self, scattered_words_pdf: Path) -> None:
        """Words of a rendering, in three different cells, decide nothing.

        This is the case ADR 0006 refused to call either way. Reading the page
        column by column does not turn it into a finding; it leaves it refused.
        """
        status, text = _pcl016(_read(scattered_words_pdf))
        assert status is Status.NOT_EVALUATED
        assert "reports neither" in text

    def test_a_cell_cannot_rescue_a_document_that_lacks_the_words(
        self, deficient_label: Path
    ) -> None:
        """The deviation is returned before any cell is consulted.

        Constructed rather than rendered, because the point is structural: even
        handed a cell that spells the rendering outright, a document whose text
        layer does not carry the words is still reported as deviating.
        """
        document = _read(deficient_label)
        planted = LabelDocument(
            path=document.path,
            sha256=document.sha256,
            page_count=document.page_count,
            raw_text=document.raw_text,
            normalized=document.normalized,
            normalized_lines=document.normalized_lines,
            image_count=document.image_count,
            extraction_basis=document.extraction_basis,
            cells=("ca utility average",),
        )
        assert "ca utility average" not in planted.normalized
        status, _text = _pcl016(planted)
        assert status is Status.DOES_NOT_CONFORM

    def test_only_one_function_in_the_catalog_reads_the_cells(self) -> None:
        """One helper consults geometry. Every check reaches it through that.

        Read off the source rather than exercised, because the property being
        held is that the surface stays this small.
        """
        import ast

        source = (
            Path(__file__).resolve().parent.parent / "src" / "power_content_check" / "checks.py"
        ).read_text(encoding="utf-8")
        readers = sorted(
            node.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef)
            and any(
                isinstance(inner, ast.Attribute) and inner.attr == "cells"
                for inner in ast.walk(node)
            )
        )
        assert readers == ["_in_a_reconstructed_cell"]


class TestClustering:
    def test_containment_joins_a_centred_second_line(self) -> None:
        wide = Segment(ty=100.0, x0=400.0, x1=445.0, height=9.0, text="CA Utility")
        narrow = Segment(ty=88.0, x0=402.0, x1=443.0, height=9.0, text="Average")
        assert _nests(wide, narrow)
        assert _cells([wide, narrow]) == ["ca utility average"]

    def test_a_line_that_only_reaches_into_a_column_does_not_join_it(self) -> None:
        """Overlap is not containment, and the difference is the whole rule.

        A supplier's name spanning most of the page overlaps the heading beside
        it. Joining on overlap would glue the two together and reproduce the
        very interleaving this is meant to undo.
        """
        spanning = Segment(ty=112.0, x0=100.0, x1=410.0, height=9.0, text="Example Utility")
        heading = Segment(ty=100.0, x0=400.0, x1=445.0, height=9.0, text="CA Utility")
        assert not _nests(spanning, heading)
        assert sorted(_cells([spanning, heading])) == ["ca utility", "example utility"]

    def test_a_cell_reads_top_to_bottom(self) -> None:
        upper = Segment(ty=100.0, x0=400.0, x1=445.0, height=9.0, text="CA Utility")
        lower = Segment(ty=88.0, x0=402.0, x1=443.0, height=9.0, text="Average")
        assert _cells([lower, upper]) == ["ca utility average"]

    def test_distance_down_the_page_breaks_a_cell(self) -> None:
        """A cell is local. Two lines a long way apart are two cells."""
        upper = Segment(ty=400.0, x0=400.0, x1=445.0, height=9.0, text="CA Utility")
        far = Segment(ty=100.0, x0=402.0, x1=443.0, height=9.0, text="Average")
        assert sorted(_cells([upper, far])) == ["average", "ca utility"]

    def test_small_type_gets_the_spacing_its_own_size_allows(self) -> None:
        """The allowance is per pair, not per page.

        A page carrying one line of large type must not let two lines of small
        type sit further apart than small type ever sits. The larger figure only
        decides when to stop looking further down the page.
        """
        headline = Segment(ty=200.0, x0=0.0, x1=500.0, height=20.0, text="Headline")
        upper = Segment(ty=100.0, x0=400.0, x1=445.0, height=5.0, text="CA Utility")
        lower = Segment(ty=85.0, x0=402.0, x1=443.0, height=5.0, text="Average")
        assert sorted(_cells([headline, upper, lower])) == [
            "average",
            "ca utility",
            "headline",
        ]

    @pytest.mark.parametrize("spacing", [1.5, 2.0, 3.0, 6.0])
    def test_the_line_spacing_constant_is_not_load_bearing(
        self, monkeypatch: pytest.MonkeyPatch, wrapped_heading_pdf: Path, spacing: float
    ) -> None:
        """Any value across a wide plateau reconstructs the same heading.

        The constant is an engineering choice and is documented as one. This is
        the evidence for that claim rather than an assertion of it.
        """
        monkeypatch.setattr("power_content_check.geometry.CELL_LINE_SPACING", spacing)
        reader = pypdf.PdfReader(wrapped_heading_pdf)
        assert "ca utility average" in (page_cells(reader.pages[0]) or ())

    def test_the_shipped_constant_sits_inside_that_plateau(self) -> None:
        assert 1.5 <= CELL_LINE_SPACING <= 6.0


class TestFailingSafely:
    def test_a_page_whose_geometry_cannot_be_read_yields_none(self) -> None:
        """Not an exception, and not an empty tuple that reads as an answer."""

        class Hostile:
            def __getitem__(self, key: str) -> object:
                raise RuntimeError("no content stream here")

        assert page_cells(Hostile()) is None

    def test_a_document_of_such_pages_yields_none(self) -> None:
        class Hostile:
            def __getitem__(self, key: str) -> object:
                raise RuntimeError("no content stream here")

        assert document_cells([Hostile(), Hostile()]) is None

    def test_a_blank_page_yields_none(self, image_only_pdf: Path) -> None:
        reader = pypdf.PdfReader(image_only_pdf)
        assert page_cells(reader.pages[0]) is None

    def test_a_page_with_too_many_spans_is_not_reconstructed(
        self, monkeypatch: pytest.MonkeyPatch, wrapped_heading_pdf: Path
    ) -> None:
        """The stop yields nothing, not a partial reading of the page."""
        monkeypatch.setattr("power_content_check.geometry.MAX_SEGMENTS", 1)
        reader = pypdf.PdfReader(wrapped_heading_pdf)
        assert page_cells(reader.pages[0]) is None

    def test_a_real_label_is_nowhere_near_that_stop(self, wrapped_heading_pdf: Path) -> None:
        from power_content_check.geometry import MAX_SEGMENTS, _segments, _text_runs

        reader = pypdf.PdfReader(wrapped_heading_pdf)
        assert len(_segments(_text_runs(reader.pages[0]))) < MAX_SEGMENTS / 10

    def test_a_page_that_draws_no_text_yields_none(self, tmp_path: Path) -> None:
        """A content stream with nothing written on it is not an empty answer."""
        path = _minimal_pdf(tmp_path / "no_text.pdf", b"q 1 0 0 1 0 0 cm Q")
        reader = pypdf.PdfReader(path)
        assert page_cells(reader.pages[0]) is None

    def test_text_state_set_outside_a_text_object_is_still_followed(self, tmp_path: Path) -> None:
        """A page may choose the font before it opens the text object.

        The issued labels do exactly that, and a walker that only watched inside
        BT and ET would read their text with no font and no width for a space,
        which is the measurement every cell boundary here depends on.
        """
        path = _minimal_pdf(
            tmp_path / "font_outside.pdf",
            b"0 Tc\n/F1 11 Tf\nBT 1 0 0 1 400 540 Tm (CA Utility) Tj ET\n"
            b"BT 1 0 0 1 402 528 Tm (Average) Tj ET",
        )
        reader = pypdf.PdfReader(path)
        assert page_cells(reader.pages[0]) == ("ca utility average",)

    def test_the_check_says_so_when_there_is_no_geometry(self, scattered_words_pdf: Path) -> None:
        """A document with no recoverable geometry reads the same as a miss."""
        document = _read(scattered_words_pdf)
        stripped = LabelDocument(
            path=document.path,
            sha256=document.sha256,
            page_count=document.page_count,
            raw_text=document.raw_text,
            normalized=document.normalized,
            normalized_lines=document.normalized_lines,
            image_count=document.image_count,
            extraction_basis=document.extraction_basis,
            cells=None,
        )
        status, text = _pcl016(stripped)
        assert status is Status.NOT_EVALUATED
        assert "no recoverable geometry" in text


class TestTheMachineryIsStillThere:
    """A pinned dependency can move under this without anything else noticing.

    The layout machinery this reads lives inside pypdf rather than on its public
    surface. If a version bump takes it away, every deviation stays correct and
    PCL016 quietly loses coverage again. That is the safe failure, and it is
    also the silent one, so it is asserted here instead of discovered later.
    """

    def test_a_real_pdf_still_yields_positioned_text(self, wrapped_heading_pdf: Path) -> None:
        reader = pypdf.PdfReader(wrapped_heading_pdf)
        cells = page_cells(reader.pages[0])
        assert cells is not None
        assert normalize("CA Utility Average") in cells

"""Reading documents, and refusing to."""

from __future__ import annotations

from pathlib import Path

import pytest

from power_content_check.extract import (
    SUPPORTED_SUFFIXES,
    LabelDocument,
    UnreadableDocument,
    count_images,
    discover,
    extract,
)


class TestReadable:
    def test_a_text_label_reads(self, conforming_label: Path) -> None:
        result = extract(conforming_label)
        assert isinstance(result, LabelDocument)
        assert result.sha256
        assert result.page_count is None
        assert "power content label" in result.normalized

    def test_the_digest_is_the_file_digest(self, conforming_label: Path) -> None:
        import hashlib

        result = extract(conforming_label)
        assert isinstance(result, LabelDocument)
        assert result.sha256 == hashlib.sha256(conforming_label.read_bytes()).hexdigest()

    def test_latin1_fallback(self, tmp_path: Path) -> None:
        path = tmp_path / "latin.txt"
        path.write_bytes("Cost is 12 \xa3 per unit. ".encode("latin-1") * 20)
        assert isinstance(extract(path), LabelDocument)


class TestArtworkVersusText:
    """What the tool is entitled to say when it cannot find something.

    Extraction reads a text layer. An element the tool cannot find is either
    absent from the document or drawn as a picture, and the difference matters
    a great deal when the document belongs to a named organisation. The tool
    measures the pictures so that it can say which explanations are available.
    """

    def _read(self, path: Path) -> LabelDocument:
        result = extract(path)
        assert isinstance(result, LabelDocument)
        return result

    def test_a_pdf_with_no_artwork_reports_none(self, text_layer_pdf: Path) -> None:
        document = self._read(text_layer_pdf)
        assert document.image_count == 0
        assert "embeds no image" in document.extraction_basis

    def test_a_zero_count_still_admits_vector_drawn_text(self, text_layer_pdf: Path) -> None:
        """A count of zero narrows the explanations. It does not close them."""
        assert "vector paths" in self._read(text_layer_pdf).extraction_basis

    def test_artwork_is_counted_including_inside_a_form(self, illustrated_pdf: Path) -> None:
        document = self._read(illustrated_pdf)
        assert document.image_count == 5
        assert "embeds 5 images" in document.extraction_basis

    def test_a_text_input_says_it_is_a_text_input(self, conforming_label: Path) -> None:
        document = self._read(conforming_label)
        assert document.image_count is None
        assert "plain text file" in document.extraction_basis

    def test_an_uncountable_document_does_not_claim_a_count(self) -> None:
        assert count_images([object()]) is None

    def test_counting_never_raises_on_a_hostile_page(self) -> None:
        class Exploding:
            def get(self, _key: str) -> object:
                raise RuntimeError("boom")

        assert count_images([Exploding()]) is None


class _Node(dict[str, object]):
    """A resource dictionary that answers ``get_object`` the way pypdf's do."""

    def get_object(self) -> _Node:
        return self


class _Ref:
    """An indirect reference, with the identity pypdf gives one."""

    def __init__(self, target: _Node, idnum: int) -> None:
        self._target = target
        self.idnum = idnum
        self.generation = 0

    def get_object(self) -> _Node:
        return self._target


def _page(resources: _Node | None) -> _Node:
    return _Node({"/Resources": resources}) if resources else _Node()


class TestImageCountingEdges:
    """The paths where a miscount would let the tool overstate an absence.

    An undercount is the dangerous direction. It would let the tool say a
    document embeds no image, which is the sentence that turns "not in the
    extracted text" into something close to "not in the document".
    """

    def _image(self, number: int) -> _Ref:
        return _Ref(_Node({"/Subtype": "/Image"}), number)

    def test_a_page_with_no_resources_counts_nothing(self) -> None:
        assert count_images([_page(None)]) == 0

    def test_one_image_referenced_twice_is_one_image(self) -> None:
        shared = self._image(7)
        resources = _Node({"/XObject": _Node({"/Im0": shared, "/Im1": shared})})
        assert count_images([_page(resources)]) == 1

    def test_an_xobject_that_is_neither_image_nor_form_is_ignored(self) -> None:
        other = _Ref(_Node({"/Subtype": "/PS"}), 8)
        resources = _Node({"/XObject": _Node({"/X0": other, "/Im0": self._image(9)})})
        assert count_images([_page(resources)]) == 1

    def test_forms_nested_past_the_depth_cap_stop_rather_than_loop(self) -> None:
        """A form that contains itself must not spin, and must not crash."""
        form = _Node({"/Subtype": "/Form"})
        ref = _Ref(form, 10)
        form["/Resources"] = _Node({"/XObject": _Node({"/Fm0": ref})})
        assert count_images([_page(_Node({"/XObject": _Node({"/Fm0": ref})}))]) == 0


class TestUnreadable:
    def test_missing_file(self, tmp_path: Path) -> None:
        result = extract(tmp_path / "nope.pdf")
        assert isinstance(result, UnreadableDocument)
        assert result.reason == "the file does not exist"
        assert result.sha256 is None

    def test_directory(self, tmp_path: Path) -> None:
        result = extract(tmp_path)
        assert isinstance(result, UnreadableDocument)
        assert "directory" in result.reason

    def test_empty_file(self, empty_file: Path) -> None:
        result = extract(empty_file)
        assert isinstance(result, UnreadableDocument)
        assert result.reason == "the file is empty"

    def test_corrupt_pdf(self, corrupt_pdf: Path) -> None:
        result = extract(corrupt_pdf)
        assert isinstance(result, UnreadableDocument)
        assert "could not be parsed" in result.reason or "no pages" in result.reason

    def test_image_only_pdf(self, image_only_pdf: Path) -> None:
        result = extract(image_only_pdf)
        assert isinstance(result, UnreadableDocument)
        assert "text layer" in result.reason

    def test_encrypted_pdf(self, encrypted_pdf: Path) -> None:
        result = extract(encrypted_pdf)
        assert isinstance(result, UnreadableDocument)
        assert result.reason == "the PDF is encrypted"

    def test_unsupported_suffix(self, unsupported_file: Path) -> None:
        result = extract(unsupported_file)
        assert isinstance(result, UnreadableDocument)
        assert "not a supported label format" in result.reason

    def test_short_text_file(self, tmp_path: Path) -> None:
        path = tmp_path / "stub.txt"
        path.write_text("2025 Power Content Label")
        result = extract(path)
        assert isinstance(result, UnreadableDocument)
        assert "below the" in result.reason

    def test_the_threshold_is_adjustable(self, tmp_path: Path) -> None:
        path = tmp_path / "stub.txt"
        path.write_text("2025 Power Content Label")
        assert isinstance(extract(path, min_chars=5), LabelDocument)

    def test_extract_never_raises(self, tmp_path: Path) -> None:
        weird = tmp_path / "weird.pdf"
        weird.write_bytes(bytes(range(256)) * 8)
        assert isinstance(extract(weird), UnreadableDocument)


class TestMultipage:
    """A label may be spread over more than one page.

    Nothing in the regulation says a label is one page, and PCL019's reason
    records that the tool declines to equate "one place" with one page.
    Extraction already joins every page before normalisation, so text split
    across a page boundary reaches the checks; what these tests hold is that
    it does, and that geometry stays a fact about one page at a time.
    """

    @pytest.fixture
    def straddling_pdf(self, tmp_path: Path) -> Path:
        """Two pages: the fuel rows split across the boundary."""
        from conftest import synthetic_multipage_pdf

        return synthetic_multipage_pdf(
            tmp_path / "straddling.pdf",
            pages=[
                (
                    (
                        "2024 POWER CONTENT LABEL",
                        "Example Municipal Utility District",
                        "Greenhouse Gas Emissions Intensity in lbs of CO2e per megawatt hour: 410",
                        "Renewables and Zero-Carbon Resources",
                        "RPS Eligible Renewables 40%",
                        "Solar 20%  Wind 12%  Geothermal 5%",
                        "Biomass and Biogas 2%  Eligible Hydroelectric 1%",
                    ),
                    (),
                ),
                (
                    (
                        "Large Hydroelectric 8%  Nuclear 9%",
                        "Fossil Fuels  Natural Gas 30%  Coal and Petroleum 3%",
                        "Unspecified Power (primarily fossil fuels) 10%",
                        "Total 100%",
                    ),
                    (),
                ),
            ],
        )

    def test_both_pages_are_seen(self, straddling_pdf: Path) -> None:
        result = extract(straddling_pdf)
        assert isinstance(result, LabelDocument)
        assert result.page_count == 2

    def test_rows_split_across_the_boundary_reach_the_checks(self, straddling_pdf: Path) -> None:
        """PCL006 needs all ten categories, which no single page carries."""
        from power_content_check.checks import CHECKS, CheckContext
        from power_content_check.engine import run_checks
        from power_content_check.model import Status

        result = extract(straddling_pdf)
        assert isinstance(result, LabelDocument)
        by_id = {r.check_id: r for r in run_checks(result, CheckContext())}
        assert by_id["PCL006"].status is Status.CONFORMS
        assert len(by_id) == len(CHECKS)

    def test_a_heading_wrapped_across_pages_still_reads_in_order(self, tmp_path: Path) -> None:
        """Each page is extracted whole, so a wrap whose second line falls on
        the next page arrives in reading order through the ordinary line join
        and needs no geometry at all. This is why cross-page reconstruction
        would be building nothing."""
        from conftest import Placed, synthetic_multipage_pdf

        page_one: tuple[tuple[str, ...], Placed] = (
            ("2024 POWER CONTENT LABEL", "Example Municipal Utility District"),
            ((200.0, 700.0, "CA Utility"),),
        )
        page_two: tuple[tuple[str, ...], Placed] = (
            (
                "Average Rate Table",
                "Greenhouse Gas Emissions Intensity in lbs of CO2e per megawatt hour: 410",
                "Fossil Fuels  Natural Gas 30%  Coal and Petroleum 3%",
                "Unspecified Power (primarily fossil fuels) 10%",
                "Total 100%",
            ),
            ((200.0, 700.0, "Average"),),
        )
        path = synthetic_multipage_pdf(tmp_path / "wrapped_break.pdf", pages=[page_one, page_two])
        result = extract(path)
        assert isinstance(result, LabelDocument)
        assert "ca utility average" in result.normalized

    def test_geometry_never_joins_two_pages(self, tmp_path: Path) -> None:
        """Cells are facts about the page they came from. The word drawn alone
        on page two shares an extent with the wide line on page one by
        construction of this fixture's layout, and must not land in the same
        cell anyway."""
        from conftest import Placed, synthetic_multipage_pdf

        page_one: tuple[tuple[str, ...], Placed] = (
            (
                "Wide line spanning alpha beta",
                "Greenhouse Gas Emissions Intensity in lbs of CO2e per megawatt hour: 410",
                "Fossil Fuels  Natural Gas 30%  Coal and Petroleum 3%",
                "Unspecified Power (primarily fossil fuels) 10%",
            ),
            (),
        )
        page_two: tuple[tuple[str, ...], Placed] = (
            (
                "alpha",
                "Renewables and Zero-Carbon Resources",
                "RPS Eligible Renewables 40%",
                "Solar 20%  Wind 12%  Geothermal 5%",
                "Total 100%",
            ),
            ((200.0, 700.0, "alpha"),),
        )
        path = synthetic_multipage_pdf(tmp_path / "two_page_cells.pdf", pages=[page_one, page_two])
        result = extract(path)
        assert isinstance(result, LabelDocument)
        assert result.cells is not None
        wide = [cell for cell in result.cells if "wide line spanning" in cell]
        assert wide, "the wide line should reconstruct into some cell"
        assert all(cell.count("alpha") == 1 for cell in wide)

    def test_a_directory_expands_to_supported_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.pdf").write_bytes(b"x")
        (tmp_path / "c.md").write_text("x")
        (tmp_path / "nested").mkdir()
        (tmp_path / "nested" / "d.txt").write_text("x")
        found = {p.name for p in discover([tmp_path])}
        assert found == {"a.txt", "b.pdf", "d.txt"}

    def test_an_empty_directory_finds_nothing(self, empty_directory: Path) -> None:
        assert discover([empty_directory]) == []

    def test_a_named_file_survives_even_if_unsupported(self, unsupported_file: Path) -> None:
        """So that an unsupported file is reported, not silently dropped."""
        assert discover([unsupported_file]) == [unsupported_file]

    def test_duplicates_collapse(self, conforming_label: Path) -> None:
        assert len(discover([conforming_label, conforming_label])) == 1

    def test_supported_suffixes_are_what_they_claim(self) -> None:
        assert SUPPORTED_SUFFIXES == (".pdf", ".txt")

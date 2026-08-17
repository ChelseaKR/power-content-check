"""Behaviour of the individual checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from power_content_check.checks import CheckContext
from power_content_check.engine import check_document
from power_content_check.extract import LabelDocument, extract
from power_content_check.model import Status

SUPPLIER = "Example Municipal Utility District"


def _statuses(path: Path, supplier: str | None = None) -> dict[str, Status]:
    report = check_document(path, CheckContext(supplier_name=supplier))
    return {r.check_id: r.status for r in report.results}


def _finding(path: Path, check_id: str, supplier: str | None = None) -> str:
    report = check_document(path, CheckContext(supplier_name=supplier))
    return next(r.finding for r in report.results if r.check_id == check_id)


class TestConformingLabel:
    def test_every_implemented_check_conforms(self, conforming_label: Path) -> None:
        from power_content_check.checks import implemented_checks

        statuses = _statuses(conforming_label, SUPPLIER)
        failures = {
            c.spec.id: statuses[c.spec.id]
            for c in implemented_checks()
            if statuses[c.spec.id] is not Status.CONFORMS
        }
        assert failures == {}

    def test_unimplemented_checks_stay_not_evaluated(self, conforming_label: Path) -> None:
        from power_content_check.checks import unimplemented_checks

        statuses = _statuses(conforming_label, SUPPLIER)
        for check in unimplemented_checks():
            assert statuses[check.spec.id] is Status.NOT_EVALUATED

    def test_a_clean_label_with_a_supplier_name_still_exits_two(
        self, conforming_label: Path
    ) -> None:
        """Because the registered-but-unimplemented checks are honest about the gap."""
        from power_content_check.engine import check_paths
        from power_content_check.model import ExitCode

        report = check_paths([conforming_label], CheckContext(supplier_name=SUPPLIER))
        assert report.exit_code == ExitCode.NOT_EVALUATED
        assert report.summary["does_not_conform"] == 0


class TestDeficientLabel:
    @pytest.mark.parametrize(
        "check_id",
        [
            "PCL002",  # no telephone number
            "PCL004",  # Energy Commission not named
            "PCL005",  # no energy.ca.gov address
            "PCL006",  # geothermal row absent
            "PCL010",  # units not stated
            "PCL011",  # retired unbundled RECs not disclosed
            "PCL012",  # unspecified power not annotated
            "PCL013",  # footnote (l)(1) absent
            "PCL014",  # footnote (l)(2) absent
            "PCL015",  # footnote (l)(3) absent
            "PCL016",  # no statewide disclosure
            "PCL017",  # no data year
            "PCL018",  # a displayed total is not 100 percent
        ],
    )
    def test_expected_deviations_are_reported(self, deficient_label: Path, check_id: str) -> None:
        assert _statuses(deficient_label)[check_id] is Status.DOES_NOT_CONFORM

    @pytest.mark.parametrize("check_id", ["PCL003", "PCL007", "PCL008", "PCL009"])
    def test_what_is_present_is_not_flagged(self, deficient_label: Path, check_id: str) -> None:
        assert _statuses(deficient_label)[check_id] is Status.CONFORMS

    def test_missing_fuel_type_is_named_in_the_finding(self, deficient_label: Path) -> None:
        assert "geothermal" in _finding(deficient_label, "PCL006")

    def test_off_total_is_reported_with_its_value(self, deficient_label: Path) -> None:
        assert "97" in _finding(deficient_label, "PCL018")


class TestSupplierName:
    def test_absent_supplier_name_is_not_a_pass(self, conforming_label: Path) -> None:
        assert _statuses(conforming_label)["PCL001"] is Status.NOT_EVALUATED

    def test_matching_supplier_name_conforms(self, conforming_label: Path) -> None:
        assert _statuses(conforming_label, SUPPLIER)["PCL001"] is Status.CONFORMS

    def test_wrong_supplier_name_does_not_conform(self, conforming_label: Path) -> None:
        statuses = _statuses(conforming_label, "Some Other Utility")
        assert statuses["PCL001"] is Status.DOES_NOT_CONFORM

    def test_supplier_name_matching_ignores_punctuation_and_case(
        self, conforming_label: Path
    ) -> None:
        statuses = _statuses(conforming_label, "EXAMPLE MUNICIPAL UTILITY DISTRICT")
        assert statuses["PCL001"] is Status.CONFORMS


class TestEveryDeviationSaysWhatWasLookedAt:
    """A deviation is an absence from extracted text, and says so.

    Two of the deviations this tool reports against published labels are the
    absence of a telephone number and the absence of the words "Energy
    Commission". Whether that is a property of the document or a limit of PDF
    text extraction is the difference between a fact and an accusation, so the
    answer is attached to the finding itself.
    """

    def _details(self, path: Path) -> list[str]:
        report = check_document(path, CheckContext())
        return [r.detail or "" for r in report.results if r.status is Status.DOES_NOT_CONFORM]

    def test_a_deviation_on_a_text_input_names_the_input(self, deficient_label: Path) -> None:
        details = self._details(deficient_label)
        assert details
        assert all("plain text file" in detail for detail in details)

    def test_a_deviation_on_an_illustrated_pdf_names_the_artwork(
        self, illustrated_pdf: Path
    ) -> None:
        details = self._details(illustrated_pdf)
        assert details
        assert all("embeds 5 images" in detail for detail in details)

    def test_a_deviation_on_an_unillustrated_pdf_says_so(self, text_layer_pdf: Path) -> None:
        details = self._details(text_layer_pdf)
        assert details
        assert all("embeds no image" in detail for detail in details)

    def test_the_finding_itself_claims_only_the_extracted_text(self, deficient_label: Path) -> None:
        assert "extracted text" in _finding(deficient_label, "PCL002")
        assert "extracted text" in _finding(deficient_label, "PCL004")


class TestEnergyCommissionNaming:
    """PCL004 reports what is present, not only what is missing."""

    def _result(self, tmp_path: Path, body: str) -> tuple[Status, str]:
        from power_content_check.checks import BY_ID

        path = tmp_path / "synthetic.txt"
        path.write_text(body + "\n" + ("filler line for length. " * 20))
        document = extract(path)
        assert isinstance(document, LabelDocument)
        run = BY_ID["PCL004"].run
        assert run is not None
        result = run(document, CheckContext())
        return result.status, result.detail or ""

    def test_the_abbreviation_is_reported_but_not_accepted(self, tmp_path: Path) -> None:
        status, detail = self._result(tmp_path, "Visit the CEC webpage at the link below.")
        assert status is Status.DOES_NOT_CONFORM
        assert "the abbreviation 'CEC'" in detail
        assert "nowhere defines 'CEC'" in detail

    def test_the_defined_term_conforms(self, tmp_path: Path) -> None:
        status, _ = self._result(tmp_path, "Contact the California Energy Commission.")
        assert status is Status.CONFORMS


class TestNarrowMatching:
    """Prose must not satisfy a check that is about a row of the table."""

    def _doc(self, tmp_path: Path, body: str) -> LabelDocument:
        path = tmp_path / "synthetic.txt"
        path.write_text(body + "\n" + ("filler line for length. " * 20))
        document = extract(path)
        assert isinstance(document, LabelDocument)
        return document

    def test_footnote_mention_of_unbundled_recs_does_not_satisfy_pcl011(
        self, tmp_path: Path
    ) -> None:
        from power_content_check.checks import BY_ID

        body = (
            "RECs that are purchased separately from the renewable energy "
            '("Unbundled RECs") can be used for RPS compliance.'
        )
        run = BY_ID["PCL011"].run
        assert run is not None
        assert run(self._doc(tmp_path, body), CheckContext()).status is Status.DOES_NOT_CONFORM

    def test_prose_mention_of_geothermal_does_not_satisfy_the_row(self, tmp_path: Path) -> None:
        from power_content_check.checks import _fuel_row_present

        body = "GHG intensity figures exclude emissions from geothermal sources entirely."
        present, how = _fuel_row_present(self._doc(tmp_path, body), "geothermal")
        assert not present
        assert how == "absent"

    def test_a_geothermal_row_does_satisfy_it(self, tmp_path: Path) -> None:
        from power_content_check.checks import _fuel_row_present

        present, how = _fuel_row_present(self._doc(tmp_path, "Geothermal 5% 0% 5%"), "geothermal")
        assert present
        assert how == "row"

    def test_an_inline_figure_also_satisfies_it(self, tmp_path: Path) -> None:
        from power_content_check.checks import _fuel_row_present

        body = "Sources this year: geothermal 5%, solar 20%."
        present, how = _fuel_row_present(self._doc(tmp_path, body), "geothermal")
        assert present
        assert how == "figure"


class TestTextTheExtractorBrokeApart:
    """A phrase split by the way a page was drawn is not a phrase the label lacks.

    Both cases here were found by running the tool over published labels. Both
    produced a deviation against a named supplier for something the document
    plainly carries, which is the failure this project exists to avoid.
    """

    def _run(self, tmp_path: Path, check_id: str, body: str) -> tuple[Status, str]:
        from power_content_check.checks import BY_ID

        path = tmp_path / "synthetic.txt"
        path.write_text(body + "\n" + ("filler line for length. " * 20))
        document = extract(path)
        assert isinstance(document, LabelDocument)
        run = BY_ID[check_id].run
        assert run is not None
        result = run(document, CheckContext())
        return result.status, result.finding

    def test_a_subscript_does_not_hide_the_ghg_footnote(self, tmp_path: Path) -> None:
        """The issued labels set the 2 of CO2 as a subscript, which extracts split."""
        body = (
            "GHG intensity figures exclude biogenic CO\n"
            "2 and emissions from geothermal sources and grandfathered imports of "
            "firmed-and-shaped energy."
        )
        status, _ = self._run(tmp_path, "PCL014", body)
        assert status is Status.CONFORMS

    def test_a_footnote_that_is_really_absent_is_still_reported(self, tmp_path: Path) -> None:
        status, finding = self._run(tmp_path, "PCL014", "Solar 14% Wind 10%")
        assert status is Status.DOES_NOT_CONFORM
        assert "extracted text" in finding

    def test_a_wrapped_column_heading_is_not_evaluated(self, tmp_path: Path) -> None:
        """Two headings side by side, each wrapping, extract interleaved."""
        body = "2024 SDG and E CA Utility\nPower Mix Average\nSolar 24% 23%"
        status, finding = self._run(tmp_path, "PCL016", body)
        assert status is Status.NOT_EVALUATED
        assert "not together" in finding

    def test_a_heading_that_is_really_absent_is_still_reported(self, tmp_path: Path) -> None:
        status, _ = self._run(tmp_path, "PCL016", "Standard Plan 32% Green Plan 100%")
        assert status is Status.DOES_NOT_CONFORM

    def test_an_intact_heading_still_conforms(self, tmp_path: Path) -> None:
        status, _ = self._run(tmp_path, "PCL016", "Standard Rate CA Utility Average")
        assert status is Status.CONFORMS


class TestUnspecifiedPowerAnnotation:
    def _run(self, tmp_path: Path, body: str) -> tuple[Status, str]:
        from power_content_check.checks import BY_ID

        path = tmp_path / "synthetic.txt"
        path.write_text(body + "\n" + ("filler line for length. " * 20))
        document = extract(path)
        assert isinstance(document, LabelDocument)
        run = BY_ID["PCL012"].run
        assert run is not None
        result = run(document, CheckContext())
        return result.status, result.finding

    def test_fossil_fuels_annotation_conforms(self, tmp_path: Path) -> None:
        status, _ = self._run(tmp_path, "Unspecified Power (primarily fossil fuels) 22%")
        assert status is Status.CONFORMS

    def test_renewables_annotation_conforms(self, tmp_path: Path) -> None:
        status, _ = self._run(
            tmp_path,
            "Unspecified Power (primarily renewables and zero-carbon resources) 22%",
        )
        assert status is Status.CONFORMS

    def test_an_invented_group_name_does_not_conform(self, tmp_path: Path) -> None:
        status, finding = self._run(tmp_path, "Unspecified Power (primarily hydrogen) 22%")
        assert status is Status.DOES_NOT_CONFORM
        assert "hydrogen" in finding


class TestDisplayedTotals:
    def _run(self, tmp_path: Path, body: str) -> tuple[Status, str]:
        from power_content_check.checks import BY_ID

        path = tmp_path / "synthetic.txt"
        path.write_text(body + "\n" + ("filler line for length. " * 20))
        document = extract(path)
        assert isinstance(document, LabelDocument)
        run = BY_ID["PCL018"].run
        assert run is not None
        result = run(document, CheckContext())
        return result.status, result.finding

    def test_no_total_row_is_not_evaluated(self, tmp_path: Path) -> None:
        status, finding = self._run(tmp_path, "Solar 14%")
        assert status is Status.NOT_EVALUATED
        assert "no total row" in finding.lower()

    def test_hundred_percent_conforms(self, tmp_path: Path) -> None:
        status, _ = self._run(tmp_path, "Total 100% 100% 100%")
        assert status is Status.CONFORMS

    def test_a_decimal_hundred_conforms(self, tmp_path: Path) -> None:
        status, _ = self._run(tmp_path, "Total 100.0% 100.0%")
        assert status is Status.CONFORMS


class TestGhgUnits:
    def _run(self, tmp_path: Path, body: str) -> tuple[Status, str]:
        from power_content_check.checks import BY_ID

        path = tmp_path / "synthetic.txt"
        path.write_text(body + "\n" + ("filler line for length. " * 20))
        document = extract(path)
        assert isinstance(document, LabelDocument)
        run = BY_ID["PCL010"].run
        assert run is not None
        result = run(document, CheckContext())
        return result.status, result.finding

    def test_absent_disclosure_is_reported_as_absent(self, tmp_path: Path) -> None:
        status, finding = self._run(tmp_path, "Solar 14%")
        assert status is Status.DOES_NOT_CONFORM
        assert "No greenhouse gas emissions intensity" in finding

    def test_mwh_shorthand_is_accepted(self, tmp_path: Path) -> None:
        status, _ = self._run(tmp_path, "GHG emissions intensity: 410 lbs CO2e/MWh")
        assert status is Status.CONFORMS

    def test_missing_units_are_named(self, tmp_path: Path) -> None:
        status, finding = self._run(tmp_path, "Greenhouse gas emissions intensity 410")
        assert status is Status.DOES_NOT_CONFORM
        assert "CO2e" in finding

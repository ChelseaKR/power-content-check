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
        assert all("declares no image and paints no vector shape" in detail for detail in details)

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
        body = "2024 Example Utility CA Utility\nPower Mix Average\nSolar 24% 23%"
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

    # Section 1393.1(c)(7) requires the display to be annotated to identify a
    # group. It prescribes no punctuation, unlike subdivision (l), whose
    # footnote text is set out verbatim. A label that identifies the group
    # after a dash, a colon or nothing at all has done what the subdivision
    # says, and a deviation reported against it would be this tool enforcing a
    # bracket no published source asks for.

    @pytest.mark.parametrize(
        "body",
        [
            "Unspecified Power - primarily fossil fuels 22%",
            "Unspecified Power: primarily fossil fuels 22%",
            "Unspecified Power primarily fossil fuels 22%",
            "Unspecified Power (primarily fossil fuels 22%",
            "Unspecified Power [primarily fossil fuels] 22%",
        ],
    )
    def test_the_annotation_conforms_whatever_punctuation_carries_it(
        self, tmp_path: Path, body: str
    ) -> None:
        assert self._run(tmp_path, body)[0] is Status.CONFORMS

    def test_the_second_group_conforms_without_parentheses(self, tmp_path: Path) -> None:
        status, _ = self._run(
            tmp_path, "Unspecified Power - primarily renewables and zero-carbon resources 22%"
        )
        assert status is Status.CONFORMS

    def test_an_invented_group_without_parentheses_names_what_it_saw(self, tmp_path: Path) -> None:
        # Losing the bracket must not lose the distinction between an
        # annotation naming the wrong group and no annotation at all.
        status, finding = self._run(tmp_path, "Unspecified Power - primarily hydrogen 22%")
        assert status is Status.DOES_NOT_CONFORM
        assert "hydrogen" in finding

    # Guards on the looseness that dropping the closing bracket could invite.
    # Both hold before and after the change: the group name has to be what
    # follows "primarily", not merely something that appears later on the page.

    @pytest.mark.parametrize(
        "body",
        [
            "Unspecified Power - primarily imported power from fossil fuels 22%",
            "Unspecified Power - primarily hydrogen. Fossil fuels are also used. 22%",
            "Unspecified Power 22% 0% 31%\nOur mix is primarily fossil fuels.",
        ],
    )
    def test_a_group_name_further_down_the_line_does_not_satisfy_it(
        self, tmp_path: Path, body: str
    ) -> None:
        assert self._run(tmp_path, body)[0] is Status.DOES_NOT_CONFORM


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

    def test_multiple_total_rows_flags_deviation_in_later_row(self, tmp_path: Path) -> None:
        body = (
            "Total 100% 100% 100%\n"
            "Retail sales covered by retired unbundled RECs 4% 0%\n"
            "Total 99% 97%"
        )
        status, finding = self._run(tmp_path, body)
        assert status is Status.DOES_NOT_CONFORM
        assert "99" in finding
        assert "97" in finding

    def test_multiple_conforming_total_rows_conforms(self, tmp_path: Path) -> None:
        status, finding = self._run(
            tmp_path,
            "Total 100% 100%\nTotal 100% 100%",
        )
        assert status is Status.CONFORMS
        assert "All 4 displayed column totals are 100 percent" in finding

    def test_deviation_finding_names_the_specific_row_it_came_from(self, tmp_path: Path) -> None:
        # A deviation must be traceable to which of several total rows
        # produced it, not just pooled into an unattributed list of numbers.
        status, finding = self._run(
            tmp_path,
            "Total 100% 100%\nTotal 99% 97%",
        )
        assert status is Status.DOES_NOT_CONFORM
        # The finding cites the matched (normalized-lowercase) row text.
        assert "total 99% 97%" in finding
        assert "total 100% 100%" not in finding


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


class TestAWebAddressIsNotAnEmailAddress:
    """An email address is not a website address, and must not satisfy one.

    Section 1393.1(c)(4) lists a website address for the retail supplier and a
    website address for the Energy Commission. A label whose only contact is an
    email address carries neither, and a check that read the domain half of an
    address as a website would report CONFORMS on a document that deviates.
    """

    def _doc(self, tmp_path: Path, body: str) -> LabelDocument:
        path = tmp_path / "synthetic.txt"
        path.write_text(body + "\n" + ("filler line for length. " * 20))
        document = extract(path)
        assert isinstance(document, LabelDocument)
        return document

    def _run(self, tmp_path: Path, check_id: str, body: str) -> tuple[Status, str]:
        from power_content_check.checks import BY_ID

        run = BY_ID[check_id].run
        assert run is not None
        result = run(self._doc(tmp_path, body), CheckContext())
        return result.status, (result.detail or "") + " " + result.finding

    def test_a_supplier_email_alone_does_not_satisfy_pcl003(self, tmp_path: Path) -> None:
        status, _ = self._run(
            tmp_path, "PCL003", "Example Utility\nbilling@example-utility.example.com"
        )
        assert status is Status.DOES_NOT_CONFORM

    def test_an_energy_ca_gov_email_alone_does_not_satisfy_pcl005(self, tmp_path: Path) -> None:
        status, _ = self._run(tmp_path, "PCL005", "Questions about this label: pscd@energy.ca.gov")
        assert status is Status.DOES_NOT_CONFORM

    def test_pcl004_does_not_offer_an_email_as_the_web_address_it_saw(self, tmp_path: Path) -> None:
        status, text = self._run(tmp_path, "PCL004", "Write to the CEC at pscd@energy.ca.gov")
        assert status is Status.DOES_NOT_CONFORM
        assert "an energy.ca.gov web address" not in text

    def test_the_scrub_removes_only_the_address(self, tmp_path: Path) -> None:
        from power_content_check.checks import _domains

        document = self._doc(
            tmp_path,
            "Email billing@example-utility.example.com or visit www.example-utility.example.com",
        )
        assert _domains(document) == ["www.example-utility.example.com"]

    # Positive controls. Both hold before and after the change, and guard the
    # opposite error: a scrub that took a real website out with the email.

    def test_a_website_alone_still_satisfies_pcl003(self, tmp_path: Path) -> None:
        status, _ = self._run(
            tmp_path, "PCL003", "Example Utility\nwww.example-utility.example.com"
        )
        assert status is Status.CONFORMS

    def test_a_website_beside_an_email_still_satisfies_pcl003(self, tmp_path: Path) -> None:
        status, _ = self._run(
            tmp_path,
            "PCL003",
            "Email billing@example-utility.example.com or visit www.example-utility.example.com",
        )
        assert status is Status.CONFORMS


class TestTheDeviationBranchesNothingHadReached:
    """Failure paths that no test in this suite ever ran.

    Every implemented check has a reachable `_bad` call, so reading the source
    tells you nothing is missing. Running the suite with `_bad` instrumented
    tells you something else: PCL008 and PCL009 never reported
    DOES_NOT_CONFORM once across all 438 tests. Both are only ever asserted to
    CONFORM, by `TestConformingLabel` over the clean fixture and by
    `TestDeficientLabel.test_what_is_present_is_not_flagged` over the
    deficient one, which carries the very text they look for.

    So the whole deviation half of both checks was unheld. Rewriting either
    `return _bad(...)` as `return _ok(...)`, which makes the check report
    conformance on a label missing the thing it exists to look for, left all
    438 tests passing and total coverage unchanged at 96.65 percent. Neither
    the suite nor the coverage floor could see it, because the lines were
    never executed either way: they were exactly two of the four uncovered
    statements in `checks.py`, at lines 340 and 352.

    A check whose deviation branch nothing reaches is a check that cannot
    fail, which is the defect class the rest of this pass is about, sitting
    inside the checks themselves rather than in the harness around them.

    The other two uncovered statements are here for the same reason: PCL002's
    "exactly one number" case, which is a distinct deviation from its
    "no number" case, and the line in PCL004 that reports an energy.ca.gov
    web address among what was seen instead. Both belong to checks that can
    still fail by other routes, so they are narrower gaps, but they are the
    same shape and this is the file they belong in.
    """

    def _doc(self, tmp_path: Path, body: str) -> LabelDocument:
        path = tmp_path / "synthetic.txt"
        path.write_text(body + "\n" + ("filler line for length. " * 20))
        document = extract(path)
        assert isinstance(document, LabelDocument)
        return document

    def _run(self, tmp_path: Path, check_id: str, body: str) -> tuple[Status, str]:
        from power_content_check.checks import BY_ID

        run = BY_ID[check_id].run
        assert run is not None
        result = run(self._doc(tmp_path, body), CheckContext())
        return result.status, (result.detail or "") + " " + result.finding

    def test_pcl008_deviates_when_rps_eligible_renewables_is_not_named(
        self, tmp_path: Path
    ) -> None:
        """The subcategory of section 1393.1(c)(2)(A) is absent."""
        status, text = self._run(
            tmp_path,
            "PCL008",
            "Renewables and Zero-Carbon Resources\nSolar 20%\nWind 15%\nFossil Fuels\n",
        )
        assert status is Status.DOES_NOT_CONFORM
        assert "RPS-eligible renewables do not appear" in text

    def test_pcl008_conforms_when_it_is_named(self, tmp_path: Path) -> None:
        """The positive control, so the test above is not passing on a document
        the extractor could not read."""
        status, _ = self._run(
            tmp_path,
            "PCL008",
            "Renewables and Zero-Carbon Resources\nRPS-Eligible Renewables 30%\n",
        )
        assert status is Status.CONFORMS

    def test_pcl009_deviates_when_the_fossil_fuels_group_is_absent(self, tmp_path: Path) -> None:
        """The group of section 1393.1(c)(2)(B) is absent."""
        status, text = self._run(
            tmp_path,
            "PCL009",
            "Renewables and Zero-Carbon Resources\nRPS-Eligible Renewables 30%\nLarge Hydro 10%\n",
        )
        assert status is Status.DOES_NOT_CONFORM
        assert "Fossil Fuels" in text

    def test_pcl009_conforms_when_the_group_appears(self, tmp_path: Path) -> None:
        """The positive control."""
        status, _ = self._run(tmp_path, "PCL009", "Fossil Fuels\nNatural Gas 40%\nCoal 5%\n")
        assert status is Status.CONFORMS

    def test_pcl002_deviates_on_exactly_one_telephone_number(self, tmp_path: Path) -> None:
        """One number is its own deviation, not the same one as none.

        Section 1393.1(c)(4) lists a number for the retail supplier and a
        number for the Energy Commission. A label carrying one of the two is
        the case this branch reports, and it says so in different words than
        the no-number branch, which is the branch the deficient fixture hits.
        """
        status, text = self._run(
            tmp_path, "PCL002", "Example Utility\nCustomer service: (800) 555-0101\n"
        )
        assert status is Status.DOES_NOT_CONFORM
        assert "Only one telephone number" in text

    def test_pcl004_names_an_energy_ca_gov_web_address_among_what_it_saw(
        self, tmp_path: Path
    ) -> None:
        """The label carries the Commission's website but never its name.

        PCL004 asks whether the Energy Commission is named. When it is not,
        the check reports what was present instead, and a real web address is
        one of the things it can report. `TestAWebAddressIsNotAnEmailAddress`
        holds the negative, that an email address must not be offered here.
        Nothing held the positive, so the line that builds it never ran.
        """
        status, text = self._run(
            tmp_path, "PCL004", "Questions about this label: visit www.energy.ca.gov for details.\n"
        )
        assert status is Status.DOES_NOT_CONFORM
        assert "an energy.ca.gov web address" in text


def _arabic_indic(text: str) -> str:
    """Rewrite ASCII digits as ARABIC-INDIC DIGIT ZERO through NINE.

    Built from the code point rather than written as literals, so this file
    stays ASCII and the linter's ambiguous-character rule does not have to be
    silenced to let a test in.
    """
    return "".join(chr(0x0660 + int(c)) if c in "0123456789" else c for c in text)


class TestDigitsTheToolCanActuallyRead:
    """A pattern must not match digits the value derivation cannot read.

    The Unicode digit class escape matches 680 characters, of which ten are
    ASCII. Everything downstream of these patterns is ASCII only: ``_phones``
    strips everything outside ``0-9``, a matched percentage is converted for
    comparison, and a matched year is printed as the data year. Where the
    pattern is wider than the derivation, the tool reports a number it never
    read, and in PCL002 that was a pass: an Arabic-Indic telephone number
    reduced to the empty string, which then counted as one of the two distinct
    numbers section 1393.1(c)(4) lists.
    """

    def _doc(self, tmp_path: Path, body: str) -> LabelDocument:
        path = tmp_path / "synthetic.txt"
        path.write_text(body + "\n" + ("filler line for length. " * 20))
        document = extract(path)
        assert isinstance(document, LabelDocument)
        return document

    def _run(self, tmp_path: Path, check_id: str, body: str) -> tuple[Status, str]:
        from power_content_check.checks import BY_ID

        run = BY_ID[check_id].run
        assert run is not None
        result = run(self._doc(tmp_path, body), CheckContext())
        return result.status, (result.detail or "") + " " + result.finding

    def test_a_number_whose_digits_were_discarded_is_not_a_second_number(
        self, tmp_path: Path
    ) -> None:
        status, _ = self._run(
            tmp_path,
            "PCL002",
            "Example Utility (555) 555-0100\nEnergy Commission " + _arabic_indic("916 555 0199"),
        )
        assert status is not Status.CONFORMS

    def test_no_telephone_key_is_empty(self, tmp_path: Path) -> None:
        from power_content_check.checks import _phones

        document = self._doc(tmp_path, "Call " + _arabic_indic("555 555 0100"))
        assert "" not in _phones(document)

    def test_a_total_row_the_tool_cannot_read_is_not_evaluated(self, tmp_path: Path) -> None:
        status, _ = self._run(tmp_path, "PCL018", "Total " + _arabic_indic("100") + "%")
        assert status is Status.NOT_EVALUATED

    def test_a_title_year_the_tool_cannot_read_is_not_a_data_year(self, tmp_path: Path) -> None:
        status, _ = self._run(
            tmp_path, "PCL017", "20" + _arabic_indic("24") + " POWER CONTENT LABEL"
        )
        assert status is Status.DOES_NOT_CONFORM

    def test_a_figure_the_tool_cannot_read_is_not_a_figure(self, tmp_path: Path) -> None:
        from power_content_check.checks import _fuel_row_present

        document = self._doc(
            tmp_path, "Sources this year: geothermal " + _arabic_indic("5") + "%, solar 20%."
        )
        assert _fuel_row_present(document, "geothermal") == (False, "absent")

    # Positive controls. Every one of these is the ASCII case of a test above,
    # and every one passes before and after the change.

    def test_two_ascii_telephone_numbers_still_conform(self, tmp_path: Path) -> None:
        status, _ = self._run(
            tmp_path, "PCL002", "Example Utility (555) 555-0100\nEnergy Commission 916 555-0199"
        )
        assert status is Status.CONFORMS

    def test_an_ascii_total_row_still_conforms(self, tmp_path: Path) -> None:
        assert self._run(tmp_path, "PCL018", "Total 100% 100%")[0] is Status.CONFORMS

    def test_an_ascii_title_year_still_conforms(self, tmp_path: Path) -> None:
        assert self._run(tmp_path, "PCL017", "2024 POWER CONTENT LABEL")[0] is Status.CONFORMS

    def test_an_ascii_figure_is_still_a_figure(self, tmp_path: Path) -> None:
        from power_content_check.checks import _fuel_row_present

        document = self._doc(tmp_path, "Sources this year: geothermal 5%, solar 20%.")
        assert _fuel_row_present(document, "geothermal") == (True, "figure")

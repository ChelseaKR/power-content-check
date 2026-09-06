"""The advisory channel says things, and cannot decide anything.

A second channel beside the checks is a place a rule can be smuggled: it has no
citation to justify, no entry in the catalog, and no line in the exit-code
table, so an observation phrased as an obligation would be a check that never
had to argue for itself. ADR 0013 fences that off in five ways and every one of
them is a test here.

The other half is that the channel has to actually fire. A code space nothing
raises reads exactly like a clean label, so each of the three codes is raised
against a document built to raise it, and the conforming fixture is asserted to
raise none.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from conftest import synthetic_label_pdf, synthetic_multipage_pdf
from power_content_check.advisory import (
    ADVISORY_CODES,
    NOTICE,
    Advisory,
    AdvisoryClaimsARequirement,
    UnregisteredAdvisory,
    broken_phrases,
    data_years,
    observe,
    textless_pages,
)
from power_content_check.checks import CHECKS
from power_content_check.cli import main
from power_content_check.engine import check_document, check_paths, fingerprint
from power_content_check.extract import LabelDocument, extract
from power_content_check.model import CheckResult, ExitCode, Status
from power_content_check.report import render_json, render_text

READABLE_PADDING = "padding words to clear the readability floor. " * 12


def _document(tmp_path: Path, name: str, text: str) -> LabelDocument:
    path = tmp_path / name
    path.write_text(text + "\n" + READABLE_PADDING)
    outcome = extract(path)
    assert isinstance(outcome, LabelDocument), outcome
    return outcome


# ---------------------------------------------------------------------------
# the fence
# ---------------------------------------------------------------------------


class TestAnAdvisoryIsNotAResult:
    def test_it_is_not_a_check_result(self) -> None:
        advisory = Advisory("ADV-TEXTLESS-PAGE", "A page yielded no text.")
        assert not isinstance(advisory, CheckResult)

    def test_it_carries_no_status_severity_or_citation(self) -> None:
        """The three things that would let it act like a rule.

        Asserted as the exact field set rather than as three absences, so a
        field added later has to come through this test.
        """
        names = {field.name for field in dataclasses.fields(Advisory)}
        assert names == {"code", "observation", "where"}
        for forbidden in ("status", "severity", "citation", "check_id", "basis"):
            assert not hasattr(Advisory("ADV-TEXTLESS-PAGE", "Noticed."), forbidden)

    def test_every_advisory_carries_the_same_notice(self) -> None:
        advisory = Advisory("ADV-TEXTLESS-PAGE", "Noticed.")
        assert advisory.notice == NOTICE
        assert advisory.to_dict()["notice"] == NOTICE
        assert "no published requirement" in NOTICE.lower()


class TestTheCodeSpaceIsClosed:
    def test_the_registered_codes_are_exactly_these_three(self) -> None:
        """Pinned, so a fourth arrives in a diff with its reasoning beside it."""
        assert ADVISORY_CODES == (
            "ADV-BROKEN-PHRASE",
            "ADV-DATA-YEAR-MISMATCH",
            "ADV-TEXTLESS-PAGE",
        )

    @pytest.mark.parametrize("code", ["PCL099", "PCL001", "ADV-ANYTHING", "", "adv-textless-page"])
    def test_an_unregistered_code_raises(self, code: str) -> None:
        with pytest.raises(UnregisteredAdvisory):
            Advisory(code, "Noticed something.")

    def test_a_check_identifier_is_not_an_advisory_code(self) -> None:
        """The specific collision the channel would be worst at.

        An advisory raised under a real check's identifier would put a sentence
        with no citation under a heading that has one.
        """
        from power_content_check.checks import CHECKS

        assert not ({c.spec.id for c in CHECKS} & set(ADVISORY_CODES))


class TestAnObservationMayNotClaimARequirement:
    @pytest.mark.parametrize(
        "observation",
        [
            "The label must carry a data year.",
            "Section 1393.1(c)(3) requires a per megawatt hour denominator.",
            "This is a deviation from the prescribed format.",
            "The document does not conform.",
            "A required element is absent.",
            "This is a compliance issue.",
        ],
    )
    def test_wording_that_reads_as_a_rule_raises(self, observation: str) -> None:
        with pytest.raises(AdvisoryClaimsARequirement):
            Advisory("ADV-TEXTLESS-PAGE", observation)

    def test_an_empty_observation_raises(self) -> None:
        """A note with nothing in it is a line the reader has to complete."""
        with pytest.raises(AdvisoryClaimsARequirement):
            Advisory("ADV-TEXTLESS-PAGE", "   ")

    def test_a_description_is_accepted(self) -> None:
        advisory = Advisory("ADV-TEXTLESS-PAGE", "Page 2 yielded no text at all.")
        assert advisory.observation.startswith("Page 2")

    @pytest.mark.parametrize("code", ADVISORY_CODES)
    def test_every_observation_this_tool_actually_raises_passes_its_own_fence(
        self, code: str, tmp_path: Path
    ) -> None:
        """The fence has to admit the wording the observers use.

        A refusal list that also refused this tool's own sentences would be
        discovered on a real label rather than here.
        """
        raised = {a.code for a in self._every_advisory(tmp_path)}
        assert code in raised, f"nothing in this suite raises {code}"

    @staticmethod
    def _every_advisory(tmp_path: Path) -> list[Advisory]:
        found = list(
            observe(
                _document(
                    tmp_path,
                    "both.txt",
                    "2025 POWER CONTENT LABEL\n"
                    "This label covers reporting year 2024.\n"
                    "Greenhouse Gas Emissions Intensity in lbs of CO 2e per megawatt hour 410",
                )
            )
        )
        pdf = synthetic_multipage_pdf(
            tmp_path / "blank_second.pdf",
            [(("2024 POWER CONTENT LABEL", "Solar 20%", READABLE_PADDING), ()), ((), ())],
        )
        outcome = extract(pdf)
        assert isinstance(outcome, LabelDocument)
        return found + observe(outcome)


class TestNothingHereReachesAConclusion:
    def test_an_advisory_does_not_change_the_exit_code(
        self, tmp_path: Path, conforming_label: Path
    ) -> None:
        """Run over the one check that conforms, so exit 0 is actually reachable.

        Over the full catalog every run exits 2, because seventeen registered
        checks enforce nothing and always report not evaluated, and 2 outranks
        1. So an advisory wired into the exit code would change nothing on a
        full run and this test would pass over the leak. Measured: it did.
        Narrowing the registry to PCL010 puts the run at 0, which is the one
        value an advisory could move.
        """
        one_check = tuple(c for c in CHECKS if c.spec.id == "PCL010")
        assert len(one_check) == 1

        clean = check_paths([conforming_label], registry=one_check)
        assert clean.exit_code == ExitCode.OK, "the clean run is not at a movable value"
        assert not clean.documents[0].advisories

        noisy = tmp_path / "noisy.txt"
        noisy.write_text(
            conforming_label.read_text(encoding="utf-8").replace("CO2e", "CO 2e"),
            encoding="utf-8",
        )
        with_notes = check_paths([noisy], registry=one_check)
        assert with_notes.documents[0].advisories
        assert with_notes.documents[0].results[0].status is Status.CONFORMS
        assert with_notes.exit_code == ExitCode.OK

    def test_an_advisory_does_not_change_a_fingerprint(
        self, tmp_path: Path, conforming_label: Path
    ) -> None:
        """A baseline recorded before advisories existed stays valid."""
        noisy = tmp_path / "noisy.txt"
        noisy.write_text(
            conforming_label.read_text(encoding="utf-8").replace("CO2e", "CO 2e"),
            encoding="utf-8",
        )
        assert check_document(noisy).advisories
        assert fingerprint(check_paths([noisy])) == fingerprint(check_paths([conforming_label]))

    def test_an_advisory_is_in_no_status_count(self, tmp_path: Path) -> None:
        document = check_document(
            _document(
                tmp_path,
                "spaced.txt",
                "2025 POWER CONTENT LABEL Greenhouse Gas Emissions Intensity "
                "in lbs of CO 2e per megawatt hour 410",
            ).path
        )
        assert document.advisories
        assert sum(document.counts.values()) == len(document.results)

    def test_advisories_are_counted_beside_the_statuses_and_not_among_them(
        self, tmp_path: Path
    ) -> None:
        report = check_paths(
            [
                _document(
                    tmp_path,
                    "spaced.txt",
                    "2025 POWER CONTENT LABEL Greenhouse Gas Emissions Intensity "
                    "in lbs of CO 2e per megawatt hour 410",
                ).path
            ]
        )
        summary = report.summary
        assert summary["advisories"] == len(report.documents[0].advisories)
        assert summary["advisories"] > 0
        assert summary["conforms"] + summary["does_not_conform"] + summary["not_evaluated"] == len(
            report.documents[0].results
        )


# ---------------------------------------------------------------------------
# the observers
# ---------------------------------------------------------------------------


class TestBrokenPhrases:
    def test_a_phrase_that_matched_only_after_the_fold_is_noticed(self, tmp_path: Path) -> None:
        doc = _document(
            tmp_path,
            "subscript.txt",
            "2025 POWER CONTENT LABEL Greenhouse Gas Emissions Intensity "
            "in lbs of CO 2e per megawatt hour 410",
        )
        found = broken_phrases(doc)
        assert [a.code for a in found] == ["ADV-BROKEN-PHRASE"]
        assert "'CO2e'" in found[0].observation

    def test_a_phrase_present_as_written_is_not_noticed(self, conforming_label: Path) -> None:
        """The channel reports the fold doing work, not the phrase being there."""
        outcome = extract(conforming_label)
        assert isinstance(outcome, LabelDocument)
        assert broken_phrases(outcome) == []

    def test_a_phrase_absent_under_both_readings_is_not_noticed(
        self, deficient_label: Path
    ) -> None:
        """That is a deviation, which PCL010 reports. Restating it here would
        be the channel doing a check's job with none of a check's citation."""
        outcome = extract(deficient_label)
        assert isinstance(outcome, LabelDocument)
        assert broken_phrases(outcome) == []

    def test_it_names_the_check_that_read_the_phrase(self, tmp_path: Path) -> None:
        doc = _document(
            tmp_path,
            "subscript.txt",
            "2025 POWER CONTENT LABEL Greenhouse Gas Emissions Intensity "
            "in lbs of CO 2e per megawatt hour 410",
        )
        assert broken_phrases(doc)[0].where == "read by PCL010"

    def test_a_broken_footnote_is_noticed_too(self, tmp_path: Path) -> None:
        """More than one check compares a prescribed string under the fold, so
        the observer must not be a special case for CO2e."""
        doc = _document(
            tmp_path,
            "footnote.txt",
            "2025 POWER CONTENT LABEL\n"
            "Unspecified power is electricity purchased from a genericized pool on the "
            "openmarket",
        )
        codes = {a.where for a in broken_phrases(doc)}
        assert "read by PCL015" in codes


class TestDataYears:
    def test_two_years_the_document_names_are_noticed(self, tmp_path: Path) -> None:
        doc = _document(
            tmp_path,
            "mismatch.txt",
            "2025 POWER CONTENT LABEL\nThis label covers reporting year 2024.",
        )
        found = data_years(doc)
        assert [a.code for a in found] == ["ADV-DATA-YEAR-MISMATCH"]
        assert "2024, 2025" in found[0].observation

    def test_one_year_is_not_a_mismatch(self, conforming_label: Path) -> None:
        outcome = extract(conforming_label)
        assert isinstance(outcome, LabelDocument)
        assert data_years(outcome) == []

    def test_the_same_year_twice_is_not_a_mismatch(self, tmp_path: Path) -> None:
        doc = _document(
            tmp_path,
            "agreeing.txt",
            "2024 POWER CONTENT LABEL\nThis label covers calendar year 2024.",
        )
        assert data_years(doc) == []

    def test_a_year_with_no_label_on_it_is_not_read_as_a_data_year(self, tmp_path: Path) -> None:
        """The observer reads the two places the document names as its period.

        A telephone number, a street address or a copyright line carries four
        digits too, and reading one of those as a data year would raise a note
        about a disagreement that does not exist.
        """
        doc = _document(
            tmp_path,
            "other_numbers.txt",
            "2024 POWER CONTENT LABEL\nCopyright 2019. Suite 2020. Call (555) 555-0100.",
        )
        assert data_years(doc) == []

    def test_the_deficient_fixture_raises_no_year_note(self, deficient_label: Path) -> None:
        outcome = extract(deficient_label)
        assert isinstance(outcome, LabelDocument)
        assert data_years(outcome) == []


class TestTextlessPages:
    def test_a_blank_page_among_readable_ones_is_noticed(self, tmp_path: Path) -> None:
        pdf = synthetic_multipage_pdf(
            tmp_path / "blank_second.pdf",
            [(("2024 POWER CONTENT LABEL", "Solar 20%", READABLE_PADDING), ()), ((), ())],
        )
        outcome = extract(pdf)
        assert isinstance(outcome, LabelDocument)
        found = textless_pages(outcome)
        assert [a.code for a in found] == ["ADV-TEXTLESS-PAGE"]
        assert found[0].where == "page 2"

    def test_a_document_whose_pages_all_carry_text_is_not_noticed(
        self, text_layer_pdf: Path
    ) -> None:
        outcome = extract(text_layer_pdf)
        assert isinstance(outcome, LabelDocument)
        assert textless_pages(outcome) == []

    def test_a_plain_text_file_has_no_pages_and_raises_nothing(
        self, conforming_label: Path
    ) -> None:
        """``page_texts`` is None there, and None is not an empty list of pages."""
        outcome = extract(conforming_label)
        assert isinstance(outcome, LabelDocument)
        assert outcome.page_texts is None
        assert textless_pages(outcome) == []

    def test_a_single_page_pdf_raises_nothing(self, text_layer_pdf: Path) -> None:
        """With one page there is no page that read differently from another."""
        outcome = extract(text_layer_pdf)
        assert isinstance(outcome, LabelDocument)
        assert outcome.page_texts is not None and len(outcome.page_texts) == 1
        assert textless_pages(outcome) == []

    def test_a_document_whose_pages_are_all_blank_raises_nothing(
        self, conforming_label: Path
    ) -> None:
        """The observer fires on "some pages", never on "every page".

        Reached by constructing the document, because extraction refuses a
        document with no text before an observer ever sees one, and a branch
        nothing can reach is a branch nobody has read. If it did fire it would
        report every page of a document as the odd one out, which is a sentence
        about nothing.
        """
        outcome = extract(conforming_label)
        assert isinstance(outcome, LabelDocument)
        all_blank = dataclasses.replace(outcome, page_texts=("", "  ", ""))
        assert textless_pages(all_blank) == []

        some_blank = dataclasses.replace(outcome, page_texts=("text", "  ", ""))
        assert [a.code for a in textless_pages(some_blank)] == ["ADV-TEXTLESS-PAGE"]

    def test_a_document_with_no_text_anywhere_is_refused_before_this_runs(
        self, image_only_pdf: Path
    ) -> None:
        """ADR 0001 refuses it outright, and a refusal is not an advisory."""
        document = check_document(image_only_pdf)
        assert document.unreadable_reason
        assert document.advisories == []


# ---------------------------------------------------------------------------
# the report
# ---------------------------------------------------------------------------


class TestTheReportCarriesThem:
    @pytest.fixture
    def noisy(self, tmp_path: Path) -> Path:
        path = tmp_path / "noisy.txt"
        path.write_text(
            "2025 POWER CONTENT LABEL\nThis label covers reporting year 2024.\n"
            "Greenhouse Gas Emissions Intensity in lbs of CO 2e per megawatt hour 410\n"
            + READABLE_PADDING
        )
        return path

    def test_the_json_carries_an_advisory_array_on_each_document(self, noisy: Path) -> None:
        payload = json.loads(render_json(check_paths([noisy])))
        advisories = payload["documents"][0]["advisories"]
        assert {a["code"] for a in advisories} == {
            "ADV-BROKEN-PHRASE",
            "ADV-DATA-YEAR-MISMATCH",
        }
        assert set(advisories[0]) == {"code", "observation", "where", "notice"}

    def test_a_document_with_none_carries_an_empty_array_rather_than_no_key(
        self, conforming_label: Path
    ) -> None:
        """A missing key and an empty list read differently to a consumer.

        The first says the tool has nothing to say about advisories; the second
        says it looked and noticed nothing.
        """
        payload = json.loads(render_json(check_paths([conforming_label])))
        assert payload["documents"][0]["advisories"] == []

    def test_the_summary_counts_them(self, noisy: Path) -> None:
        payload = json.loads(render_json(check_paths([noisy])))
        assert payload["summary"]["advisories"] == 2

    def test_the_text_report_shows_them_without_verbose(self, noisy: Path) -> None:
        out = render_text(check_paths([noisy]), verbose=False)
        assert "NOTICED, AND COVERED BY NO PUBLISHED REQUIREMENT" in out
        assert "ADV-BROKEN-PHRASE" in out
        assert "no published requirement" in out.lower()

    def test_the_text_report_shows_no_section_when_there_is_nothing(
        self, conforming_label: Path
    ) -> None:
        out = render_text(check_paths([conforming_label]), verbose=True)
        assert "NOTICED, AND COVERED BY NO PUBLISHED REQUIREMENT" not in out

    def test_the_text_summary_says_they_are_in_no_count(self, noisy: Path) -> None:
        out = render_text(check_paths([noisy]))
        assert "Advisory notes:       2 (in no count above and in no exit code)" in out

    def test_the_command_line_exits_on_conformance_alone(
        self, noisy: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["check", str(noisy)])
        capsys.readouterr()
        assert code in (ExitCode.OK, ExitCode.NONCONFORMANCE, ExitCode.NOT_EVALUATED)
        assert code != ExitCode.NOTHING_CHECKED


class TestTheRefusalsStayRefused:
    def test_no_advisory_restates_a_recorded_refusal(self, tmp_path: Path) -> None:
        """ROADMAP.md's Refusals are decisions about statements, not about which
        heading a statement is printed under.

        The fuel mix sum is the one most likely to arrive here, because it is
        the one a reader most often asks for and the only reason it is refused
        is the arithmetic.
        """
        pdf = synthetic_label_pdf(tmp_path / "label.pdf")
        outcome = extract(pdf)
        assert isinstance(outcome, LabelDocument)
        text = " ".join(a.observation for a in observe(outcome))
        for refused in ("add up", "sum", "total of the rows", "rank", "score"):
            assert refused not in text.lower()

    def test_no_advisory_is_raised_for_a_conforming_document(self, conforming_label: Path) -> None:
        """The issue's first done-when. A channel that fired on a clean label
        would train a reader to ignore it."""
        outcome = extract(conforming_label)
        assert isinstance(outcome, LabelDocument)
        assert observe(outcome) == []

    def test_a_deviation_and_an_advisory_are_different_statements(self, tmp_path: Path) -> None:
        """The subscript case: PCL010 conforms and the note says the fold did it."""
        path = _document(
            tmp_path,
            "subscript.txt",
            "2025 POWER CONTENT LABEL Greenhouse Gas Emissions Intensity "
            "in lbs of CO 2e per megawatt hour 410",
        ).path
        document = check_document(path)
        pcl010 = next(r for r in document.results if r.check_id == "PCL010")
        assert pcl010.status is Status.CONFORMS
        assert [a.code for a in document.advisories] == ["ADV-BROKEN-PHRASE"]

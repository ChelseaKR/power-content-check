"""`explain` must show the work and settle nothing.

The verb exists so that a reader can tell a genuine deviation from a phrase
the extractor broke apart, which is how the two false findings recorded in ADR
0006 were found. That only holds if three things are true, and each has a test
here:

* its conclusion is the conclusion `check` reaches, for every registered check
  on both fixtures;
* the scan plans describe the checks they claim to describe, bound two ways so
  a retyped literal that drifts fails rather than misleads;
* no probe list is silently empty, because "nothing was compared" rendered as
  a clean report is this portfolio's oldest defect.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from power_content_check import checks as checks_module
from power_content_check.checks import CHECKS, CheckContext
from power_content_check.cli import main
from power_content_check.engine import check_document
from power_content_check.explain import (
    MATCH_LIMIT,
    SURFACE_CHARS,
    TRUNCATION_MARKER,
    Expression,
    Fold,
    Phrase,
    ScanPlan,
    UnknownCheck,
    assess_expression,
    assess_phrase,
    explain,
    find_check,
    plan_for,
    render_json,
    render_text,
)
from power_content_check.model import ExitCode, Status

ROOT = Path(__file__).resolve().parent.parent
CHECKS_SOURCE = (ROOT / "src" / "power_content_check" / "checks.py").read_text(encoding="utf-8")

IMPLEMENTED = [c.spec.id for c in CHECKS if c.spec.implemented]
UNIMPLEMENTED = [c.spec.id for c in CHECKS if not c.spec.implemented]

#: Every regular expression `checks.py` compiles, by its source. A plan that
#: quotes one of these is quoting the object itself, so it cannot drift.
COMPILED_SOURCES = {
    value.pattern for value in vars(checks_module).values() if isinstance(value, re.Pattern)
}


def _ctx(name: str | None = None) -> CheckContext:
    return CheckContext(supplier_name=name)


class TestTheDenominators:
    """A binding that iterates an empty set passes having checked nothing."""

    def test_there_are_implemented_checks_to_bind(self) -> None:
        assert len(IMPLEMENTED) > 10

    def test_there_are_unimplemented_checks_to_bind(self) -> None:
        assert len(UNIMPLEMENTED) > 5

    def test_the_compiled_patterns_were_actually_found(self) -> None:
        assert len(COMPILED_SOURCES) > 3


class TestEveryImplementedCheckHasAPlan:
    @pytest.mark.parametrize("check_id", IMPLEMENTED)
    def test_a_plan_exists(self, check_id: str) -> None:
        assert plan_for(check_id, _ctx("Example Municipal Utility District")) is not None

    @pytest.mark.parametrize("check_id", UNIMPLEMENTED)
    def test_a_check_that_enforces_nothing_has_no_plan(self, check_id: str) -> None:
        """A plan for a check that enforces nothing would describe a scan that
        never happens, which is a fiction with the shape of evidence."""
        assert plan_for(check_id, _ctx()) is None

    @pytest.mark.parametrize("check_id", IMPLEMENTED)
    def test_a_plan_names_a_surface(self, check_id: str) -> None:
        plan = plan_for(check_id, _ctx("Example Municipal Utility District"))
        assert plan is not None
        assert plan.reads


class TestThePlansDescribeTheChecks:
    """The anti drift binding, in two directions.

    A plan is a description of a check maintained beside it, not a derivation
    of it, so a literal retyped into a plan can drift from the literal the
    check matches. These two tests are what makes that drift loud. The first
    proves every literal a plan quotes is a literal `checks.py` contains. The
    second proves that on a document every implemented check passes, something
    each check declares actually matched, which catches a plan quoting a real
    literal that the named check does not use.
    """

    @pytest.mark.parametrize("check_id", IMPLEMENTED)
    def test_every_phrase_a_plan_quotes_occurs_in_the_check_module(self, check_id: str) -> None:
        plan = plan_for(check_id, _ctx())
        assert plan is not None
        for phrase in plan.phrases:
            assert phrase.text in CHECKS_SOURCE, (
                f"{check_id} declares the phrase {phrase.text!r}, which does not occur "
                f"in checks.py at all"
            )

    @pytest.mark.parametrize("check_id", IMPLEMENTED)
    def test_every_pattern_a_plan_quotes_is_one_the_check_module_writes(
        self, check_id: str
    ) -> None:
        plan = plan_for(check_id, _ctx())
        assert plan is not None
        for expression in plan.expressions:
            known = expression.source in COMPILED_SOURCES or expression.source in CHECKS_SOURCE
            assert known, (
                f"{check_id} declares the pattern {expression.source!r}, which checks.py "
                f"neither compiles nor writes"
            )

    def test_the_supplier_name_phrase_is_the_one_supplied(self) -> None:
        """PCL001 is the one plan whose phrase is not a literal in the module.

        It compares a name given on the command line, so the binding above
        cannot cover it and this covers it instead.
        """
        plan = plan_for("PCL001", _ctx("Example Municipal Utility District"))
        assert plan is not None
        assert [p.text for p in plan.phrases] == ["Example Municipal Utility District"]

    @pytest.mark.parametrize("check_id", IMPLEMENTED)
    def test_a_conforming_check_has_a_probe_that_matched(
        self, check_id: str, conforming_label: Path
    ) -> None:
        supplier = "Example Municipal Utility District"
        explanation = explain(conforming_label, check_id, _ctx(supplier))
        if explanation.result.status is not Status.CONFORMS:
            pytest.skip(f"{check_id} does not conform on this fixture")
        hits: list[str] = [p.phrase.text for p in explanation.phrase_outcomes if p.matched] + [
            e.expression.source for e in explanation.expression_outcomes if e.matched
        ]
        assert hits, (
            f"{check_id} reports conforms on the conforming fixture and not one of the "
            f"probes its plan declares matched anything"
        )

    def test_the_conforming_fixture_makes_that_binding_reachable(
        self, conforming_label: Path
    ) -> None:
        """The fixture has to sit where the binding above can fail.

        If nothing conformed, every case would skip and the parametrised test
        would report green having compared nothing.
        """
        supplier = "Example Municipal Utility District"
        conforming = [
            check_id
            for check_id in IMPLEMENTED
            if explain(conforming_label, check_id, _ctx(supplier)).result.status is Status.CONFORMS
        ]
        assert len(conforming) >= 10


class TestItSettlesNothing:
    """The conclusion is the engine's, reached by the engine's own code."""

    @pytest.mark.parametrize("check_id", [c.spec.id for c in CHECKS])
    def test_the_status_equals_a_full_run_on_the_conforming_label(
        self, check_id: str, conforming_label: Path
    ) -> None:
        ctx = _ctx("Example Municipal Utility District")
        whole = check_document(conforming_label, ctx)
        wanted = next(r for r in whole.results if r.check_id == check_id)
        assert explain(conforming_label, check_id, ctx).result == wanted

    @pytest.mark.parametrize("check_id", [c.spec.id for c in CHECKS])
    def test_the_status_equals_a_full_run_on_the_deficient_label(
        self, check_id: str, deficient_label: Path
    ) -> None:
        whole = check_document(deficient_label, _ctx())
        wanted = next(r for r in whole.results if r.check_id == check_id)
        assert explain(deficient_label, check_id, _ctx()).result == wanted

    def test_the_two_fixtures_disagree_somewhere(
        self, conforming_label: Path, deficient_label: Path
    ) -> None:
        """Both tests above would pass over a pair of identical documents."""
        good = {r.check_id: r.status for r in check_document(conforming_label, _ctx()).results}
        bad = {r.check_id: r.status for r in check_document(deficient_label, _ctx()).results}
        assert good != bad


class TestAnUnreadableDocumentIsRefused:
    def test_it_gives_the_reason_check_gives(self, image_only_pdf: Path) -> None:
        explanation = explain(image_only_pdf, "PCL006")
        whole = check_document(image_only_pdf, _ctx())
        assert explanation.document.unreadable_reason == whole.unreadable_reason
        assert explanation.result.status is Status.NOT_EVALUATED

    def test_it_shows_no_surfaces_it_could_not_read(self, image_only_pdf: Path) -> None:
        explanation = explain(image_only_pdf, "PCL006")
        assert explanation.surfaces == ()
        assert explanation.phrase_outcomes == ()

    def test_it_exits_two(self, image_only_pdf: Path) -> None:
        assert explain(image_only_pdf, "PCL006").exit_code == 2


class TestNoProbeListIsSilentlyEmpty:
    def test_a_plan_with_no_probes_and_no_reason_is_refused(self) -> None:
        with pytest.raises(ValueError, match="say in words"):
            ScanPlan(reads=("normalized",))

    def test_a_plan_cannot_both_carry_probes_and_claim_it_compared_nothing(self) -> None:
        with pytest.raises(ValueError, match="cannot also say"):
            ScanPlan(
                reads=("normalized",),
                phrases=(Phrase("solar", Fold.SUBSTRING, "a category"),),
                scanned_nothing="nothing at all",
            )

    def test_a_plan_must_name_a_surface(self) -> None:
        with pytest.raises(ValueError, match="name the surface"):
            ScanPlan(reads=(), phrases=(Phrase("solar", Fold.SUBSTRING, "a category"),))

    def test_pcl001_without_a_name_says_it_compared_nothing(self, conforming_label: Path) -> None:
        explanation = explain(conforming_label, "PCL001")
        assert explanation.plan is not None
        assert explanation.plan.scanned_nothing is not None
        assert explanation.phrase_outcomes == ()
        assert "NOTHING COMPARED" in render_text(explanation)

    def test_pcl001_with_a_name_compares_it(self, conforming_label: Path) -> None:
        supplier = "Example Municipal Utility District"
        explanation = explain(conforming_label, "PCL001", _ctx(supplier))
        assert [p.matched for p in explanation.phrase_outcomes] == [True]

    def test_a_name_that_normalises_away_compares_nothing(self, conforming_label: Path) -> None:
        """A phrase of only spaces is not a phrase, and is not a match either."""
        explanation = explain(conforming_label, "PCL001", _ctx("   "))
        outcome = explanation.phrase_outcomes[0]
        assert outcome.matched is False
        assert outcome.note is not None
        assert "empty string" in outcome.note


class TestTheNearMissDescribes:
    def test_it_names_the_divergent_character(self, deficient_label: Path) -> None:
        explanation = explain(deficient_label, "PCL006")
        geothermal = next(p for p in explanation.phrase_outcomes if p.phrase.text == "geothermal")
        assert geothermal.matched is False
        assert geothermal.agreed_characters > 0
        assert geothermal.phrase_character is not None
        assert geothermal.document_character != geothermal.phrase_character

    def test_a_phrase_whose_first_character_is_absent_has_no_candidate_span(self) -> None:
        outcome = assess_phrase("solar and wind", Phrase("xylem", Fold.SUBSTRING, "a probe"))
        assert outcome.offset is None
        assert outcome.note is not None
        assert "first character" in outcome.note

    def test_a_match_reports_the_whole_phrase_as_agreed(self) -> None:
        outcome = assess_phrase("solar and wind", Phrase("and wind", Fold.SUBSTRING, "a probe"))
        assert outcome.matched is True
        assert outcome.agreed_characters == len("and wind")
        assert outcome.phrase_character is None

    def test_the_longest_agreement_wins_over_an_earlier_shorter_one(self) -> None:
        outcome = assess_phrase("solid solar", Phrase("solar", Fold.SUBSTRING, "a probe"))
        assert outcome.offset == len("solid ")

    def test_a_space_insensitive_match_is_shown_where_the_fold_found_it(self) -> None:
        """ADR 0006's case. The span quoted has to be the spaced extraction.

        Anchored on the plain walk instead, this reports whichever equal length
        prefix came first, which points the reader at an unrelated word while
        telling them the phrase matched.
        """
        text = "intensity in lbs of co 2e per megawatt hour"
        outcome = assess_phrase(text, Phrase("CO2e", Fold.SPACE_INSENSITIVE, "the unit"))
        assert outcome.matched is True
        assert outcome.offset == text.index("co 2e")
        assert outcome.span is not None and outcome.span.startswith("co 2e")
        assert outcome.document_character == " "
        assert outcome.phrase_character == "2"

    def test_a_space_insensitive_phrase_that_is_absent_falls_back_to_the_walk(self) -> None:
        outcome = assess_phrase(
            "solar and wind", Phrase("solid state", Fold.SPACE_INSENSITIVE, "a probe")
        )
        assert outcome.matched is False
        assert outcome.offset == 0
        assert outcome.agreed_characters == len("sol")

    def test_a_long_span_is_truncated_with_a_marker(self) -> None:
        text = "solar" + "x" * 500
        outcome = assess_phrase(text, Phrase("solar", Fold.SUBSTRING, "a probe"))
        assert outcome.span is not None
        assert outcome.span.endswith(TRUNCATION_MARKER)


class TestAPatternReportsWhatItFound:
    def test_it_quotes_the_matches(self) -> None:
        outcome = assess_expression("total 100% 97%", Expression(r"[0-9]{1,3}%", "a figure"))
        assert outcome.matched is True
        assert outcome.total_matches == 2
        assert outcome.matches == ("100%", "97%")

    def test_it_invents_no_near_miss(self) -> None:
        outcome = assess_expression("solar and wind", Expression(r"[0-9]{1,3}%", "a figure"))
        assert outcome.matched is False
        assert outcome.matches == ()

    def test_the_rendering_says_so_rather_than_leaving_a_blank(self, deficient_label: Path) -> None:
        """PCL017's pattern finds nothing on this label. The output has to say
        that no nearest span is reported, not print an empty section that a
        reader completes for themselves."""
        rendered = render_text(explain(deficient_label, "PCL017"))
        assert "NO MATCH" in rendered
        assert "no nearest span is reported" in rendered

    def test_it_counts_past_what_it_quotes(self) -> None:
        text = " ".join(f"{n}%" for n in range(MATCH_LIMIT + 3))
        outcome = assess_expression(text, Expression(r"[0-9]{1,3}%", "a figure"))
        assert len(outcome.matches) == MATCH_LIMIT
        assert outcome.total_matches == MATCH_LIMIT + 3


class TestTheSurfaces:
    def test_the_whole_text_layer_is_reported_with_its_length(self, conforming_label: Path) -> None:
        explanation = explain(conforming_label, "PCL007")
        surface = explanation.surfaces[0]
        assert surface.name == "normalized"
        assert surface.text is not None
        assert surface.length == len(surface.text)
        assert surface.excerpt() == surface.text

    def test_a_surface_longer_than_the_cap_is_cut_with_a_marker(self, tmp_path: Path) -> None:
        """The cut is announced and the full length is still reported.

        A truncation that is not announced is a smaller document standing in
        for a larger one, which is the failure this project is about.
        """
        path = tmp_path / "long_label.txt"
        path.write_text("2024 POWER CONTENT LABEL solar and wind " + "padding words. " * 400)
        explanation = explain(path, "PCL007")
        surface = explanation.surfaces[0]
        assert surface.length is not None and surface.length > SURFACE_CHARS
        excerpt = surface.excerpt()
        assert excerpt is not None and excerpt.endswith(TRUNCATION_MARKER)

    def test_a_missing_column_reading_says_so_rather_than_reading_empty(
        self, conforming_label: Path
    ) -> None:
        """PCL016 consults the column reading. A plain text file has none.

        Reported as an empty surface it would read as a column reading that
        found nothing, which is a different statement and a false one.
        """
        explanation = explain(conforming_label, "PCL016")
        cells = next(s for s in explanation.surfaces if s.name == "cells")
        assert cells.text is None
        assert cells.absent_reason is not None
        assert "no recoverable column geometry" in cells.absent_reason
        assert "not available" in render_text(explanation)

    def test_a_document_with_geometry_reports_its_cells(self, text_layer_pdf: Path) -> None:
        explanation = explain(text_layer_pdf, "PCL016")
        cells = next(s for s in explanation.surfaces if s.name == "cells")
        assert cells.text is not None
        assert cells.absent_reason is None

    def test_the_domain_surface_is_the_one_pcl005_reads(self, conforming_label: Path) -> None:
        explanation = explain(conforming_label, "PCL005")
        assert explanation.surfaces[0].name == "domains"
        assert "energy.ca.gov" in (explanation.surfaces[0].text or "")


class TestTheTextRendering:
    """The text rendering is the product; the JSON is the machine's copy of it.

    Every branch here puts a sentence in front of a reader, so each one is
    exercised against a real explanation rather than trusted to be reachable.
    """

    def test_an_unreadable_document_prints_the_refusal(self, image_only_pdf: Path) -> None:
        rendered = render_text(explain(image_only_pdf, "PCL006"))
        assert "refused" in rendered
        assert "unreadable" in rendered

    def test_a_phrase_with_a_note_prints_the_note_instead_of_a_span(
        self, conforming_label: Path
    ) -> None:
        rendered = render_text(explain(conforming_label, "PCL001", _ctx("   ")))
        assert "empty string" in rendered
        assert "nearest span at" not in rendered

    def test_the_rendering_quotes_what_a_pattern_found(self, conforming_label: Path) -> None:
        rendered = render_text(explain(conforming_label, "PCL018"))
        assert "match(es)" in rendered
        assert "    found " in rendered

    def test_the_rendering_counts_matches_past_what_it_quotes(self, tmp_path: Path) -> None:
        """A quoted list that stops without saying it stopped is a count the
        reader gets wrong."""
        path = tmp_path / "many_domains.txt"
        addresses = " ".join(f"www.example-{n}.example.com" for n in range(MATCH_LIMIT + 4))
        path.write_text(f"2024 POWER CONTENT LABEL solar and wind {addresses} " + "pad. " * 40)
        rendered = render_text(explain(path, "PCL003"))
        assert " more" in rendered


class TestAnUnimplementedCheck:
    def test_it_prints_the_registered_reason_and_the_blocker(self, conforming_label: Path) -> None:
        check_id = UNIMPLEMENTED[0]
        explanation = explain(conforming_label, check_id)
        assert explanation.plan is None
        text = render_text(explanation)
        spec = find_check(check_id).spec
        assert spec.unimplemented_reason is not None
        assert spec.unimplemented_reason in text
        assert spec.blocker is not None
        assert spec.blocker.value in text

    def test_it_is_not_evaluated_and_exits_two(self, conforming_label: Path) -> None:
        explanation = explain(conforming_label, UNIMPLEMENTED[0])
        assert explanation.result.status is Status.NOT_EVALUATED
        assert explanation.exit_code == 2


class TestUnknownIdentifiers:
    def test_the_library_refuses_and_names_the_identifier(self, conforming_label: Path) -> None:
        with pytest.raises(UnknownCheck, match="PCL999"):
            explain(conforming_label, "PCL999")

    def test_find_check_returns_the_registered_one(self) -> None:
        assert find_check("PCL006").spec.id == "PCL006"


class TestTheJsonAndTheTextAgree:
    def test_the_json_is_valid_and_versioned(self, deficient_label: Path) -> None:
        payload = json.loads(render_json(explain(deficient_label, "PCL017")))
        assert payload["schema_version"] >= 1
        assert payload["check"]["id"] == "PCL017"

    def test_the_json_carries_the_same_status_as_the_text(self, deficient_label: Path) -> None:
        explanation = explain(deficient_label, "PCL017")
        payload = json.loads(render_json(explanation))
        assert payload["result"]["status"] == explanation.result.status.value
        assert explanation.result.status.value in render_text(explanation)

    def test_the_json_carries_the_quote_the_check_cites(self, deficient_label: Path) -> None:
        payload = json.loads(render_json(explain(deficient_label, "PCL017")))
        assert payload["check"]["citation"]["quote"]

    def test_the_json_names_the_surfaces_and_the_probes(self, deficient_label: Path) -> None:
        payload = json.loads(render_json(explain(deficient_label, "PCL006")))
        assert [s["name"] for s in payload["surfaces"]] == ["lines", "normalized"]
        assert any(p["matched"] is False for p in payload["phrases"])

    def test_the_json_reports_the_fences_that_decided(self, deficient_label: Path) -> None:
        payload = json.loads(render_json(explain(deficient_label, "PCL016")))
        assert payload["scan"]["fences"]


class TestTheCommandLine:
    def test_a_deviation_exits_one(
        self, deficient_label: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["explain", str(deficient_label), "PCL017"]) == ExitCode.NONCONFORMANCE
        assert "PCL017" in capsys.readouterr().out

    def test_a_conforming_check_exits_zero(
        self, conforming_label: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["explain", str(conforming_label), "PCL007"]) == ExitCode.OK
        capsys.readouterr()

    def test_an_unregistered_identifier_is_the_documented_usage_error(
        self, conforming_label: Path
    ) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(["explain", str(conforming_label), "PCL999"])
        assert exit_info.value.code == ExitCode.USAGE_ERROR

    def test_the_json_flag_emits_json(
        self, deficient_label: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["explain", str(deficient_label), "PCL017", "--json"])
        assert json.loads(capsys.readouterr().out)["check"]["id"] == "PCL017"

    def test_a_negative_threshold_is_a_usage_error(self, conforming_label: Path) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main(["explain", str(conforming_label), "PCL007", "--min-text-chars", "-1"])
        assert exit_info.value.code == ExitCode.USAGE_ERROR

    def test_the_supplier_name_reaches_pcl001(
        self, conforming_label: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(
            [
                "explain",
                str(conforming_label),
                "PCL001",
                "--supplier-name",
                "Example Municipal Utility District",
            ]
        )
        assert code == ExitCode.OK
        assert "matched" in capsys.readouterr().out

    def test_the_installed_entry_point_carries_the_verb(self) -> None:
        """The shipped console script, not only the importable module."""
        result = subprocess.run(
            [sys.executable, "-m", "power_content_check", "explain", "--help"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )
        assert result.returncode == 0
        assert "CHECK_ID" in result.stdout

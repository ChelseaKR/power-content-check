"""Command line behaviour, including the exit codes callers depend on."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from power_content_check.cli import main
from power_content_check.model import ExitCode


class TestExitCodes:
    def test_nothing_checked_exits_three(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["check"]) == ExitCode.NOTHING_CHECKED
        assert "NOTHING CHECKED" in capsys.readouterr().out

    def test_empty_directory_exits_three(
        self, empty_directory: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["check", str(empty_directory)]) == ExitCode.NOTHING_CHECKED
        capsys.readouterr()

    def test_unreadable_exits_two(
        self, image_only_pdf: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["check", str(image_only_pdf)]) == ExitCode.NOT_EVALUATED
        out = capsys.readouterr().out
        assert "could not be read" in out
        assert "never reported as conforming" in out

    def test_a_deviation_exits_nonzero(
        self, deficient_label: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["check", str(deficient_label)])
        assert code in (ExitCode.NONCONFORMANCE, ExitCode.NOT_EVALUATED)
        assert code != ExitCode.OK
        capsys.readouterr()

    def test_negative_threshold_is_a_usage_error(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["check", "--min-text-chars", "-1", "x.pdf"])
        assert excinfo.value.code == 2


class TestPrecedence:
    """Higher codes win. These pin the combinations callers actually hit.

    With the catalog as registered, a readable document always carries the
    seventeen checks that enforce nothing, so NOT_EVALUATED shadows
    NONCONFORMANCE on every run over a readable document and code 1 is
    unreachable until a conditional check implements. That is the documented
    ordinary result, not a defect; these tests hold the shadowing on purpose,
    so that implementing a conditional check surfaces here first.
    """

    def test_nothing_checked_beats_everything(
        self, empty_directory: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["check", str(empty_directory)]) == ExitCode.NOTHING_CHECKED

    def test_not_evaluated_beats_nonconformance(
        self, deficient_label: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The same run found deviations AND could not evaluate checks, and
        reports the louder of the two."""
        assert main(["check", "--json", str(deficient_label)]) == ExitCode.NOT_EVALUATED
        payload = json.loads(capsys.readouterr().out)
        counts = payload["documents"][0]["counts"]
        assert counts["does_not_conform"] > 0, "this test needs a run with both"
        assert counts["not_evaluated"] > 0
        assert payload["exit_code"] == ExitCode.NOT_EVALUATED


class TestOutput:
    def test_json_is_valid_and_carries_the_notice(
        self, conforming_label: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["check", "--json", str(conforming_label)])
        payload = json.loads(capsys.readouterr().out)
        assert payload["tool"] == "power-content-check"
        assert payload["ruleset_effective"] == "2025-06-18"
        assert "no judgment" in payload["notice"]
        assert len(payload["documents"]) == 1

    def test_json_names_every_check(
        self, conforming_label: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from power_content_check.checks import CHECKS

        main(["check", "--json", str(conforming_label)])
        payload = json.loads(capsys.readouterr().out)
        ids = {r["check_id"] for r in payload["documents"][0]["results"]}
        assert ids == {c.spec.id for c in CHECKS}

    def test_verbose_lists_conforming_checks(
        self, conforming_label: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(
            [
                "check",
                "--verbose",
                "--supplier-name",
                "Example Municipal Utility District",
                str(conforming_label),
            ]
        )
        out = capsys.readouterr().out
        assert "PCL006" in out
        assert "PCL019" in out

    def test_quiet_output_hides_conforming_checks(
        self, conforming_label: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["check", str(conforming_label)])
        out = capsys.readouterr().out
        assert "PCL019" not in out
        assert "Pass --verbose" in out

    def test_fingerprint_is_printed_on_request(
        self, conforming_label: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["check", "--fingerprint", str(conforming_label)])
        out = capsys.readouterr().out
        assert "fingerprint: " in out

    def test_the_notice_appears_in_text_output(
        self, conforming_label: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main(["check", str(conforming_label)])
        out = " ".join(capsys.readouterr().out.split())
        assert "not affiliated with, endorsed by, or approved by" in out
        assert "does not rank suppliers" in out


class TestCatalog:
    def test_catalog_text_lists_every_check(self, capsys: pytest.CaptureFixture[str]) -> None:
        from power_content_check.checks import CHECKS

        assert main(["catalog"]) == ExitCode.OK
        out = capsys.readouterr().out
        for check in CHECKS:
            assert check.spec.id in out

    def test_catalog_marks_the_unimplemented_ones(self, capsys: pytest.CaptureFixture[str]) -> None:
        main(["catalog"])
        assert "REGISTERED, ENFORCES NOTHING" in capsys.readouterr().out

    def test_catalog_json_carries_citations(self, capsys: pytest.CaptureFixture[str]) -> None:
        main(["catalog", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert len(payload) == 35
        for entry in payload:
            assert entry["citation"]["source_url"].startswith("https://")
            assert entry["citation"]["quote"]
            assert entry["implemented"] or entry["blocker"]

    def test_version_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--version"])
        assert excinfo.value.code == 0
        assert "power-content-check" in capsys.readouterr().out


class TestNoCommand:
    def test_a_bare_invocation_is_a_usage_error(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main([])
        assert excinfo.value.code == 2

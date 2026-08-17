"""The safety property.

A document the tool could not read must never be reported as conforming.

This is not a hypothetical. The same defect, an unreadable document coming back
clean, was found in a sibling project, which is why it gets its own test module
rather than a line inside a larger one.
"""

from __future__ import annotations

from pathlib import Path

from power_content_check.checks import CHECKS
from power_content_check.engine import check_document, check_paths, fingerprint
from power_content_check.model import ExitCode, Readability, Status


def _statuses(path: Path) -> list[Status]:
    return [r.status for r in check_document(path).results]


class TestUnreadableIsNeverClean:
    def test_image_only_pdf_is_unreadable(self, image_only_pdf: Path) -> None:
        report = check_document(image_only_pdf)
        assert report.readability is Readability.UNREADABLE
        assert report.unreadable_reason is not None
        assert "text layer" in report.unreadable_reason

    def test_unreadable_produces_no_conforming_result(self, image_only_pdf: Path) -> None:
        statuses = _statuses(image_only_pdf)
        assert statuses, "an unreadable document must still produce results"
        assert Status.CONFORMS not in statuses
        assert Status.DOES_NOT_CONFORM not in statuses
        assert set(statuses) == {Status.NOT_EVALUATED}

    def test_unreadable_covers_every_registered_check(self, image_only_pdf: Path) -> None:
        report = check_document(image_only_pdf)
        assert len(report.results) == len(CHECKS)
        assert {r.check_id for r in report.results} == {c.spec.id for c in CHECKS}

    def test_every_unreadable_shape_behaves_the_same(
        self,
        image_only_pdf: Path,
        corrupt_pdf: Path,
        encrypted_pdf: Path,
        empty_file: Path,
        unsupported_file: Path,
        tmp_path: Path,
    ) -> None:
        missing = tmp_path / "not_here.pdf"
        for path in (
            image_only_pdf,
            corrupt_pdf,
            encrypted_pdf,
            empty_file,
            unsupported_file,
            missing,
        ):
            report = check_document(path)
            assert report.readability is Readability.UNREADABLE, path
            assert Status.CONFORMS not in [r.status for r in report.results], path

    def test_unreadable_run_does_not_exit_zero(self, image_only_pdf: Path) -> None:
        assert check_paths([image_only_pdf]).exit_code == ExitCode.NOT_EVALUATED

    def test_one_bad_document_taints_a_mixed_run(
        self, conforming_label: Path, image_only_pdf: Path
    ) -> None:
        report = check_paths([conforming_label, image_only_pdf])
        assert report.exit_code != ExitCode.OK
        assert report.summary["documents_unreadable"] == 1


class TestOutputsDiffer:
    """The required proof, stated as a hash comparison.

    ``fingerprint`` deliberately excludes the file path, the timestamp and the
    tool version, so this asserts that the tool reached different conclusions,
    not merely that it was handed different filenames.
    """

    def test_unreadable_and_clean_hash_differently(
        self, conforming_label: Path, image_only_pdf: Path
    ) -> None:
        clean = check_paths([conforming_label])
        unreadable = check_paths([image_only_pdf])
        assert fingerprint(clean) != fingerprint(unreadable)

    def test_the_hash_is_stable_for_the_same_conclusions(self, conforming_label: Path) -> None:
        first = check_paths([conforming_label])
        second = check_paths([conforming_label])
        assert fingerprint(first) == fingerprint(second)

    def test_every_unreadable_shape_differs_from_clean(
        self,
        conforming_label: Path,
        image_only_pdf: Path,
        corrupt_pdf: Path,
        empty_file: Path,
    ) -> None:
        clean = fingerprint(check_paths([conforming_label]))
        for path in (image_only_pdf, corrupt_pdf, empty_file):
            assert fingerprint(check_paths([path])) != clean, path

    def test_a_deviation_differs_from_a_clean_read(
        self, conforming_label: Path, deficient_label: Path
    ) -> None:
        assert fingerprint(check_paths([conforming_label])) != fingerprint(
            check_paths([deficient_label])
        )


class TestEmptyDenominator:
    """Checking zero labels is not success."""

    def test_no_paths_exits_three(self) -> None:
        report = check_paths([])
        assert report.documents == []
        assert report.exit_code == ExitCode.NOTHING_CHECKED

    def test_directory_with_no_labels_exits_three(self, empty_directory: Path) -> None:
        assert check_paths([empty_directory]).exit_code == ExitCode.NOTHING_CHECKED

    def test_empty_run_never_reports_a_conforming_check(self) -> None:
        summary = check_paths([]).summary
        assert summary["documents_checked"] == 0
        assert summary["conforms"] == 0

    def test_empty_run_says_so_in_words(self) -> None:
        from power_content_check.report import render_text

        text = " ".join(render_text(check_paths([])).split())
        assert "NOTHING CHECKED" in text
        assert "This is not a pass" in text


class TestCrashIsNotAPass:
    """A check that blows up must not be indistinguishable from one that passed."""

    def test_a_raising_check_becomes_not_evaluated(self, conforming_label: Path) -> None:
        from power_content_check.checks import CheckContext, RegisteredCheck
        from power_content_check.engine import run_checks
        from power_content_check.extract import LabelDocument, extract
        from power_content_check.model import CheckResult

        def boom(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
            raise RuntimeError("deliberate")

        registry = [RegisteredCheck(spec=CHECKS[0].spec, run=boom)]
        document = extract(conforming_label)
        assert isinstance(document, LabelDocument)

        results = run_checks(document, CheckContext(), registry)

        assert len(results) == 1
        assert results[0].status is Status.NOT_EVALUATED
        assert results[0].detail is not None
        assert "RuntimeError" in results[0].detail
        assert "deliberate" in results[0].detail

    def test_a_raising_check_keeps_the_run_from_exiting_zero(self, conforming_label: Path) -> None:
        from power_content_check.checks import CheckContext, RegisteredCheck
        from power_content_check.extract import LabelDocument
        from power_content_check.model import CheckResult

        def boom(doc: LabelDocument, ctx: CheckContext) -> CheckResult:
            raise RuntimeError("deliberate")

        registry = [RegisteredCheck(spec=CHECKS[0].spec, run=boom)]
        report = check_paths([conforming_label], registry=registry)
        assert report.exit_code == ExitCode.NOT_EVALUATED
        assert report.summary["conforms"] == 0

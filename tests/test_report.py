"""Rendering, and the claims the rendering is allowed to make."""

from __future__ import annotations

import json
from pathlib import Path

from power_content_check.checks import CheckContext
from power_content_check.engine import check_paths
from power_content_check.model import SCHEMA_VERSION, ExitCode
from power_content_check.report import render_catalog, render_json, render_text

SUPPLIER = "Example Municipal Utility District"


def _flat(text: str) -> str:
    return " ".join(text.split())


class TestNotice:
    """The disclaimer travels with the output, not only with the README."""

    def test_text_output_disclaims_judgment(self, conforming_label: Path) -> None:
        out = _flat(render_text(check_paths([conforming_label])))
        assert "no judgment about any supplier's power mix" in out
        assert "does not rank suppliers" in out
        assert "not affiliated with, endorsed by, or approved by" in out

    def test_text_output_explains_who_generates_the_label(self, conforming_label: Path) -> None:
        out = _flat(render_text(check_paths([conforming_label])))
        assert "the retail supplier may not alter the format" in out
        assert "not evidence of anything a named supplier did" in out

    def test_json_output_carries_the_same_notice(self, conforming_label: Path) -> None:
        payload = json.loads(render_json(check_paths([conforming_label])))
        assert "does not rank suppliers" in payload["notice"]


class TestJson:
    def test_shape(self, conforming_label: Path) -> None:
        payload = json.loads(
            render_json(check_paths([conforming_label], CheckContext(supplier_name=SUPPLIER)))
        )
        assert set(payload) == {
            "schema_version",
            "tool",
            "tool_version",
            "ruleset_id",
            "ruleset_effective",
            "generated_at",
            "notice",
            "skipped",
            "summary",
            "exit_code",
            "documents",
        }
        assert payload["schema_version"] == SCHEMA_VERSION
        document = payload["documents"][0]
        assert set(document) == {
            "path",
            "readability",
            "unreadable_reason",
            "sha256",
            "page_count",
            "image_count",
            "extraction_basis",
            "counts",
            "results",
        }
        assert document["readability"] == "readable"
        assert document["sha256"]
        assert set(document["counts"]) == {"conforms", "does_not_conform", "not_evaluated"}
        assert set(payload["summary"]) == {
            "documents_checked",
            "documents_readable",
            "documents_unreadable",
            "conforms",
            "does_not_conform",
            "not_evaluated",
        }
        assert "image_count" in document
        assert document["extraction_basis"]

    def test_a_result_carries_exactly_its_documented_keys(self, conforming_label: Path) -> None:
        payload = json.loads(render_json(check_paths([conforming_label])))
        result = payload["documents"][0]["results"][0]
        assert set(result) == {"check_id", "status", "finding", "detail"}

    def test_unreadable_document_json(self, image_only_pdf: Path) -> None:
        payload = json.loads(render_json(check_paths([image_only_pdf])))
        document = payload["documents"][0]
        assert document["readability"] == "unreadable"
        assert document["unreadable_reason"]
        assert document["counts"]["conforms"] == 0
        assert payload["exit_code"] == ExitCode.NOT_EVALUATED

    def test_empty_run_json(self) -> None:
        payload = json.loads(render_json(check_paths([])))
        assert payload["documents"] == []
        assert payload["summary"]["documents_checked"] == 0
        assert payload["exit_code"] == ExitCode.NOTHING_CHECKED


class TestText:
    def test_deviations_are_shown_by_default(self, deficient_label: Path) -> None:
        out = render_text(check_paths([deficient_label]))
        assert "FAIL" in out
        assert "PCL017" in out

    def test_every_shown_result_carries_its_citation(self, deficient_label: Path) -> None:
        out = render_text(check_paths([deficient_label]))
        assert "Cited:" in out
        assert "ccr-t20-art5" in out

    def test_exit_code_is_explained_in_words(self, deficient_label: Path) -> None:
        out = render_text(check_paths([deficient_label]))
        assert "Exit code:" in out

    def test_the_document_header_states_what_was_looked_at(self, illustrated_pdf: Path) -> None:
        out = _flat(render_text(check_paths([illustrated_pdf])))
        assert "Basis: the text layer of this PDF, which also embeds 5 images." in out


class TestFilesThatWereNotRead:
    """A folder holds more than the file this tool reads, and says so.

    The Energy Commission publishes a spreadsheet beside every label, an
    alternative rendering of the same disclosure. This tool reads the PDF and
    the plain text and does not read that spreadsheet, for the reasons in ADR
    0009. What it must not do is leave a reader thinking the folder held one
    file.
    """

    def _folder(self, tmp_path: Path, conforming_label: Path) -> Path:
        folder = tmp_path / "one_label"
        folder.mkdir()
        (folder / "label.txt").write_text(conforming_label.read_text(encoding="utf-8"))
        (folder / "label.xlsx").write_bytes(b"PK\x03\x04 an alternative rendering")
        return folder

    def test_the_skipped_file_is_named(self, tmp_path: Path, conforming_label: Path) -> None:
        out = render_text(check_paths([self._folder(tmp_path, conforming_label)]))
        assert "label.xlsx" in out
        assert "is not a format this tool reads" in out

    def test_the_skipped_file_is_not_a_document(
        self, tmp_path: Path, conforming_label: Path
    ) -> None:
        """It is named, and it is in no count. Naming it is not checking it."""
        report = check_paths([self._folder(tmp_path, conforming_label)])
        assert report.summary["documents_checked"] == 1
        assert len(report.skipped) == 1

    def test_json_carries_the_same_list(self, tmp_path: Path, conforming_label: Path) -> None:
        payload = json.loads(render_json(check_paths([self._folder(tmp_path, conforming_label)])))
        assert [Path(p).name for p in payload["skipped"]] == ["label.xlsx"]

    def test_a_folder_of_nothing_readable_still_says_nothing_checked(self, tmp_path: Path) -> None:
        """Naming what was skipped must not soften an empty denominator."""
        folder = tmp_path / "only_workbooks"
        folder.mkdir()
        (folder / "one.xlsx").write_bytes(b"PK\x03\x04 first")
        (folder / "two.xlsx").write_bytes(b"PK\x03\x04 second")
        report = check_paths([folder])
        out = render_text(report)
        assert report.exit_code == ExitCode.NOTHING_CHECKED
        assert "NOTHING CHECKED." in out
        assert "2 files in the directories given are not a format" in _flat(out)

    def test_a_file_named_on_the_command_line_is_not_skipped_quietly(
        self, unsupported_file: Path
    ) -> None:
        """Naming a file is asking about it, so it stays a document and fails closed."""
        report = check_paths([unsupported_file])
        assert report.skipped == []
        assert report.summary["documents_unreadable"] == 1

    def test_a_long_list_is_summarised_and_never_truncated_in_the_json(
        self, tmp_path: Path, conforming_label: Path
    ) -> None:
        """A folder of a hundred other files must not bury the findings."""
        folder = tmp_path / "busy"
        folder.mkdir()
        (folder / "label.txt").write_text(conforming_label.read_text(encoding="utf-8"))
        for index in range(30):
            (folder / f"other-{index:02d}.xlsx").write_bytes(b"PK\x03\x04")
        report = check_paths([folder])
        out = render_text(report)
        assert "and 20 more, all of them in the JSON output." in out
        assert len(json.loads(render_json(report))["skipped"]) == 30

    def test_nothing_is_said_when_nothing_was_skipped(self, conforming_label: Path) -> None:
        out = render_text(check_paths([conforming_label]))
        assert "is not a format this tool reads" not in out


class TestCatalogRendering:
    def test_text_catalog_quotes_every_source(self) -> None:
        from power_content_check.checks import CHECKS

        out = render_catalog()
        for check in CHECKS:
            assert check.spec.id in out
        assert out.count("Quote:") == len(CHECKS)
        assert out.count("URL:") == len(CHECKS)

    def test_unimplemented_entries_give_a_reason(self) -> None:
        assert "Why not implemented [" in render_catalog()

    def test_unimplemented_entries_say_whether_the_block_is_permanent(self) -> None:
        out = render_catalog()
        assert "Why not implemented [permanent]:" in out
        assert "Why not implemented [conditional]:" in out
        assert "REGISTERED, ENFORCES NOTHING, permanent" in out

    def test_json_catalog_is_machine_readable(self) -> None:
        from power_content_check.checks import CHECKS

        payload = json.loads(render_catalog(as_json=True))
        assert len(payload) == len(CHECKS)
        assert {e["id"] for e in payload} == {c.spec.id for c in CHECKS}

    def test_a_catalog_entry_carries_exactly_its_documented_keys(self) -> None:
        """The catalog is consumed by scripts too. Its shape is pinned like the
        run report's, so a change to CheckSpec's rendering fails a test rather
        than a stranger's parser."""
        payload = json.loads(render_catalog(as_json=True))
        assert set(payload[0]) == {
            "id",
            "title",
            "basis",
            "implemented",
            "what_it_looks_for",
            "unimplemented_reason",
            "blocker",
            "citation",
        }
        assert set(payload[0]["citation"]) == {
            "source_key",
            "source_title",
            "source_url",
            "source_effective",
            "source_retrieved",
            "locator",
            "quote",
        }

"""Rendering, and the claims the rendering is allowed to make."""

from __future__ import annotations

import json
from pathlib import Path

from power_content_check.checks import CheckContext
from power_content_check.engine import check_paths
from power_content_check.model import ExitCode
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
        assert set(payload) >= {
            "tool",
            "tool_version",
            "ruleset_id",
            "ruleset_effective",
            "generated_at",
            "notice",
            "summary",
            "exit_code",
            "documents",
        }
        document = payload["documents"][0]
        assert document["readability"] == "readable"
        assert document["sha256"]
        assert set(document["counts"]) == {"conforms", "does_not_conform", "not_evaluated"}

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


class TestCatalogRendering:
    def test_text_catalog_quotes_every_source(self) -> None:
        from power_content_check.checks import CHECKS

        out = render_catalog()
        for check in CHECKS:
            assert check.spec.id in out
        assert out.count("Quote:") == len(CHECKS)
        assert out.count("URL:") == len(CHECKS)

    def test_unimplemented_entries_give_a_reason(self) -> None:
        assert "Why not implemented:" in render_catalog()

    def test_json_catalog_is_machine_readable(self) -> None:
        from power_content_check.checks import CHECKS

        payload = json.loads(render_catalog(as_json=True))
        assert len(payload) == len(CHECKS)
        assert {e["id"] for e in payload} == {c.spec.id for c in CHECKS}

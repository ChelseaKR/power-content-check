"""The published JSON Schemas, and the things that would make them a lie.

Three separate obligations live here, and they fail for different reasons:

1. **The committed files match the builders.** ``schemas/`` is generated, so a
   hand edit, or a model change nobody regenerated for, is a failing test rather
   than a stale published contract.
2. **Every report the suite can produce validates.** Including the ones that are
   easy to forget: an unreadable document, a run that checked nothing, a run
   with skipped files, and a run carrying advisories.
3. **The schema is not weaker than the tests it replaces.** A schema that
   accepted anything would pass (1) and (2) and be worthless, so each structural
   promise is checked by mutating a valid report until it breaks: a deleted key,
   an unknown key, a dropped not-evaluated result, a status outside the
   enumeration, an exit code the tool cannot emit.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from power_content_check.checks import CheckContext
from power_content_check.engine import check_paths
from power_content_check.model import (
    CATALOG_SCHEMA_ID,
    REPORT_SCHEMA_ID,
    CheckResult,
    DocumentReport,
    ExitCode,
    RunReport,
    Status,
)
from power_content_check.report import render_catalog, render_json
from power_content_check.schemas import (
    catalog_schema,
    registered_check_ids,
    render,
    report_schema,
)

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"
SUPPLIER = "Example Utility"


def _report_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMAS / "report-v1.schema.json").read_text()))


def _catalog_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMAS / "catalog-v1.schema.json").read_text()))


def _payload(paths: list[Path], **kwargs: Any) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(render_json(check_paths(paths, CheckContext(**kwargs))))
    return payload


# ---------------------------------------------------------------------------
# 1. the committed files are the generated ones
# ---------------------------------------------------------------------------


class TestCommittedFilesAreGenerated:
    def test_the_report_schema_on_disk_is_what_the_builder_produces(self) -> None:
        expected = render(report_schema(registered_check_ids()))
        assert (SCHEMAS / "report-v1.schema.json").read_text(encoding="utf-8") == expected, (
            "schemas/report-v1.schema.json is stale; run 'make schemas'"
        )

    def test_the_catalog_schema_on_disk_is_what_the_builder_produces(self) -> None:
        expected = render(catalog_schema())
        assert (SCHEMAS / "catalog-v1.schema.json").read_text(encoding="utf-8") == expected, (
            "schemas/catalog-v1.schema.json is stale; run 'make schemas'"
        )

    def test_the_generator_reports_a_clean_tree_under_check(self) -> None:
        """The gate the Makefile could run, exercised rather than assumed."""
        done = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "gen_schemas.py"), "--check"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert "up to date" in done.stdout

    def test_both_schemas_are_valid_schemas(self) -> None:
        Draft202012Validator.check_schema(
            json.loads((SCHEMAS / "report-v1.schema.json").read_text())
        )
        Draft202012Validator.check_schema(
            json.loads((SCHEMAS / "catalog-v1.schema.json").read_text())
        )

    def test_a_report_names_the_schema_it_claims_to_meet(self, conforming_label: Path) -> None:
        payload = _payload([conforming_label])
        assert payload["schema"] == REPORT_SCHEMA_ID
        assert REPORT_SCHEMA_ID.endswith("/schemas/report-v1.schema.json")
        assert CATALOG_SCHEMA_ID.endswith("/schemas/catalog-v1.schema.json")


# ---------------------------------------------------------------------------
# 2. the shape the schema describes is the shape the code emits
# ---------------------------------------------------------------------------


class TestParityWithTheModel:
    """The schema's keys against the dataclasses, not against a fixture.

    A fixture-only check would keep passing after a field was added to
    ``CheckResult`` and left out of the schema, because the fixture would not
    carry it either.
    """

    def test_check_result_fields_are_exactly_the_schema_properties(self) -> None:
        schema = report_schema(registered_check_ids())
        properties = set(schema["$defs"]["check_result"]["properties"])
        assert properties == {f.name for f in dataclasses.fields(CheckResult)}
        assert set(schema["$defs"]["check_result"]["required"]) == properties

    def test_document_fields_plus_the_derived_count_are_the_schema_properties(self) -> None:
        schema = report_schema(registered_check_ids())
        properties = set(schema["$defs"]["document"]["properties"])
        fields = {f.name for f in dataclasses.fields(DocumentReport)}
        assert properties == fields | {"counts"}
        assert set(schema["$defs"]["document"]["required"]) == properties

    def test_run_fields_plus_the_derived_ones_are_the_schema_properties(self) -> None:
        schema = report_schema(registered_check_ids())
        properties = set(schema["properties"])
        fields = {f.name for f in dataclasses.fields(RunReport)}
        assert properties == fields | {"schema", "schema_version", "summary", "exit_code"}
        assert set(schema["required"]) == properties

    def test_the_status_enumeration_comes_from_the_model(self) -> None:
        schema = report_schema(registered_check_ids())
        assert schema["$defs"]["check_result"]["properties"]["status"]["enum"] == [
            s.value for s in Status
        ]

    def test_the_exit_code_enumeration_is_every_code_the_tool_defines(self) -> None:
        schema = report_schema(registered_check_ids())
        defined = {value for name, value in vars(ExitCode).items() if not name.startswith("_")}
        assert set(schema["properties"]["exit_code"]["enum"]) == defined
        assert ExitCode.NOTHING_CHECKED in schema["properties"]["exit_code"]["enum"]


class TestRealReportsValidate:
    def test_a_conforming_run(self, conforming_label: Path) -> None:
        _report_validator().validate(_payload([conforming_label], supplier_name=SUPPLIER))

    def test_a_deficient_run(self, deficient_label: Path) -> None:
        _report_validator().validate(_payload([deficient_label], supplier_name=SUPPLIER))

    def test_an_unreadable_document(self, image_only_pdf: Path) -> None:
        payload = _payload([image_only_pdf])
        _report_validator().validate(payload)
        assert payload["documents"][0]["readability"] == "unreadable"
        assert payload["documents"][0]["extraction_basis"] is None

    def test_a_run_that_checked_nothing(self) -> None:
        payload = _payload([])
        _report_validator().validate(payload)
        assert payload["exit_code"] == ExitCode.NOTHING_CHECKED

    def test_a_run_with_a_skipped_file(self, tmp_path: Path, conforming_label: Path) -> None:
        folder = tmp_path / "batch"
        folder.mkdir()
        (folder / "label.txt").write_text(conforming_label.read_text(encoding="utf-8"))
        (folder / "notes.docx").write_bytes(b"not a label")
        payload = _payload([folder])
        _report_validator().validate(payload)
        assert payload["skipped"], "the fixture did not produce a skipped file"

    def test_a_run_carrying_advisories(self, tmp_path: Path, conforming_label: Path) -> None:
        """Advisories are a separate array with a fixed notice; validate one.

        The assertion that the fixture actually produced an advisory is the
        point of it. A first draft of this test mutated the label in a way that
        raised none, so it validated an empty array and would have passed
        against a schema with no advisory definition at all.
        """
        label = tmp_path / "two-years.txt"
        label.write_text(
            conforming_label.read_text(encoding="utf-8") + "\nData year 2023\n",
            encoding="utf-8",
        )
        payload = _payload([label])
        advisories = payload["documents"][0]["advisories"]
        assert advisories, "the fixture raised no advisory, so this validates nothing"
        assert advisories[0]["code"] == "ADV-DATA-YEAR-MISMATCH"
        assert payload["summary"]["advisories"] == len(advisories)
        _report_validator().validate(payload)

    def test_the_catalog_validates_and_lists_every_registered_check(self) -> None:
        payload = json.loads(render_catalog(as_json=True))
        _catalog_validator().validate(payload)
        assert [entry["id"] for entry in payload] == list(registered_check_ids())
        assert len(payload) == 35


# ---------------------------------------------------------------------------
# 3. the schema can actually fail
# ---------------------------------------------------------------------------


class TestTheSchemaRefusesWhatItShould:
    """Each of these mutates a valid report and requires a rejection.

    Without them the suite would prove only that a permissive schema accepts
    real reports, which is what a schema that said ``{"type": "object"}`` would
    also do.
    """

    @pytest.fixture
    def valid(self, conforming_label: Path) -> dict[str, Any]:
        payload = _payload([conforming_label], supplier_name=SUPPLIER)
        _report_validator().validate(payload)
        return payload

    def test_a_deleted_key_is_rejected_and_the_error_names_the_path(
        self, valid: dict[str, Any]
    ) -> None:
        del valid["documents"][0]["extraction_basis"]
        with pytest.raises(ValidationError) as caught:
            _report_validator().validate(valid)
        assert list(caught.value.absolute_path) == ["documents", 0]
        assert "extraction_basis" in caught.value.message

    def test_an_unknown_key_is_rejected(self, valid: dict[str, Any]) -> None:
        valid["confidence"] = 0.97
        with pytest.raises(ValidationError, match="confidence"):
            _report_validator().validate(valid)

    def test_dropping_a_not_evaluated_result_invalidates_the_report(
        self, valid: dict[str, Any]
    ) -> None:
        """The fail-closed contract, held by the format and not only by a test.

        A report that lists only the checks it managed to run reads as a
        shorter clean run. Removing one unevaluated result must be a validation
        failure, not a smaller document.
        """
        results = valid["documents"][0]["results"]
        dropped = next(r for r in results if r["status"] == Status.NOT_EVALUATED.value)
        results.remove(dropped)
        with pytest.raises(ValidationError):
            _report_validator().validate(valid)

    def test_dropping_a_conforming_result_also_invalidates_the_report(
        self, valid: dict[str, Any]
    ) -> None:
        results = valid["documents"][0]["results"]
        dropped = next(r for r in results if r["status"] == Status.CONFORMS.value)
        results.remove(dropped)
        with pytest.raises(ValidationError):
            _report_validator().validate(valid)

    def test_a_status_outside_the_enumeration_is_rejected(self, valid: dict[str, Any]) -> None:
        valid["documents"][0]["results"][0]["status"] = "probably_fine"
        with pytest.raises(ValidationError, match="probably_fine"):
            _report_validator().validate(valid)

    def test_an_exit_code_the_tool_cannot_emit_is_rejected(self, valid: dict[str, Any]) -> None:
        valid["exit_code"] = 7
        with pytest.raises(ValidationError):
            _report_validator().validate(valid)

    def test_a_report_claiming_a_different_schema_is_rejected(self, valid: dict[str, Any]) -> None:
        valid["schema"] = "https://example.invalid/report-v2.schema.json"
        with pytest.raises(ValidationError):
            _report_validator().validate(valid)

    def test_an_advisory_may_not_drop_its_notice(self, valid: dict[str, Any]) -> None:
        valid["documents"][0]["advisories"] = [
            {"code": "ADV-TEXTLESS-PAGE", "observation": "x", "where": "page 1"}
        ]
        with pytest.raises(ValidationError, match="notice"):
            _report_validator().validate(valid)

    def test_a_catalog_entry_that_enforces_nothing_must_say_why(self) -> None:
        payload = json.loads(render_catalog(as_json=True))
        entry = next(e for e in payload if not e["implemented"])
        entry["unimplemented_reason"] = None
        with pytest.raises(ValidationError):
            _catalog_validator().validate(payload)

    def test_a_catalog_entry_that_enforces_nothing_must_classify_the_blocker(self) -> None:
        payload = json.loads(render_catalog(as_json=True))
        entry = next(e for e in payload if not e["implemented"])
        entry["blocker"] = None
        with pytest.raises(ValidationError):
            _catalog_validator().validate(payload)

    def test_an_implemented_entry_may_not_carry_an_unimplemented_reason(self) -> None:
        payload = json.loads(render_catalog(as_json=True))
        entry = next(e for e in payload if e["implemented"])
        entry["unimplemented_reason"] = "because"
        with pytest.raises(ValidationError):
            _catalog_validator().validate(payload)

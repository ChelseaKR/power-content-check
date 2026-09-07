"""The SARIF log, and the fail-closed contract surviving the translation.

SARIF's natural shape is a list of problems found. This tool's central claim is
about the checks it could *not* decide, and a serialiser that emitted only
deviations would quietly discard it: a log with an empty ``results`` array would
say the same thing for a clean label, an unreadable one, and a run that checked
nothing at all. Every assertion here exists to stop one of those three collapsing
into the others.

On validating against the published schema
------------------------------------------

Issue #42 asks that the log validate against SARIF 2.1.0 in the gate. It does
validate. Measured 2026-09-07 against the OASIS errata01 schema
(``https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json``,
112,768 bytes, a draft-04 schema), with **zero errors** for the deficient
fixture. What is *not* here is a vendored copy of that 112 KB document, because
redistributing an OASIS specification artifact carries its notice requirements
and that is the owner's call rather than an agent's. The gate below is therefore
structural: :data:`_REQUIRED` pins the shape of every object this serialiser
emits, so a key dropped or retyped fails here.

That is a real gap and it is stated rather than papered over. It is also worth
knowing that it is a *smaller* gap than it looks, because of what the schema
cannot do:

**The defect issue #42 cites as the reason to validate is one schema validation
would not have caught.** ``qfer-preflight`` #14 was a wrong ``ruleIndex``: an
index that resolves to a different rule than ``ruleId`` names. That is a
well-formed SARIF log by every structural rule in the specification, and a
consumer shows the reader the wrong requirement.
:func:`test_every_rule_index_resolves_to_the_rule_its_id_names` is the check that
catches it, and no schema is a substitute for it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from power_content_check.checks import BY_ID, CHECKS, CheckContext
from power_content_check.cli import main
from power_content_check.engine import check_paths
from power_content_check.model import ExitCode, Readability, Status
from power_content_check.sarif import (
    SARIF_SCHEMA,
    SARIF_VERSION,
    render_sarif,
    report_to_sarif_dict,
)

SUPPLIER = "Example Municipal Utility District"


def _log(*paths: Path, supplier: str | None = None) -> dict[str, Any]:
    report = check_paths(list(paths), CheckContext(supplier_name=supplier))
    return report_to_sarif_dict(report)


def _run(log: dict[str, Any]) -> dict[str, Any]:
    runs = log["runs"]
    assert len(runs) == 1
    run: dict[str, Any] = runs[0]
    return run


def _invocation(log: dict[str, Any]) -> dict[str, Any]:
    invocations = _run(log)["invocations"]
    assert len(invocations) == 1
    invocation: dict[str, Any] = invocations[0]
    return invocation


# ---------------------------------------------------------------------------
# Shape. What a vendored schema would decide, decided here instead.
# ---------------------------------------------------------------------------

#: Object path to the keys SARIF 2.1.0 requires of it, for every object this
#: serialiser emits. Not the whole specification: the part of it this log uses.
_REQUIRED: dict[str, set[str]] = {
    "log": {"version", "runs"},
    "run": {"tool", "invocations", "results"},
    "driver": {"name", "rules"},
    "rule": {"id"},
    "result": {"message"},
    "location": {"physicalLocation"},
    "notification": {"message"},
    "invocation": {"executionSuccessful"},
}


def _assert_required(kind: str, node: dict[str, Any]) -> None:
    missing = _REQUIRED[kind] - set(node)
    assert not missing, f"{kind} is missing {sorted(missing)}"


def test_the_log_declares_the_version_and_a_resolvable_schema(deficient_label: Path) -> None:
    """A ``$schema`` nobody can fetch is a broken contract nothing notices.

    The address that circulates in tooling,
    ``raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/...``,
    was measured returning 404 on 2026-09-07: the specification repository moved
    its schema and dropped the ``master`` branch. This pins the OASIS address
    instead, and pins it against the dead one by name so a copy-paste back to it
    fails here.
    """
    log = _log(deficient_label)
    _assert_required("log", log)
    assert log["version"] == SARIF_VERSION == "2.1.0"
    assert log["$schema"] == SARIF_SCHEMA
    assert "docs.oasis-open.org" in SARIF_SCHEMA
    assert "oasis-tcs/sarif-spec/master" not in SARIF_SCHEMA


def test_every_object_the_log_emits_carries_what_sarif_requires(deficient_label: Path) -> None:
    log = _log(deficient_label)
    run = _run(log)
    _assert_required("run", run)
    driver = run["tool"]["driver"]
    _assert_required("driver", driver)
    for rule in driver["rules"]:
        _assert_required("rule", rule)
    for result in run["results"]:
        _assert_required("result", result)
        for location in result["locations"]:
            _assert_required("location", location)
    invocation = _invocation(log)
    _assert_required("invocation", invocation)
    for notification in (
        invocation["toolConfigurationNotifications"] + invocation["toolExecutionNotifications"]
    ):
        _assert_required("notification", notification)


def test_the_driver_names_the_ruleset_and_when_it_took_effect(deficient_label: Path) -> None:
    """A conformance verdict with no ruleset identifier cannot be reproduced."""
    driver = _run(_log(deficient_label))["tool"]["driver"]
    assert driver["properties"]["rulesetId"]
    assert driver["properties"]["rulesetEffective"]
    assert "does not rank suppliers" in driver["properties"]["notice"]


# ---------------------------------------------------------------------------
# The catalog, whole, and reachable from every result.
# ---------------------------------------------------------------------------


def test_the_driver_carries_the_whole_catalog_with_its_citations(deficient_label: Path) -> None:
    """Including the checks that enforce nothing.

    A rule missing from the driver is a check the reader cannot look up, and the
    registered-only entries are precisely the ones whose reason they need.
    """
    driver = _run(_log(deficient_label))["tool"]["driver"]
    assert [rule["id"] for rule in driver["rules"]] == [check.spec.id for check in CHECKS]
    for rule in driver["rules"]:
        spec = BY_ID[rule["id"]].spec
        assert rule["properties"]["implemented"] is spec.implemented
        assert spec.citation.locator in rule["help"]["text"]
        assert spec.citation.source.url in rule["help"]["text"]
        assert rule["properties"]["citation"]["quote"] == spec.citation.quote


def test_every_rule_index_resolves_to_the_rule_its_id_names(deficient_label: Path) -> None:
    """The defect issue #42 cites, and the one a schema cannot catch.

    A ``ruleIndex`` pointing at a different rule than ``ruleId`` names is
    structurally valid SARIF. Every consumer then shows the reader the wrong
    requirement, with the right rule identifier printed beside it.
    """
    run = _run(_log(deficient_label))
    rules = run["tool"]["driver"]["rules"]
    invocation = run["invocations"][0]

    referenced = [(item["ruleId"], item["ruleIndex"]) for item in run["results"]]
    referenced += [
        (item["associatedRule"]["id"], item["associatedRule"]["index"])
        for item in invocation["toolConfigurationNotifications"]
    ]
    referenced += [
        (item["descriptor"]["id"], item["descriptor"]["index"])
        for item in invocation["toolConfigurationNotifications"]
    ]
    assert referenced, "nothing in this log references a rule"
    for rule_id, position in referenced:
        assert rules[position]["id"] == rule_id


def test_every_registered_check_appears_exactly_once(deficient_label: Path) -> None:
    """The whole catalog, per readable document, results and notifications together.

    This is what stops the unevaluated half reading as a pass: a consumer
    counting entries gets the denominator, not only the deviations.
    """
    run = _run(_log(deficient_label))
    seen = [item["ruleId"] for item in run["results"]]
    seen += [
        item["associatedRule"]["id"]
        for item in run["invocations"][0]["toolConfigurationNotifications"]
    ]
    conforming = {
        result.check_id
        for document in check_paths([deficient_label]).documents
        for result in document.results
        if result.status is Status.CONFORMS
    }
    assert sorted(seen) + sorted(conforming) != [], "the log referenced no check at all"
    assert len(seen) == len(set(seen)), "a check appears twice in one document's log"
    assert set(seen) | conforming == {check.spec.id for check in CHECKS}


# ---------------------------------------------------------------------------
# The three ways an empty results array could mislead.
# ---------------------------------------------------------------------------


def test_a_conforming_check_emits_no_result_and_is_still_counted(
    conforming_label: Path,
) -> None:
    """Otherwise the log cannot show its own denominator."""
    log = _log(conforming_label, supplier=SUPPLIER)
    run = _run(log)
    invocation = run["invocations"][0]
    summary = invocation["properties"]["summary"]

    assert run["results"] == []
    assert summary["conforms"] > 0
    assert summary["does_not_conform"] == 0
    assert invocation["executionSuccessful"] is True


def test_an_unreadable_document_has_no_results_and_one_execution_error(
    image_only_pdf: Path,
) -> None:
    """A scanned label is not a clean label.

    No check ran, so nothing is reported per check; what the log carries is a
    single execution notification at ``error`` naming the file and the reason.
    """
    log = _log(image_only_pdf)
    run = _run(log)
    invocation = run["invocations"][0]

    assert run["results"] == []
    assert invocation["toolConfigurationNotifications"] == []
    assert len(invocation["toolExecutionNotifications"]) == 1
    notification = invocation["toolExecutionNotifications"][0]
    assert notification["level"] == "error"
    assert notification["descriptor"]["id"] == "unreadable-document"
    assert str(image_only_pdf) in notification["message"]["text"]
    assert "not reported as conforming" in notification["message"]["text"]
    assert invocation["exitCode"] == ExitCode.NOT_EVALUATED


def test_a_run_that_checked_nothing_says_the_tool_did_not_succeed() -> None:
    """Exit code 3 exists because an empty denominator is never a pass.

    ``executionSuccessful: true`` with an empty results array is, to every
    consumer, a clean run. This is the one place the flag is false, and finding
    a deviation is deliberately not one of them.
    """
    log = _log()
    invocation = _invocation(log)

    assert _run(log)["results"] == []
    assert invocation["executionSuccessful"] is False
    assert invocation["exitCode"] == ExitCode.NOTHING_CHECKED
    ids = [item["descriptor"]["id"] for item in invocation["toolExecutionNotifications"]]
    assert ids == ["nothing-checked"]
    assert "never a pass" in invocation["toolExecutionNotifications"][0]["message"]["text"]


def test_a_deviation_is_still_a_successful_run(deficient_label: Path) -> None:
    """SARIF's flag is about the tool, not about the document."""
    invocation = _invocation(_log(deficient_label))
    assert invocation["executionSuccessful"] is True
    assert invocation["exitCode"] != ExitCode.OK


# ---------------------------------------------------------------------------
# The two kinds of not-evaluated, kept apart.
# ---------------------------------------------------------------------------


def test_an_unimplemented_check_is_a_note_carrying_its_registered_reason(
    deficient_label: Path,
) -> None:
    """A permanent catalog gap is in every run. Raised as an error it gets muted."""
    notifications = _invocation(_log(deficient_label))["toolConfigurationNotifications"]
    unimplemented = [item for item in notifications if item["properties"]["implemented"] is False]
    assert unimplemented, "no registered-only check reached the log"
    for item in unimplemented:
        spec = BY_ID[item["associatedRule"]["id"]].spec
        assert item["level"] == "note"
        assert item["properties"]["blocker"] == (spec.blocker.value if spec.blocker else None)
        assert spec.unimplemented_reason is not None
        assert spec.unimplemented_reason in item["message"]["text"]


def test_an_implemented_check_that_could_not_decide_is_an_error(
    deficient_label: Path,
) -> None:
    """The tool tried to look and could not. That must never read as a pass.

    ``PCL001`` is the reachable case: without ``--supplier-name`` it reports as
    not evaluated rather than guessing, and it is an implemented check.
    """
    notifications = _invocation(_log(deficient_label))["toolConfigurationNotifications"]
    undecided = [item for item in notifications if item["properties"]["implemented"] is True]
    assert undecided, (
        "no implemented check reported as not evaluated, so the level that "
        "distinguishes 'could not look' from 'never built' was not exercised"
    )
    for item in undecided:
        assert item["level"] == "error"
        assert item["properties"]["status"] == Status.NOT_EVALUATED.value


def test_the_two_kinds_are_distinguishable_without_reading_the_level(
    deficient_label: Path,
) -> None:
    notifications = _invocation(_log(deficient_label))["toolConfigurationNotifications"]
    for item in notifications:
        assert isinstance(item["properties"]["implemented"], bool)


# ---------------------------------------------------------------------------
# What a result is allowed to say, and what must never become one.
# ---------------------------------------------------------------------------


def test_every_result_carries_the_basis_the_tool_looked_on(deficient_label: Path) -> None:
    """A deviation is a claim about text the tool could read (ADR 0003).

    Whether an absence is a property of the document or a limit of extraction
    depends on what else the page carries, so the answer travels with the
    finding.
    """
    report = check_paths([deficient_label])
    basis = report.documents[0].extraction_basis
    assert basis
    results = report_to_sarif_dict(report)["runs"][0]["results"]
    assert results
    for result in results:
        assert result["level"] == "error"
        assert result["kind"] == "fail"
        assert basis in result["message"]["text"]


def test_an_advisory_never_becomes_a_result(tmp_path: Path, conforming_label: Path) -> None:
    """ADR 0013: the advisory channel is fenced off from the rules.

    An advisory carries no status, is in no count and reaches no exit code.
    Emitting one as a SARIF result would score it, which is exactly the fence
    coming down. The label here is otherwise conforming and has one phrase the
    extractor broke apart, which is what raises the advisory.
    """
    noisy = tmp_path / "noisy.txt"
    noisy.write_text(
        conforming_label.read_text(encoding="utf-8").replace("CO2e", "CO 2e"),
        encoding="utf-8",
    )
    report = check_paths([noisy], CheckContext(supplier_name=SUPPLIER))
    assert report.documents[0].advisories, "this fixture no longer raises an advisory"
    log = report_to_sarif_dict(report)
    run = _run(log)

    codes = {advisory.code for advisory in report.documents[0].advisories}
    rule_ids = {result["ruleId"] for result in run["results"]}
    notification_ids = {
        item["associatedRule"]["id"]
        for item in run["invocations"][0]["toolConfigurationNotifications"]
    }
    assert not (codes & (rule_ids | notification_ids))
    assert {item["code"] for item in run["properties"]["advisories"]} == codes


def test_results_name_the_document_they_are_about(deficient_label: Path) -> None:
    for result in _run(_log(deficient_label))["results"]:
        uri = result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        assert uri == str(deficient_label)


# ---------------------------------------------------------------------------
# Determinism, and the timestamp.
# ---------------------------------------------------------------------------


def test_rendering_the_same_report_twice_yields_identical_bytes(
    deficient_label: Path, conforming_label: Path
) -> None:
    report = check_paths([deficient_label, conforming_label])
    assert render_sarif(report) == render_sarif(report)


def test_the_only_timestamp_is_the_runs_own(deficient_label: Path) -> None:
    """No wall clock beyond the one the report already carries.

    ``invocation.startTimeUtc`` and ``endTimeUtc`` are deliberately absent: this
    tool does not measure when its execution began, and inventing the number
    would make two runs over one document differ.
    """
    report = check_paths([deficient_label])
    log = report_to_sarif_dict(report)
    invocation = log["runs"][0]["invocations"][0]
    assert "startTimeUtc" not in invocation
    assert "endTimeUtc" not in invocation
    assert log["runs"][0]["properties"]["generatedAt"] == report.generated_at

    text = render_sarif(report)
    assert text.count(report.generated_at) == 1


def test_results_are_ordered_by_document_then_check(
    deficient_label: Path, conforming_label: Path
) -> None:
    results = _run(_log(deficient_label, conforming_label))["results"]
    keys = [
        (result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"], result["ruleId"])
        for result in results
    ]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# The command line. Nothing the tool concludes may move.
# ---------------------------------------------------------------------------


def test_sarif_changes_no_exit_code(
    deficient_label: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A serialiser that moved an exit code would be a rule change in disguise."""
    plain = main(["check", str(deficient_label)])
    capsys.readouterr()
    as_sarif = main(["check", str(deficient_label), "--sarif"])
    printed = capsys.readouterr().out
    assert plain == as_sarif
    assert json.loads(printed)["version"] == "2.1.0"


def test_sarif_and_json_together_is_a_usage_error(
    deficient_label: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["check", str(deficient_label), "--json", "--sarif"])
    assert raised.value.code == ExitCode.USAGE_ERROR
    assert "one" in capsys.readouterr().err


def test_sarif_over_no_paths_still_emits_a_log(capsys: pytest.CaptureFixture[str]) -> None:
    """Checking nothing produces a report in the same shape as any other run."""
    code = main(["check", "--sarif"])
    payload = json.loads(capsys.readouterr().out)
    assert code == ExitCode.NOTHING_CHECKED
    assert payload["runs"][0]["invocations"][0]["executionSuccessful"] is False


def test_sarif_reports_a_skipped_file(
    conforming_label: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A file the tool did not read is named, not dropped in silence."""
    directory = tmp_path / "labels"
    directory.mkdir()
    (directory / "label.txt").write_text(
        conforming_label.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (directory / "label.docx").write_bytes(b"PK\x03\x04 not a label this tool reads")

    main(["check", str(directory), "--sarif"])
    payload = json.loads(capsys.readouterr().out)
    skipped = payload["runs"][0]["invocations"][0]["properties"]["skipped"]
    assert any(name.endswith("label.docx") for name in skipped)


def test_an_unreadable_document_beside_a_readable_one_keeps_both(
    conforming_label: Path, image_only_pdf: Path
) -> None:
    """The unreadable one must not suppress the other, or be suppressed by it."""
    report = check_paths([conforming_label, image_only_pdf], CheckContext(supplier_name=SUPPLIER))
    assert {document.readability for document in report.documents} == {
        Readability.READABLE,
        Readability.UNREADABLE,
    }
    invocation = report_to_sarif_dict(report)["runs"][0]["invocations"][0]
    assert len(invocation["toolExecutionNotifications"]) == 1
    assert invocation["properties"]["summary"]["documents_readable"] == 1
    assert invocation["properties"]["summary"]["documents_unreadable"] == 1

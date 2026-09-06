"""The `diff` verb, and the reports it must refuse.

Three fences carry most of this module, because each is a way the verb could quietly say
something untrue:

* a check registered since the earlier report must read as *added*, not as a document
  whose conclusion moved;
* two reports at different schema versions must be refused rather than diffed, since
  ADR 0010 only makes the shape append-only *within* a version;
* an unreadable or empty report must be refused rather than parsed into an empty one,
  because two empty reports compare equal and "nothing moved" about two files that were
  never read is the vacuous pass this project exists to prevent.

The positive control matters as much: a report against itself must print nothing, or
"nothing moved" is simply what this prints when it cannot see.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from power_content_check.checks import CheckContext
from power_content_check.cli import main
from power_content_check.diff import (
    DOCUMENT_FACTS,
    NOT_COMPARED,
    Change,
    DiffExit,
    Kind,
    ReportUnreadable,
    SchemaMismatch,
    compare,
    compare_documents,
    load_report,
    render_jsonl,
    render_text,
)
from power_content_check.engine import check_paths
from power_content_check.model import SCHEMA_VERSION
from power_content_check.report import render_json

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def report_for(name: str) -> dict[str, Any]:
    """A real report over a committed fixture, not a hand-written stand-in."""
    run = check_paths([FIXTURES / name], CheckContext())
    loaded: dict[str, Any] = json.loads(render_json(run))
    return loaded


def synthetic() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "documents": [
            {
                "path": "label.pdf",
                "sha256": "a" * 64,
                "readability": "readable",
                "unreadable_reason": None,
                "page_count": 2,
                "image_count": 1,
                "vector_shape_count": 30,
                "extraction_basis": "Read 2 pages of text.",
                # Carried because this stands in for a report this tool emits, and a
                # report this tool emits carries the key. A stand-in that had drifted
                # from the real shape would make every comparison here a test of
                # something the tool never produces.
                "advisories": [],
                "results": [
                    {
                        "check_id": "PCL001",
                        "status": "conforms",
                        "finding": "found it",
                        "detail": None,
                    },
                    {
                        "check_id": "PCL012",
                        "status": "does_not_conform",
                        "finding": "phrase absent",
                        "detail": "looked in the text layer",
                    },
                ],
            }
        ],
    }


def write(tmp_path: Path, name: str, document: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


# --- the positive control -----------------------------------------------------


def test_a_report_against_itself_moves_nothing() -> None:
    assert compare(synthetic(), synthetic()) == []


def test_a_real_report_against_itself_moves_nothing() -> None:
    """Over an actual run, so the walk is exercised on the real report shape."""
    report = report_for("deficient_label.txt")
    assert report["documents"], "the fixture produced no document to compare"
    assert report["documents"][0]["results"], "the run recorded no results"
    assert compare(report, report) == []


def test_nothing_moved_prints_nothing() -> None:
    assert render_text([]) == ""
    assert render_jsonl([]) == ""


# --- the moves it must report --------------------------------------------------


def test_a_status_move_carries_both_findings() -> None:
    later = synthetic()
    later["documents"][0]["results"][1]["status"] = "conforms"
    later["documents"][0]["results"][1]["finding"] = "phrase present"
    changes = compare(synthetic(), later)
    assert [c.kind for c in changes] == [Kind.STATUS_MOVED]
    assert changes[0].check_id == "PCL012"
    assert changes[0].before == {
        "status": "does_not_conform",
        "finding": "phrase absent",
        "detail": "looked in the text layer",
    }
    after = changes[0].after
    assert after is not None
    assert after["status"] == "conforms"
    assert after["finding"] == "phrase present"


def test_the_text_rendering_shows_both_sides_and_states_no_direction() -> None:
    later = synthetic()
    later["documents"][0]["results"][1]["status"] = "conforms"
    later["documents"][0]["results"][1]["finding"] = "phrase present"
    text = render_text(compare(synthetic(), later))
    assert "does_not_conform -> conforms" in text
    assert "was: phrase absent" in text
    assert "now: phrase present" in text
    for adjective in ("improve", "better", "worse", "regress", "fixed"):
        assert adjective not in text.lower(), f"{adjective!r} is a judgment, not a fact"


def test_two_fixtures_name_exactly_the_checks_whose_status_differs() -> None:
    """The issue's second acceptance criterion, over the two committed fixtures."""
    conforming = report_for("conforming_label.txt")
    deficient = report_for("deficient_label.txt")
    # Match on check id alone: the two fixtures are different files, so path and hash
    # both differ by construction.
    left = {r["check_id"]: r for r in conforming["documents"][0]["results"]}
    right = {r["check_id"]: r for r in deficient["documents"][0]["results"]}
    expected = {i for i in left.keys() & right.keys() if left[i]["status"] != right[i]["status"]}
    assert expected, "the two fixtures conclude identically, so this proves nothing"

    aligned = json.loads(json.dumps(deficient))
    aligned["documents"][0]["path"] = conforming["documents"][0]["path"]
    aligned["documents"][0]["sha256"] = conforming["documents"][0]["sha256"]
    changes = compare(conforming, aligned)
    moved = {c.check_id for c in changes if c.kind is Kind.STATUS_MOVED}
    assert moved == expected
    for change in changes:
        if change.kind is Kind.STATUS_MOVED:
            before_side, after_side = change.before, change.after
            assert before_side is not None and after_side is not None
            assert before_side["finding"], f"{change.check_id} lost its earlier finding"
            assert after_side["finding"], f"{change.check_id} lost its later finding"


@pytest.mark.parametrize(
    ("fact", "value"),
    [
        ("page_count", 5),
        ("readability", "unreadable"),
        ("image_count", 9),
        ("vector_shape_count", 0),
        ("extraction_basis", "Read 5 pages of text."),
    ],
)
def test_a_moved_document_fact_is_reported(fact: str, value: Any) -> None:
    later = synthetic()
    later["documents"][0][fact] = value
    changes = compare(synthetic(), later)
    assert [c.kind for c in changes] == [Kind.DOCUMENT_FACT_MOVED]
    assert changes[0].field == fact
    assert changes[0].after == {fact: value}


# --- the fence: added is not moved ---------------------------------------------


def test_a_newly_registered_check_is_added_never_a_status_move() -> None:
    later = synthetic()
    later["documents"][0]["results"].append(
        {
            "check_id": "PCL099",
            "status": "not_evaluated",
            "finding": "registered, enforces nothing",
            "detail": None,
        }
    )
    changes = compare(synthetic(), later)
    assert [c.kind for c in changes] == [Kind.CHECK_ADDED]
    assert changes[0].check_id == "PCL099"
    assert changes[0].before is None
    assert "newly registered" in render_text(changes)


def test_a_retired_check_is_removed_never_a_status_move() -> None:
    later = synthetic()
    later["documents"][0]["results"] = later["documents"][0]["results"][:1]
    changes = compare(synthetic(), later)
    assert [c.kind for c in changes] == [Kind.CHECK_REMOVED]
    assert changes[0].after is None


def test_a_document_on_one_side_only_is_reported_as_such() -> None:
    later = synthetic()
    later["documents"].append(dict(synthetic()["documents"][0], path="other.pdf", sha256="b" * 64))
    changes = compare(synthetic(), later)
    assert [c.kind for c in changes] == [Kind.DOCUMENT_ADDED]
    assert changes[0].document == "other.pdf"


def test_by_hash_matches_documents_whose_paths_moved() -> None:
    later = synthetic()
    later["documents"][0]["path"] = "renamed.pdf"
    later["documents"][0]["results"][0]["status"] = "not_evaluated"
    by_path = compare(synthetic(), later)
    assert {c.kind for c in by_path} == {Kind.DOCUMENT_ADDED, Kind.DOCUMENT_REMOVED}
    by_hash = compare(synthetic(), later, by_hash=True)
    assert [c.kind for c in by_hash] == [Kind.STATUS_MOVED]


# --- determinism ---------------------------------------------------------------


def test_rows_are_sorted_so_two_runs_emit_identical_bytes() -> None:
    later = synthetic()
    later["documents"][0]["results"][0]["status"] = "not_evaluated"
    later["documents"][0]["page_count"] = 7
    first = render_jsonl(compare(synthetic(), later))
    second = render_jsonl(compare(synthetic(), later))
    assert first == second
    lines = [json.loads(line) for line in first.splitlines()]
    assert lines == sorted(lines, key=lambda r: (r["document"], r["kind"], r["check_id"] or ""))


# --- the reports it must refuse -------------------------------------------------


def test_a_schema_version_mismatch_is_refused_naming_both() -> None:
    later = synthetic()
    later["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(SchemaMismatch) as caught:
        compare(synthetic(), later)
    assert str(SCHEMA_VERSION) in str(caught.value)
    assert str(SCHEMA_VERSION + 1) in str(caught.value)


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ReportUnreadable, match="no such file"):
        load_report(tmp_path / "absent.json")


def test_an_empty_file_is_refused_rather_than_read_as_a_report(tmp_path: Path) -> None:
    """The filename deliberately avoids the word matched, so the path cannot satisfy it."""
    path = tmp_path / "nothing-here.json"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ReportUnreadable, match="the file is empty"):
        load_report(path)


def test_an_unparseable_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ReportUnreadable, match="not parseable"):
        load_report(path)


def test_a_json_document_that_is_not_an_object_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ReportUnreadable, match="not a report object"):
        load_report(path)


def test_a_document_without_the_matching_key_is_refused() -> None:
    report = synthetic()
    del report["documents"][0]["sha256"]
    with pytest.raises(ReportUnreadable, match="carries no sha256"):
        compare(report, report, by_hash=True)


def test_two_documents_sharing_a_key_are_refused() -> None:
    report = synthetic()
    report["documents"].append(dict(report["documents"][0]))
    with pytest.raises(ReportUnreadable, match="share the key"):
        compare(report, report)


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ({"schema_version": SCHEMA_VERSION}, "no 'documents' key"),
        ({"documents": []}, "no 'schema_version' key"),
    ],
    ids=["no-documents", "no-schema-version"],
)
def test_a_file_that_is_not_one_of_this_tools_reports_is_refused(
    tmp_path: Path, document: dict[str, Any], expected: str
) -> None:
    path = write(tmp_path, "other.json", document)
    with pytest.raises(ReportUnreadable, match=expected):
        load_report(path)


def test_documents_not_a_list_is_refused(tmp_path: Path) -> None:
    path = write(tmp_path, "odd.json", {"schema_version": SCHEMA_VERSION, "documents": {}})
    with pytest.raises(ReportUnreadable, match="not a list"):
        compare(load_report(path), synthetic())


def test_a_document_entry_that_is_not_an_object_is_refused(tmp_path: Path) -> None:
    path = write(tmp_path, "odd.json", {"schema_version": SCHEMA_VERSION, "documents": ["x"]})
    with pytest.raises(ReportUnreadable, match="not an object"):
        compare(load_report(path), synthetic())


# --- exit codes through the CLI -------------------------------------------------


def test_diffing_a_report_against_itself_exits_zero_and_prints_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write(tmp_path, "r.json", synthetic())
    assert main(["diff", str(path), str(path)]) == DiffExit.UNCHANGED
    assert capsys.readouterr().out == ""


def test_a_moved_status_exits_three(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    later = synthetic()
    later["documents"][0]["results"][0]["status"] = "not_evaluated"
    before = write(tmp_path, "before.json", synthetic())
    after = write(tmp_path, "after.json", later)
    assert main(["diff", str(before), str(after)]) == DiffExit.MOVED
    assert "PCL001" in capsys.readouterr().out


def test_jsonl_emits_one_object_per_change(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    later = synthetic()
    later["documents"][0]["results"][0]["status"] = "not_evaluated"
    later["documents"][0]["page_count"] = 3
    before = write(tmp_path, "before.json", synthetic())
    after = write(tmp_path, "after.json", later)
    assert main(["diff", str(before), str(after), "--jsonl"]) == DiffExit.MOVED
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert {json.loads(line)["kind"] for line in lines} == {
        "status_moved",
        "document_fact_moved",
    }


def test_a_schema_mismatch_exits_sixty_four_and_says_so_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    later = synthetic()
    later["schema_version"] = SCHEMA_VERSION + 1
    before = write(tmp_path, "before.json", synthetic())
    after = write(tmp_path, "after.json", later)
    assert main(["diff", str(before), str(after)]) == DiffExit.REFUSED
    captured = capsys.readouterr()
    assert captured.out == "", "a refused comparison must not print an empty diff"
    assert "schema" in captured.err


def test_an_unreadable_report_exits_sixty_four(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = write(tmp_path, "before.json", synthetic())
    assert main(["diff", str(before), str(tmp_path / "absent.json")]) == DiffExit.REFUSED
    assert capsys.readouterr().out == ""


def test_by_hash_is_reachable_from_the_command_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    later = synthetic()
    later["documents"][0]["path"] = "renamed.pdf"
    later["documents"][0]["results"][0]["status"] = "not_evaluated"
    before = write(tmp_path, "before.json", synthetic())
    after = write(tmp_path, "after.json", later)
    assert main(["diff", str(before), str(after), "--by-hash"]) == DiffExit.MOVED
    assert "PCL001" in capsys.readouterr().out


# --- every rendering branch is reachable ----------------------------------------


def test_every_kind_of_movement_has_a_rendering() -> None:
    """A branch nothing reaches is a sentence nobody has read.

    Each rendering is checked here because the text output is what a maintainer actually
    looks at, and a `Kind` added later without a rendering would otherwise fall through
    to whichever branch happens to be last.
    """
    later = synthetic()
    later["documents"][0]["results"][1]["status"] = "conforms"
    later["documents"][0]["results"].append(
        {"check_id": "PCL099", "status": "conforms", "finding": "new", "detail": None}
    )
    later["documents"][0]["page_count"] = 4
    later["documents"].append(dict(synthetic()["documents"][0], path="added.pdf", sha256="c" * 64))
    earlier = synthetic()
    earlier["documents"].append(dict(synthetic()["documents"][0], path="gone.pdf", sha256="d" * 64))
    changes = compare(earlier, later)
    kinds = {c.kind for c in changes}
    assert kinds == {
        Kind.STATUS_MOVED,
        Kind.CHECK_ADDED,
        Kind.DOCUMENT_FACT_MOVED,
        Kind.DOCUMENT_ADDED,
        Kind.DOCUMENT_REMOVED,
    }
    text = render_text(changes)
    assert "in the later report only" in text
    assert "in the earlier report only" in text
    assert "page_count: 2 -> 4" in text
    assert "newly registered" in text
    assert "5 movements across 3 documents" in text


def test_a_retired_check_renders_both_the_status_and_the_finding_it_had() -> None:
    later = synthetic()
    later["documents"][0]["results"] = later["documents"][0]["results"][:1]
    text = render_text(compare(synthetic(), later))
    assert "PCL012: does_not_conform in the earlier report, not in the later one" in text
    assert "was: phrase absent" in text


def test_a_row_missing_the_side_it_needs_raises_rather_than_printing_none() -> None:
    """`python -O` strips asserts; this invariant must hold without them.

    Rendering `None` into "was: None" would put a sentence in front of a reader that
    looks like a finding and is the absence of one.
    """
    broken = Change(
        kind=Kind.STATUS_MOVED,
        document="label.pdf",
        check_id="PCL001",
        field=None,
        before=None,
        after={"status": "conforms", "finding": "x", "detail": None},
    )
    with pytest.raises(ValueError, match="carries no before side"):
        render_text([broken])


# --- the list of what is compared, held to the report it compares -------------------------


class TestNothingASideCarriesGoesUncompared:
    """`DOCUMENT_FACTS` is hand kept, and until now it was held to nothing.

    The first key added to a document report after this module was written walked
    straight past it. `advisories` was emitted by `DocumentReport.to_dict`, was absent
    from `DOCUMENT_FACTS`, and no test in the suite could tell. A hand-kept list of what
    the code emits, maintained beside the code that emits it, is exactly the thing that
    goes quietly out of date, and the failure is invisible: the diff keeps passing and
    simply reports less than a reader assumes.

    The binding is exhaustive in both directions. A key the report emits that is neither
    compared nor excused fails; an excuse or a fact naming a key the report does not emit
    fails too, because a rule about a key that no longer exists is a rule that has stopped
    covering anything.
    """

    def _document_keys(self, conforming_label: Path) -> set[str]:
        report = check_paths([conforming_label])
        return set(report.documents[0].to_dict())

    def test_the_report_has_keys_to_check(self, conforming_label: Path) -> None:
        """The denominator. An empty key set passes every rule below."""
        assert len(self._document_keys(conforming_label)) > 5

    def test_every_document_key_is_either_compared_or_excused(self, conforming_label: Path) -> None:
        emitted = self._document_keys(conforming_label)
        accounted = set(DOCUMENT_FACTS) | set(NOT_COMPARED)
        missing = sorted(emitted - accounted)
        assert missing == [], (
            f"a document report carries {missing}, which `diff` neither compares nor "
            "excuses. Add each to DOCUMENT_FACTS, or to NOT_COMPARED with the reason."
        )

    def test_nothing_compared_or_excused_has_left_the_report(self, conforming_label: Path) -> None:
        emitted = self._document_keys(conforming_label)
        accounted = set(DOCUMENT_FACTS) | set(NOT_COMPARED)
        orphaned = sorted(accounted - emitted)
        assert orphaned == [], (
            f"`diff` names {orphaned}, which a document report no longer carries. A rule "
            "about a key that does not exist has stopped covering anything."
        )

    def test_a_key_is_not_both_compared_and_excused(self) -> None:
        assert not (set(DOCUMENT_FACTS) & set(NOT_COMPARED))

    def test_every_excuse_gives_a_reason(self) -> None:
        """An excuse with no reason is an omission wearing a decision's clothes."""
        for key, reason in NOT_COMPARED.items():
            assert len(reason) > 20, f"{key} is excused without saying why"


class TestAdvisoriesAreComparedWithoutBeingConclusions:
    def _report(self, path: Path) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads(render_json(check_paths([path])))
        return loaded

    @pytest.fixture
    def noisy_label(self, tmp_path: Path, conforming_label: Path) -> Path:
        path = tmp_path / "noisy.txt"
        path.write_text(
            conforming_label.read_text(encoding="utf-8").replace("CO2e", "CO 2e"),
            encoding="utf-8",
        )
        return path

    def test_an_advisory_appearing_is_reported(
        self, conforming_label: Path, noisy_label: Path
    ) -> None:
        before = self._report(conforming_label)["documents"][0]
        after = self._report(noisy_label)["documents"][0]
        changes = compare_documents(before, after, key="label")
        moved = [c for c in changes if c.kind is Kind.ADVISORY_MOVED]
        assert len(moved) == 1
        assert moved[0].side("before")["codes"] == []
        assert moved[0].side("after")["codes"] == ["ADV-BROKEN-PHRASE"]

    def test_the_same_advisories_on_both_sides_move_nothing(self, noisy_label: Path) -> None:
        document = self._report(noisy_label)["documents"][0]
        changes = compare_documents(document, document, key="label")
        assert [c for c in changes if c.kind is Kind.ADVISORY_MOVED] == []

    def test_an_advisory_is_not_filed_among_the_document_facts(
        self, conforming_label: Path, noisy_label: Path
    ) -> None:
        """It is not a conclusion, and the kinds keep that visible."""
        before = self._report(conforming_label)["documents"][0]
        after = self._report(noisy_label)["documents"][0]
        facts = [
            c
            for c in compare_documents(before, after, key="label")
            if c.kind is Kind.DOCUMENT_FACT_MOVED
        ]
        assert all(c.field != "advisories" for c in facts)

    def test_a_report_predating_the_channel_is_not_read_as_an_empty_one(
        self, noisy_label: Path
    ) -> None:
        """The whole reason this is not a plain `.get(key, [])`.

        Adding a key is append only within a schema version (ADR 0010), so a report
        written before the channel existed declares the same `schema_version` as one
        written after and is not refused. Reading its missing key as an empty list would
        report an advisory appearing on every document of every diff spanning that
        change, which is an absence rendered as a movement.
        """
        after = self._report(noisy_label)["documents"][0]
        old_style = {k: v for k, v in after.items() if k != "advisories"}
        assert "advisories" not in old_style

        changes = compare_documents(old_style, after, key="label")
        kinds = {c.kind for c in changes}
        assert Kind.ADVISORIES_NOT_COMPARABLE in kinds
        assert Kind.ADVISORY_MOVED not in kinds

    def test_the_uncomparable_row_says_which_side_was_missing_it(self, noisy_label: Path) -> None:
        after = self._report(noisy_label)["documents"][0]
        old_style = {k: v for k, v in after.items() if k != "advisories"}
        row = next(
            c
            for c in compare_documents(old_style, after, key="label")
            if c.kind is Kind.ADVISORIES_NOT_COMPARABLE
        )
        assert row.side("after")["missing_from"] == "the earlier"
        rendered = render_text([row])
        assert "predates the channel" in rendered
        assert "an absent key is not an empty list" in rendered

    def test_a_missing_key_on_the_later_side_is_named_too(self, noisy_label: Path) -> None:
        after = self._report(noisy_label)["documents"][0]
        old_style = {k: v for k, v in after.items() if k != "advisories"}
        row = next(
            c
            for c in compare_documents(after, old_style, key="label")
            if c.kind is Kind.ADVISORIES_NOT_COMPARABLE
        )
        assert row.side("after")["missing_from"] == "the later"

    def test_the_move_renders_with_both_sides_and_its_own_caveat(
        self, conforming_label: Path, noisy_label: Path
    ) -> None:
        before = self._report(conforming_label)["documents"][0]
        after = self._report(noisy_label)["documents"][0]
        row = next(
            c
            for c in compare_documents(before, after, key="label")
            if c.kind is Kind.ADVISORY_MOVED
        )
        rendered = render_text([row])
        assert "ADV-BROKEN-PHRASE" in rendered
        assert "in no count and no exit code" in rendered

    def test_every_kind_this_module_defines_can_be_rendered(self) -> None:
        """A kind with no branch in `_describe` falls through to the last one.

        The renderer ends in a bare `return`, so a kind nobody wrote a branch for is
        printed as "in the earlier report only", which is a sentence about something else
        entirely. Two kinds were added here; this is what keeps a third from arriving
        silently wrong.
        """
        sides = {
            "advisories": [],
            "codes": [],
            "missing_from": "the earlier",
            "status": "x",
            "finding": "y",
            "readability": "readable",
        }
        for kind in Kind:
            row = Change(
                kind=kind,
                document="label",
                check_id="PCL001",
                field="readability",
                before=dict(sides),
                after=dict(sides),
            )
            rendered = render_text([row])
            assert rendered.strip(), kind
            if kind not in (Kind.DOCUMENT_ADDED, Kind.DOCUMENT_REMOVED):
                assert "in the earlier report only" not in rendered, (
                    f"{kind.value} has no branch in _describe and fell through to the "
                    "document-removed wording"
                )

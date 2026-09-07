"""The published calibration figures, held against the evidence behind them.

``README.md`` and ``docs/sources.md`` publish four numbers about the calibration
set: thirty four labels read, the same two checks and only those two deviating
on every one of them, fifteen checks conforming on every one, and seventeen
checks evaluable without a supplier name on the command line. Those numbers were
typed by hand from a run over a cache that git excludes and that no one else has.
Nothing held them to anything.

``scripts/check_regressions.py census`` writes ``docs/calibration/census.json``
from that cache: per registered check, on how many labels it conformed, deviated
and went unevaluated, plus the digests of the labels counted. That file is
committed, so from the moment it exists the figures have evidence in the
repository and this module binds the two together.

Two tests, and only one of them is allowed to be conditional
------------------------------------------------------------

The obvious way to write this is one test that skips when the cache is absent.
That would be a gate that cannot fail where it is watched: it would run on one
laptop and skip in CI, which is the shape this repository has removed elsewhere
(``tests/test_release_claims.py``, ``tests/test_fail_closed.py``). The split that
saves it is that only *regenerating* the census needs the cache. Reading it does
not. So:

* Everything in :class:`TestPublishedFiguresBind` runs everywhere,
  unconditionally, with no cache and no network.
* :class:`TestTheCensusMatchesTheCache` is the only conditional part, and all it
  does is regenerate the census from a cache and require the committed file to
  be what comes out.

The rule's failing branch is driven on every run
------------------------------------------------

``docs/calibration/census.json`` cannot be generated here -- the cache is not in
this repository and no label may be committed to it -- so on a tree where the
census is absent, a test that only compared the real README to the real census
would pass by never comparing. That is the same vacuous pass
``tests/test_release_claims.py`` refuses, and it is refused the same way: the
comparison is a pure function over (published figures, census), it is driven from
synthetic censuses on every run with both a positive and several negative
controls, and the real pair is fed through it as one more case whenever the real
census exists. The literal figures the README publishes are pinned here as well,
so a hand edit of "thirty four" fails today, with no census and no cache.

The one owner step this leaves is naming the state. While no census is committed
the README's figures rest on a hand-typed note, and
``docs/calibration/README.md`` has to say so; :meth:`test_an_absent_census_is_disclosed`
enforces that, so the absence is never silent.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_regressions.py"
README = ROOT / "README.md"
SOURCES = ROOT / "docs" / "sources.md"
CALIBRATION = ROOT / "docs" / "calibration"
CENSUS = CALIBRATION / "census.json"

#: The figures the project publishes about its calibration set, pinned to their
#: literal values. A property cannot catch a wrong constant: a test that only
#: said "the README figure equals the census figure" would agree with both sides
#: being wrong together, and both sides are edited by the same hand in the same
#: pull request. These are the numbers, written down once.
PUBLISHED: dict[str, int] = {
    "labels_read": 34,
    "checks_deviating": 2,
    "checks_conforming_on_every_label": 15,
    "checks_evaluable_without_a_supplier_name": 17,
}

#: The sentences the numbers above are written out in, so that editing the prose
#: without editing this file fails. Matched after collapsing whitespace, because
#: these sentences wrap and rewrapping a paragraph is not a change to a figure.
CLAIMS: tuple[tuple[Path, str], ...] = (
    (
        README,
        "On all thirty four the same two checks, and only those two, report a deviation.",
    ),
    (
        SOURCES,
        "On all thirty four, the same two checks and only those two report a deviation",
    ),
    (
        SOURCES,
        "Of the seventeen checks that can be evaluated without a supplier name on the "
        "command line, fifteen conform on every one of the thirty four and two deviate.",
    ),
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("census_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT_MODULE = _load()


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _synthetic_census(
    *,
    labels: int = PUBLISHED["labels_read"],
    deviating: int = PUBLISHED["checks_deviating"],
    conforming: int = PUBLISHED["checks_conforming_on_every_label"],
    unevaluated_on_one: int = 0,
    duplicate_digest: bool = False,
) -> dict[str, Any]:
    """A census with the requested shape, built from nothing but arithmetic.

    Carries no cache, no label and no digest of anything real: the digests are
    counters rendered as hex, because what the comparison reads from them is
    whether they repeat, never what they are.
    """
    digests = [f"{index:064x}" for index in range(labels)]
    if duplicate_digest and digests:
        digests[-1] = digests[0]
    checks: dict[str, dict[str, int]] = {}
    index = 0
    for _ in range(deviating):
        index += 1
        checks[f"PCL{index:03d}"] = {
            "conforms": 0,
            "does_not_conform": labels,
            "not_evaluated": 0,
        }
    for _ in range(conforming):
        index += 1
        checks[f"PCL{index:03d}"] = {
            "conforms": labels,
            "does_not_conform": 0,
            "not_evaluated": 0,
        }
    for _ in range(unevaluated_on_one):
        index += 1
        checks[f"PCL{index:03d}"] = {
            "conforms": max(labels - 1, 0),
            "does_not_conform": 0,
            "not_evaluated": min(1, labels),
        }
    return {
        "census_version": 1,
        "tool": "power-content-check",
        "tool_version": "0.1.0",
        "ruleset_id": "ccr-t20-art5@2025-06-18",
        "ruleset_effective": "2025-06-18",
        "label_vintage": "2024",
        "labels_read": len(digests),
        "labels": digests,
        "checks": checks,
    }


def figures_from(census: dict[str, Any]) -> dict[str, int]:
    """The four published figures, derived from a census rather than typed.

    ``checks_evaluable_without_a_supplier_name`` is the checks that reached a
    verdict on every label. It is not a fourth independent count: a check that
    went unevaluated even once is not one of the seventeen, which is exactly the
    distinction ``docs/sources.md`` draws.
    """
    read = int(census["labels_read"])
    checks: dict[str, dict[str, int]] = census["checks"]
    deviating = [c for c in checks.values() if c["does_not_conform"] > 0]
    conforming = [
        c for c in checks.values() if c["conforms"] == read and c["does_not_conform"] == 0
    ]
    evaluable = [c for c in checks.values() if c["not_evaluated"] == 0]
    return {
        "labels_read": read,
        "checks_deviating": len(deviating),
        "checks_conforming_on_every_label": len(conforming),
        "checks_evaluable_without_a_supplier_name": len(evaluable),
    }


def disagreements(published: dict[str, int], census: dict[str, Any]) -> list[str]:
    """Every way the published figures and a census fail to say the same thing.

    Returned rather than raised so the whole disagreement is reported at once,
    and so both branches of the rule can be driven on synthetic input.
    """
    problems: list[str] = list(SCRIPT_MODULE.census_problems(census))
    derived = figures_from(census)
    for name, claimed in sorted(published.items()):
        found = derived[name]
        if found != claimed:
            problems.append(f"{name}: the project publishes {claimed}, the census holds {found}")
    return problems


class TestPublishedFiguresBind:
    """Unconditional. No cache, no network, no committed census required."""

    def test_the_published_figures_are_pinned_to_their_prose(self) -> None:
        """A hand edit of "thirty four" fails here, today, with no census."""
        for path, claim in CLAIMS:
            assert _flat(claim) in _flat(path.read_text(encoding="utf-8")), (
                f"{path.name} no longer carries: {claim}\n"
                "If the calibration set changed, change PUBLISHED in this file too, "
                "and regenerate docs/calibration/census.json from the cache."
            )
        assert (
            PUBLISHED["checks_conforming_on_every_label"] + PUBLISHED["checks_deviating"]
            == PUBLISHED["checks_evaluable_without_a_supplier_name"]
        ), "the published figures do not add up to each other"

    def test_a_census_that_agrees_reports_nothing(self) -> None:
        """Positive control. The rule cannot pass by never passing."""
        assert disagreements(PUBLISHED, _synthetic_census()) == []

    @pytest.mark.parametrize(
        ("kwargs", "expected_fragment"),
        [
            ({"labels": 33}, "labels_read"),
            ({"deviating": 3}, "checks_deviating"),
            ({"deviating": 0}, "checks_deviating"),
            ({"conforming": 14, "unevaluated_on_one": 1}, "checks_conforming_on_every_label"),
        ],
    )
    def test_a_census_that_disagrees_is_reported(
        self, kwargs: dict[str, Any], expected_fragment: str
    ) -> None:
        """Negative controls, executed on every run rather than on a bad day."""
        found = disagreements(PUBLISHED, _synthetic_census(**kwargs))
        assert found, f"a census built with {kwargs} was accepted"
        assert any(expected_fragment in problem for problem in found), found

    def test_a_repeated_label_digest_is_refused(self) -> None:
        """One label counted twice would inflate every figure in the census."""
        found = SCRIPT_MODULE.census_problems(_synthetic_census(labels=34, duplicate_digest=True))
        assert any("repeats a digest" in problem for problem in found), found

    def test_a_check_whose_outcomes_do_not_cover_the_labels_is_refused(self) -> None:
        """A check missing an outcome on some label is a hole, not a pass."""
        census = _synthetic_census()
        tally = census["checks"][next(iter(census["checks"]))]
        tally[max(tally, key=lambda key: tally[key])] -= 1
        found = SCRIPT_MODULE.census_problems(census)
        assert any("outcomes recorded against" in problem for problem in found), found

    def test_the_committed_census_agrees_with_the_published_figures(self) -> None:
        """The real pair, fed through the same function as the synthetic ones.

        Conditional on a committed file rather than on a machine-local cache, so
        it is the same verdict everywhere: absent for everyone today, binding for
        everyone the moment the census lands.
        """
        if not CENSUS.exists():
            pytest.skip("no census committed yet; test_an_absent_census_is_disclosed covers it")
        census = json.loads(CENSUS.read_text(encoding="utf-8"))
        assert disagreements(PUBLISHED, census) == []

    def test_the_committed_census_names_no_supplier_path_or_url(self) -> None:
        """The refusal on rankings is what lets the census be published at all."""
        if not CENSUS.exists():
            pytest.skip("no census committed yet")
        raw = CENSUS.read_text(encoding="utf-8")
        for forbidden in ("http://", "https://", ".pdf", "/", "\\"):
            assert forbidden not in raw, f"the census carries {forbidden!r}"

    def test_an_absent_census_is_disclosed(self) -> None:
        """No census is a legitimate state. An undisclosed one is not.

        The same two-state rule ``tests/test_release_claims.py`` applies to the
        declared version: being pre-evidence is not the defect, publishing the
        figures in silence is.
        """
        if CENSUS.exists():
            return
        note = CALIBRATION / "README.md"
        assert note.exists(), (
            "no docs/calibration/census.json and no docs/calibration/README.md: "
            "the published figures rest on a hand-typed note and nothing says so"
        )
        text = _flat(note.read_text(encoding="utf-8"))
        assert "census.json" in text and "not committed" in text, (
            "docs/calibration/README.md must say plainly that no census is committed yet"
        )


class TestTheCensusMatchesTheCache:
    """The only conditional part, and it is conditional on the cache alone.

    Regenerating the census is the one operation that genuinely needs the
    labels. Everything a reader of this repository can check is in the class
    above.
    """

    def test_the_committed_census_is_what_the_cache_produces(self) -> None:
        if not CENSUS.exists():
            pytest.skip("no census committed yet")
        cache = SCRIPT_MODULE.CACHE
        if not cache.is_dir() or not any(
            p.suffix.lower() in (".pdf", ".txt") for p in cache.iterdir()
        ):
            pytest.skip("no local label cache; the committed census cannot be regenerated here")
        committed = json.loads(CENSUS.read_text(encoding="utf-8"))
        rebuilt = SCRIPT_MODULE.build_census(
            SCRIPT_MODULE._run_over_cache(), committed["label_vintage"]
        )
        assert rebuilt == committed, (
            "the committed census is not what this cache produces. Rerun "
            "'check_regressions.py census --vintage <year>' and read the diff before "
            "committing it."
        )


class TestTheCensusBuilder:
    """The builder, driven over synthetic reports. Unconditional."""

    def _report(self, statuses: dict[str, list[str]]) -> Any:
        from power_content_check.checks import CHECKS
        from power_content_check.model import (
            CheckResult,
            DocumentReport,
            Readability,
            RunReport,
            Status,
        )

        documents = []
        for digest, per_check in statuses.items():
            results = [
                CheckResult(
                    check_id=registered.spec.id,
                    status=Status(per_check[index]),
                    finding="synthetic",
                )
                for index, registered in enumerate(CHECKS)
            ]
            documents.append(
                DocumentReport(
                    path="synthetic",
                    readability=Readability.READABLE,
                    unreadable_reason=None,
                    sha256=digest,
                    page_count=1,
                    results=results,
                )
            )
        return RunReport(
            tool="power-content-check",
            tool_version="0.0.0",
            ruleset_id="r",
            ruleset_effective="e",
            generated_at="t",
            notice="n",
            documents=documents,
        )

    def _all(self, status: str) -> list[str]:
        from power_content_check.checks import CHECKS

        return [status] * len(CHECKS)

    def test_it_counts_every_registered_check_on_every_label(self) -> None:
        from power_content_check.checks import CHECKS

        report = self._report({"a" * 64: self._all("conforms"), "b" * 64: self._all("conforms")})
        census = SCRIPT_MODULE.build_census(report, "2024")
        assert census["labels_read"] == 2
        assert set(census["checks"]) == {r.spec.id for r in CHECKS}
        assert all(tally["conforms"] == 2 for tally in census["checks"].values())
        assert SCRIPT_MODULE.census_problems(census) == []

    def test_it_refuses_a_cache_holding_one_label_twice(self) -> None:
        report = self._report({"a" * 64: self._all("conforms")})
        report.documents.append(report.documents[0])
        with pytest.raises(SCRIPT_MODULE.CensusError, match="appears twice"):
            SCRIPT_MODULE.build_census(report, "2024")

    def test_it_refuses_a_document_with_no_digest(self) -> None:
        from power_content_check.model import DocumentReport, Readability

        report = self._report({"a" * 64: self._all("conforms")})
        report.documents.append(
            DocumentReport(
                path="synthetic",
                readability=Readability.UNREADABLE,
                unreadable_reason="no",
                sha256=None,
                page_count=None,
            )
        )
        with pytest.raises(SCRIPT_MODULE.CensusError, match="no content digest"):
            SCRIPT_MODULE.build_census(report, "2024")

    def test_the_vintage_is_required_rather_than_guessed(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Which label year the cache holds is a fact about the fetch."""
        monkeypatch.setattr(sys, "argv", ["check_regressions.py", "census"])
        assert SCRIPT_MODULE.main() == 64
        assert "--vintage is required" in capsys.readouterr().out

    def test_it_writes_a_census_carrying_no_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """End to end over a cache of this repository's synthetic fixtures."""
        cache = tmp_path / "cache"
        cache.mkdir()
        for name in ("conforming_label", "deficient_label"):
            source = ROOT / "tests" / "fixtures" / f"{name}.txt"
            (cache / f"{name}.txt").write_text(source.read_text(encoding="utf-8"))
        out = tmp_path / "docs" / "calibration" / "census.json"
        monkeypatch.setattr(SCRIPT_MODULE, "CACHE", cache)
        monkeypatch.setattr(SCRIPT_MODULE, "CENSUS", out)
        monkeypatch.setattr(sys, "argv", ["check_regressions.py", "census", "--vintage", "2024"])
        assert SCRIPT_MODULE.main() == 0
        raw = out.read_text(encoding="utf-8")
        assert "conforming_label" not in raw and "/" not in raw
        assert json.loads(raw)["labels_read"] == 2

"""The regression script's own denominator.

``scripts/check_regressions.py`` is not part of the package and ``make
verify`` does not run it. It is tested anyway, because three of this
repository's open pull requests quote one line of its output as the evidence
that no conclusion about a published label moved:

    10 documents conclude exactly as recorded.

A line of evidence that can be printed over an empty comparison is worth
nothing, and that is exactly what it used to do: ``compare`` diffed the
intersection of the current cache and the baseline, and when that intersection
was empty it printed the sentence above with the size of the cache in it and
exited 0. Nothing had been compared. This module holds the property that makes
the sentence mean something.

The cache the real script reads is local and git ignored, so these tests build
their own out of the repository's synthetic fixtures and point the script at
it. No published label is involved, here or anywhere in this repository.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_regressions.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_regressions_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ModuleType, Path, Path, list[str]]:
    """The script, pointed at a cache of this repository's own fixtures."""
    module = _load()
    cache = tmp_path / "cache"
    cache.mkdir()
    baseline = cache / "fingerprints.json"
    monkeypatch.setattr(module, "CACHE", cache)
    monkeypatch.setattr(module, "BASELINE", baseline)
    return module, cache, baseline, []


def _stock(cache: Path, *names: str) -> None:
    """Copy named repository fixtures into the cache under stable filenames."""
    for name in names:
        source = ROOT / "tests" / "fixtures" / f"{name}.txt"
        (cache / f"{name}.txt").write_text(source.read_text(encoding="utf-8"))


def _run(module: ModuleType, action: str, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "argv", ["check_regressions.py", action])
    code = module.main()
    assert isinstance(code, int)
    return code


class TestComparingNothingIsNotAPass:
    def test_a_recorded_cache_compares_clean(
        self,
        script: tuple[ModuleType, Path, Path, list[str]],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The positive control. Nothing about the ordinary path moves."""
        module, cache, _baseline, _ = script
        _stock(cache, "conforming_label", "deficient_label")
        assert _run(module, "record", monkeypatch) == 0
        capsys.readouterr()
        assert _run(module, "compare", monkeypatch) == 0
        assert "2 documents conclude exactly as recorded." in capsys.readouterr().out

    def test_a_cache_replaced_wholesale_does_not_report_a_pass(
        self,
        script: tuple[ModuleType, Path, Path, list[str]],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The defect. Every digest in the baseline is gone, so the comparison
        has an empty denominator and can say nothing about this tree."""
        module, cache, _baseline, _ = script
        _stock(cache, "conforming_label")
        assert _run(module, "record", monkeypatch) == 0
        capsys.readouterr()

        (cache / "conforming_label.txt").unlink()
        _stock(cache, "deficient_label")

        assert _run(module, "compare", monkeypatch) == 1
        out = capsys.readouterr().out
        assert "nothing was compared" in out
        assert "conclude exactly as recorded" not in out

    def test_the_count_reported_is_the_count_compared(
        self,
        script: tuple[ModuleType, Path, Path, list[str]],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A partial overlap must not report the size of the cache.

        One document is in both, one is new. Saying "2 conclude exactly as
        recorded" would credit the baseline with a document it has never
        seen.
        """
        module, cache, _baseline, _ = script
        _stock(cache, "conforming_label")
        assert _run(module, "record", monkeypatch) == 0
        capsys.readouterr()

        _stock(cache, "deficient_label")
        assert _run(module, "compare", monkeypatch) == 0
        out = capsys.readouterr().out
        assert "1 documents conclude exactly as recorded." in out
        assert "1 documents are new to the cache" in out

    def test_a_moved_conclusion_is_still_caught(
        self,
        script: tuple[ModuleType, Path, Path, list[str]],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The other positive control: the comparison it does make still bites."""
        module, cache, baseline, _ = script
        _stock(cache, "conforming_label", "deficient_label")
        assert _run(module, "record", monkeypatch) == 0
        capsys.readouterr()

        recorded = json.loads(baseline.read_text())
        victim = sorted(recorded)[0]
        recorded[victim] = "0" * 64
        baseline.write_text(json.dumps(recorded, indent=2, sort_keys=True) + "\n")

        assert _run(module, "compare", monkeypatch) == 1
        assert "conclude differently than the baseline says" in capsys.readouterr().out

    def test_an_empty_cache_refuses_before_it_compares(
        self,
        script: tuple[ModuleType, Path, Path, list[str]],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """An empty denominator is refused one step earlier, in collect()."""
        module, _cache, _baseline, _ = script
        with pytest.raises(SystemExit) as excinfo:
            _run(module, "compare", monkeypatch)
        assert excinfo.value.code == 1
        assert "no supported documents" in capsys.readouterr().out

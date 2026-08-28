"""Rules about the repository itself, enforced rather than remembered."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

TEXT_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".txt", ".cff"}
SKIP_PARTS = {".git", ".venv", "__pycache__", "htmlcov", "examples", ".ruff_cache"}
SKIP_NAMES = {"LICENSE", "uv.lock"}


def tracked_text_files() -> list[Path]:
    out: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if path.name in SKIP_NAMES:
            continue
        if any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts):
            continue
        out.append(path)
    return out


FILES = tracked_text_files()


def test_there_are_files_to_check() -> None:
    """An empty denominator is not a pass here either."""
    assert len(FILES) > 20


@pytest.mark.parametrize("path", FILES, ids=[str(p.relative_to(ROOT)) for p in FILES])
def test_no_em_or_en_dashes(path: Path) -> None:
    """House style, checked rather than trusted."""
    forbidden = {
        "\u2013": "en dash",
        "\u2014": "em dash",
        "\u2012": "figure dash",
        "\u2015": "horizontal bar",
    }
    text = path.read_text(encoding="utf-8")
    hits = [name for char, name in forbidden.items() if char in text]
    assert not hits, f"{path.relative_to(ROOT)} contains {', '.join(hits)}"


def test_the_dash_script_agrees(tmp_path: Path) -> None:
    """The pre-commit hook and this test must not disagree."""
    offender = tmp_path / "bad.md"
    offender.write_text("a \u2014 b\n")
    clean = tmp_path / "good.md"
    clean.write_text("a and b\n")

    script = ROOT / "scripts" / "check_no_dashes.py"
    bad = subprocess.run(
        [sys.executable, str(script), str(offender)], capture_output=True, text=True, check=False
    )
    good = subprocess.run(
        [sys.executable, str(script), str(clean)], capture_output=True, text=True, check=False
    )
    assert bad.returncode == 1
    assert "em dash" in bad.stdout
    assert good.returncode == 0


class TestNoOverclaiming:
    """Copy this project will not carry.

    Adoption language on a project with no users, and any wording that implies
    a blessing from the regulator, are both easy to write by accident.
    """

    BANNED = (
        r"\btrusted by\b",
        r"\bused by \d",
        r"\bthousands of\b",
        r"\bmillions of\b",
        r"\bdownloads?\b",
        r"\bin production at\b",
        r"\bofficially (?:approved|endorsed|certified)\b",
        r"\bendorsed by the (?:California )?Energy Commission\b",
        r"\bapproved by the (?:California )?Energy Commission\b",
        r"\bin partnership with the (?:California )?Energy Commission\b",
    )

    @pytest.mark.parametrize("pattern", BANNED)
    def test_readme_avoids_overclaiming(self, pattern: str) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        assert not re.search(pattern, readme, re.IGNORECASE), pattern

    def test_readme_disclaims_affiliation(self) -> None:
        readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
        assert (
            "not affiliated with, endorsed by, or approved by the California Energy "
            "Commission or any utility" in readme
        )

    def test_readme_disclaims_judgment(self) -> None:
        readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
        assert "makes no judgment about a supplier's power mix" in readme
        assert "does not rank suppliers" in readme

    def test_readme_rules_out_ranking_explicitly(self) -> None:
        readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
        assert "produces no leaderboard" in readme
        assert "Structural conformance only" in readme


class TestWorkflowHardening:
    """Cheap structural facts about CI, checked here so a local run catches them."""

    def workflows(self) -> list[Path]:
        return sorted((ROOT / ".github" / "workflows").glob("*.yml"))

    def test_there_are_workflows(self) -> None:
        assert self.workflows()

    def test_every_action_is_pinned_to_a_commit_sha(self) -> None:
        pattern = re.compile(r"^\s*-?\s*uses:\s*([^\s@]+)@(\S+)", re.MULTILINE)
        for workflow in self.workflows():
            for name, ref in pattern.findall(workflow.read_text(encoding="utf-8")):
                if name.startswith("./"):
                    continue
                assert re.fullmatch(r"[0-9a-f]{40}", ref), f"{workflow.name}: {name}@{ref}"

    def test_every_pinned_action_carries_a_version_comment(self) -> None:
        pattern = re.compile(r"^\s*-?\s*uses:\s*[^\s@]+@[0-9a-f]{40}\s*#\s*\S+", re.MULTILINE)
        bare = re.compile(r"^\s*-?\s*uses:\s*[^\s@./]+/[^\s@]+@[0-9a-f]{40}\s*$", re.MULTILINE)
        for workflow in self.workflows():
            text = workflow.read_text(encoding="utf-8")
            assert not bare.search(text), f"{workflow.name} has an unlabelled pin"
            assert pattern.search(text), f"{workflow.name} has no labelled pin"

    def test_every_workflow_declares_top_level_permissions(self) -> None:
        for workflow in self.workflows():
            text = workflow.read_text(encoding="utf-8")
            assert re.search(r"^permissions:", text, re.MULTILINE), workflow.name

    def test_no_security_gate_is_silenced(self) -> None:
        tokens = ("pip-audit", "gitleaks", "semgrep", "bandit", "trivy", "grype", "codeql")
        for workflow in self.workflows():
            for line in workflow.read_text(encoding="utf-8").splitlines():
                low = line.lower()
                muted = "|| true" in low or "continue-on-error: true" in low
                assert not (muted and any(t in low for t in tokens)), f"{workflow.name}: {line}"

    def test_dependencies_are_installed_from_the_lockfile(self) -> None:
        for workflow in self.workflows():
            text = workflow.read_text(encoding="utf-8")
            assert "uv sync --frozen" not in text, f"{workflow.name} uses --frozen"


SOURCE_FILES = [
    p
    for p in sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "scripts").rglob("*.py"))
    if "__pycache__" not in p.parts
]


class TestDigitClasses:
    r"""Digit classes are written ``[0-9]``, never ``\d``.

    Python's ``\d`` matches every Unicode decimal digit, 680 characters
    against ASCII's ten, and ``float`` and ``Decimal`` convert all of them.
    A pattern that matches wider than the code deriving a value from it means
    the tool reports a number it did not read. Enforced here rather than
    remembered, because the failure is invisible on every input anyone tries.
    """

    def test_there_are_source_files_to_check(self) -> None:
        assert len(SOURCE_FILES) > 10

    @pytest.mark.parametrize(
        "path", SOURCE_FILES, ids=[str(p.relative_to(ROOT)) for p in SOURCE_FILES]
    )
    def test_no_unicode_digit_class(self, path: Path) -> None:
        hits = [
            f"line {number}"
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
            if "\\" + "d" in line
        ]
        assert not hits, f"{path.relative_to(ROOT)} writes a digit class as \\d at {hits}"

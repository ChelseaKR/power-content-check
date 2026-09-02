"""Rules about the repository itself, enforced rather than remembered."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

TEXT_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".txt", ".cff"}

#: Files with no suffix at all that are still prose these rules cover.
#:
#: Selecting on suffix alone silently excluded the Makefile, which is where
#: the gate itself is written, and CODEOWNERS. A scan that never opens the
#: file holding the gate is exactly the shape this repository worries about,
#: so the extensionless files are named rather than left to a glob that cannot
#: see them.
TEXT_NAMES = {"Makefile", "CODEOWNERS"}

SKIP_PARTS = {".git", ".venv", "__pycache__", "htmlcov", "examples", ".ruff_cache"}
SKIP_NAMES = {"LICENSE", "uv.lock"}

MAKEFILE = ROOT / "Makefile"

#: Every way a step can be made unable to fail. A leading ``-`` on a make
#: recipe line is make's own ignore-errors prefix, and mutes as completely as
#: ``|| true`` does.
MUTING_PATTERNS = (
    r"\|\|\s*true\b",
    r"\|\|\s*:",
    r"\|\|\s*exit\s+0\b",
    r"continue-on-error:\s*true",
    r"^\s*if:\s*false\s*$",
)

SECURITY_TOOLS = ("pip-audit", "gitleaks", "semgrep", "bandit", "trivy", "grype", "codeql")


def tracked_text_files() -> list[Path]:
    out: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
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


def test_the_extensionless_files_are_in_scope() -> None:
    """The scan opens the Makefile, not only what a suffix glob finds.

    Its own assertion because the omission was invisible: every dash test
    passed, over a set that silently excluded the file the gate lives in.
    """
    names = {path.name for path in FILES}
    for wanted in sorted(TEXT_NAMES):
        assert wanted in names, f"{wanted} is not in the scanned set"


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
        """Both YAML spellings. GitHub reads either, so a rule that reads one
        of them can be stepped around by renaming a file."""
        directory = ROOT / ".github" / "workflows"
        return sorted(set(directory.glob("*.yml")) | set(directory.glob("*.yaml")))

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

    def _security_workflows(self) -> list[Path]:
        return [
            workflow
            for workflow in self.workflows()
            if any(tool in workflow.read_text(encoding="utf-8").lower() for tool in SECURITY_TOOLS)
        ]

    def test_a_workflow_actually_runs_a_security_tool(self) -> None:
        """The denominator for the two rules below.

        Both of them iterate over the workflows that name a security tool. If
        that set were ever empty, both would pass having examined nothing, and
        deleting the security workflow would read as compliance.
        """
        assert self._security_workflows(), "no workflow names any security tool"

    def test_no_security_gate_is_silenced(self) -> None:
        """The line level floor: a mute written beside the tool it mutes."""
        for workflow in self.workflows():
            for line in workflow.read_text(encoding="utf-8").splitlines():
                low = line.lower()
                muted = any(re.search(pattern, low) for pattern in MUTING_PATTERNS)
                assert not (muted and any(t in low for t in SECURITY_TOOLS)), (
                    f"{workflow.name}: {line}"
                )

    def test_a_workflow_that_runs_a_security_tool_mutes_nothing(self) -> None:
        """The rule the line level one could not reach.

        A step is not silenced on the line that names the tool. It is silenced
        by a key beside it:

            - name: Run pip-audit
              run: uv run pip-audit --strict ...
              continue-on-error: true

        The mute and the tool name are on different lines, so scanning line by
        line cannot see it, and the guard could not fail in the way a gate is
        actually turned off. A workflow whose job is to run security gates
        does not get to mute anything anywhere in the file, which needs no
        YAML parser to enforce and has no blind spot between two lines.
        """
        for workflow in self._security_workflows():
            text = workflow.read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), start=1):
                for pattern in MUTING_PATTERNS:
                    assert not re.search(pattern, line.lower()), (
                        f"{workflow.name}:{number} mutes a step in a workflow that "
                        f"runs a security gate: {line.strip()}"
                    )

    def test_dependencies_are_installed_from_the_lockfile(self) -> None:
        """Both directions. Forbidding one spelling is not requiring another.

        This asserted only that ``--frozen`` was absent, so a workflow that
        dropped to a bare ``uv sync`` and resolved whatever was newest passed
        it. The positive is the claim that matters.
        """
        installs = re.compile(r"uv sync(?P<flags>[^\n]*)")
        for workflow in self.workflows():
            text = workflow.read_text(encoding="utf-8")
            assert "uv sync --frozen" not in text, f"{workflow.name} uses --frozen"
            for match in installs.finditer(text):
                assert "--locked" in match.group("flags"), (
                    f"{workflow.name} installs without --locked: {match.group(0).strip()}"
                )

    def test_turning_errexit_off_is_always_paired_with_reading_the_code(self) -> None:
        """`set +e` with nothing that reads `$?` is a step that cannot fail.

        CI turns errexit off in one place, deliberately: the self check that
        proves an empty run exits 3 has to run a command expected to fail and
        then look at what it returned. That is correct, and it is one deleted
        line away from a step that runs the tool and ignores whatever it says,
        with the workflow still green. The line that reads the code is the
        entire gate, so its presence is asserted rather than assumed.
        """
        for workflow in self.workflows():
            text = workflow.read_text(encoding="utf-8")
            if "set +e" not in text:
                continue
            assert "$?" in text, f"{workflow.name} turns errexit off and never reads an exit code"
            assert re.search(r"\btest\b[^\n]*-eq|\[\s+[^\n]*-eq", text), (
                f"{workflow.name} reads an exit code and never compares it"
            )

    def test_ci_still_proves_an_empty_run_is_not_a_pass(self) -> None:
        """The gate the rule above protects, named so it cannot quietly go.

        `make verify` cannot cover this one: the exit code of the installed
        console script over no arguments is a fact about the shipped
        entry point, and CI is where it is asserted. A rule about how the
        step is written is worth little if the step itself can be deleted.
        """
        joined = "\n".join(w.read_text(encoding="utf-8") for w in self.workflows())
        assert "power-content-check check" in joined, "no workflow runs the empty check"
        assert re.search(r'test\s+"\$code"\s+-eq\s+3', joined), (
            "no workflow asserts that an empty run exits 3"
        )


class TestTheMakefileGate:
    """`make verify` is the gate, and nothing had ever read the Makefile.

    Every rule above reads `.github/workflows`. But CI's own summary of itself
    is `make verify`, the release workflow runs `make verify` at the tagged
    commit before anything is published, and CONTRIBUTING tells a contributor
    it must exit 0 before anything is pushed. A `-` prefix on one recipe line,
    which is make's ignore-errors prefix and mutes as completely as
    `|| true`, would have taken the security scanners out of all three with
    nothing to notice.
    """

    def text(self) -> str:
        return MAKEFILE.read_text(encoding="utf-8")

    def _recipe_lines(self, target: str) -> list[str]:
        """The recipe body of one target, which is its tab indented lines."""
        lines = self.text().splitlines()
        for index, line in enumerate(lines):
            if not line.startswith(f"{target}:"):
                continue
            body: list[str] = []
            for following in lines[index + 1 :]:
                if following.startswith("\t"):
                    body.append(following[1:])
                elif following.strip():
                    break
            return body
        raise AssertionError(f"no target named {target} in the Makefile")

    def test_the_makefile_is_there_and_names_the_scanners(self) -> None:
        """The denominator. A Makefile that stopped running the scanners would
        otherwise satisfy every rule below by having nothing to check."""
        assert MAKEFILE.is_file()
        body = "\n".join(self._recipe_lines("security"))
        assert "bandit" in body, "the security target no longer runs bandit"
        assert "pip-audit" in body, "the security target no longer runs pip-audit"

    def test_verify_depends_on_every_gate(self) -> None:
        match = re.search(r"^verify:(?P<prereqs>[^\n]*)", self.text(), re.MULTILINE)
        assert match, "no verify target"
        prerequisites = match.group("prereqs").split()
        for gate in ("lint", "typecheck", "test", "security"):
            assert gate in prerequisites, f"verify does not depend on {gate}"

    def test_no_recipe_line_ignores_a_failure(self) -> None:
        """Every muting construct, over every recipe line in the file.

        Not scoped to the security target: a `-` prefix on the test or lint
        line takes the same gate off, and scoping the rule to the target whose
        name says "security" is how a rule stops covering the thing it is for.
        """
        for number, line in enumerate(self.text().splitlines(), start=1):
            if not line.startswith("\t"):
                continue
            recipe = line[1:]
            assert not recipe.startswith("-"), (
                f"Makefile:{number} ignores errors with make's `-` prefix: {recipe.strip()}"
            )
            for pattern in MUTING_PATTERNS:
                assert not re.search(pattern, recipe), (
                    f"Makefile:{number} swallows a failure: {recipe.strip()}"
                )


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

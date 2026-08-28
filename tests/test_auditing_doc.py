"""The auditor's entry point must agree with the tool it describes.

`docs/AUDITING.md` tells someone who does not trust this tool how to check
it. A statement in it that the tool does not honour is worse than no
document, because an auditor following it looks for values the reports never
contain and concludes the tool is broken, or worse, concludes it is fine.

An earlier attempt at this document listed five result statuses where the
model defines three, which is exactly the failure these tests exist to make
impossible to repeat. So the factual claims are pinned here rather than
proofread: the status set, the blocker set, the basis set, the exit codes,
the catalog's key set, every check identifier named, every link, and every
repository path quoted.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from power_content_check.checks import CHECKS
from power_content_check.model import Basis, Blocker, ExitCode, Status

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "AUDITING.md"
TEXT = DOC.read_text(encoding="utf-8")


def test_the_document_exists_and_is_not_empty() -> None:
    """An empty denominator is not a pass here either."""
    assert len(TEXT) > 2000


class TestTheEnumerationsMatch:
    """Every set the document prints is the set the model defines.

    Printed as the exact repr of the sorted values, so the document cannot
    drift by one member without this failing.
    """

    def test_the_status_set(self) -> None:
        assert repr(sorted(s.value for s in Status)) in TEXT

    def test_no_invented_status_is_named(self) -> None:
        invented = {"pass", "deviation", "error", "fail", "warning", "skipped"}
        quoted = set(re.findall(r"`([a-z_]+)`", TEXT))
        assert not (quoted & invented), f"names a status the tool never emits: {quoted & invented}"

    def test_the_blocker_set(self) -> None:
        assert repr(sorted(b.value for b in Blocker)) in TEXT

    def test_the_basis_set(self) -> None:
        assert repr(sorted(b.value for b in Basis)) in TEXT

    def test_the_catalog_key_set(self) -> None:
        keys = sorted(CHECKS[0].spec.to_dict())
        assert repr(keys) in TEXT

    @pytest.mark.parametrize(
        "code",
        [ExitCode.OK, ExitCode.NONCONFORMANCE, ExitCode.NOT_EVALUATED, ExitCode.NOTHING_CHECKED],
    )
    def test_every_exit_code_is_listed_in_its_table(self, code: int) -> None:
        assert re.search(rf"^\| {code} \| ", TEXT, re.MULTILINE), f"exit code {code} not tabulated"

    def test_the_counts_of_registered_and_unimplemented_checks(self) -> None:
        unimplemented = [c for c in CHECKS if not c.spec.implemented]
        assert len(CHECKS) == 35 and len(unimplemented) == 17, (
            "the counts moved; docs/AUDITING.md section 6 spells them out in words"
        )
        assert "Seventeen of the thirty five registered checks" in TEXT


class TestEveryReferenceResolves:
    def _links(self) -> list[str]:
        return [
            target
            for target in re.findall(r"\]\(([^)#]+)\)", TEXT)
            if not target.startswith(("http://", "https://"))
        ]

    def test_there_are_links_to_check(self) -> None:
        assert len(self._links()) > 5

    def test_every_relative_link_resolves(self) -> None:
        missing = [t for t in self._links() if not (DOC.parent / t).exists()]
        assert not missing, f"dangling links: {missing}"

    def test_every_check_identifier_named_is_registered(self) -> None:
        known = {c.spec.id for c in CHECKS}
        named = set(re.findall(r"\bPCL[0-9]{3}\b", TEXT))
        assert named, "the document names no check at all"
        assert named <= known, f"names checks that do not exist: {sorted(named - known)}"

    def test_every_repository_path_quoted_exists(self) -> None:
        paths = set(re.findall(r"`((?:tests|src|scripts|docs)/[A-Za-z0-9_./-]+)`", TEXT))
        assert paths, "the document quotes no repository path"
        missing = sorted(p for p in paths if not (ROOT / p).exists())
        assert not missing, f"quoted paths that do not exist: {missing}"


class TestTheCommandsRun:
    """The shell in the document is executed, not proofread.

    Every command here is quoted in `docs/AUDITING.md`. A command that no
    longer works is a broken instruction to someone who came to verify the
    tool and has no other route in.
    """

    def _cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "power_content_check", *args],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )

    def test_the_catalog_command_runs(self) -> None:
        assert "power-content-check catalog\n" in TEXT
        assert self._cli("catalog").returncode == 0

    def test_the_status_settling_command_reports_the_three_statuses(self) -> None:
        assert "tests/fixtures/deficient_label.txt --json" in TEXT
        result = self._cli("check", "tests/fixtures/deficient_label.txt", "--json")
        report = json.loads(result.stdout)
        seen = sorted({r["status"] for r in report["documents"][0]["results"]})
        assert seen == sorted(s.value for s in Status)

    def test_the_fingerprint_flag_exists(self) -> None:
        assert "--fingerprint" in TEXT
        result = self._cli("check", "tests/fixtures/conforming_label.txt", "--fingerprint")
        assert "fingerprint: " in result.stdout

    def test_the_catalog_json_shape_the_recipes_index_into(self) -> None:
        entries = json.loads(self._cli("catalog", "--json").stdout)
        one = entries[0]
        # The two recipes in the document index into these keys by name.
        assert {"id", "implemented", "blocker", "unimplemented_reason"} <= set(one)
        assert {"locator", "source_url", "quote"} <= set(one["citation"])

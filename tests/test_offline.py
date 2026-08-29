"""The offline claim, read off the source rather than trusted.

The README's fourth paragraph of usage says it plainly:

    The tool is offline. It opens the files you name and nothing else. No
    network call, no telemetry, no account, no configuration file, no cache.

`src/power_content_check/cli.py` repeats it in its module docstring. Nothing
checked it. A single `import urllib.request` inside a check, or a
`subprocess.run` that shelled out to something that did, would have gone in
under every gate this repository has, because none of them read the package's
imports.

This is deliberately a claim about this package's own source, not about the
whole process. `pypdf` is a dependency and this cannot speak for it, and the
docstring says so rather than letting the test imply a bigger claim than it
makes. That is the same register the tool itself uses when it reports an
absence from extracted text rather than an absence from the document.

Function-local imports count. This codebase uses them heavily, so a rule that
read only module-level imports would miss the place a network call would most
plausibly be written.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "power_content_check"

#: Module roots that would make the offline claim untrue.
#:
#: The network modules are the claim itself. The process-spawning ones are
#: here because they are the way around it: a package that shells out can
#: reach the network without importing a socket, and the claim a reader takes
#: from the README is about the tool's behaviour, not about its import list.
FORBIDDEN_ROOTS = frozenset(
    {
        "aiohttp",
        "asyncio",
        "ftplib",
        "http",
        "httpx",
        "imaplib",
        "multiprocessing",
        "nntplib",
        "poplib",
        "requests",
        "smtplib",
        "socket",
        "socketserver",
        "ssl",
        "subprocess",
        "telnetlib",
        "urllib",
        "urllib3",
        "webbrowser",
        "xmlrpc",
    }
)

#: Callables that reach out or spawn without an import this rule would see.
FORBIDDEN_CALLS = ("os.system", "os.popen", "os.execv", "os.spawnl", "os.fork")


def _sources() -> list[Path]:
    return sorted(path for path in PACKAGE.rglob("*.py") if "__pycache__" not in path.parts)


SOURCES = _sources()


def _roots(tree: ast.AST) -> set[str]:
    """Every module root imported anywhere in the file, nested imports included."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # A relative import has no module root outside this package.
            if node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found


def test_there_is_source_to_read() -> None:
    """The denominator. A glob that found nothing would pass every rule below.

    The package is eight modules and a dunder pair. If this ever drops to
    zero, the rest of this file is asserting things about an empty set.
    """
    assert len(SOURCES) >= 8, f"only {len(SOURCES)} source files found under {PACKAGE}"
    assert (PACKAGE / "cli.py") in SOURCES
    assert (PACKAGE / "checks.py") in SOURCES


@pytest.mark.parametrize("path", SOURCES, ids=[p.name for p in SOURCES])
def test_no_module_imports_anything_that_could_reach_the_network(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offending = sorted(_roots(tree) & FORBIDDEN_ROOTS)
    assert not offending, (
        f"{path.relative_to(ROOT)} imports {', '.join(offending)}, and the README "
        "says this tool makes no network call"
    )


@pytest.mark.parametrize("path", SOURCES, ids=[p.name for p in SOURCES])
def test_no_module_shells_out(path: Path) -> None:
    """The escape hatch that needs no forbidden import."""
    source = path.read_text(encoding="utf-8")
    for call in FORBIDDEN_CALLS:
        assert call not in source, f"{path.relative_to(ROOT)} calls {call}"


def test_the_rule_can_see_a_nested_import() -> None:
    """The rule's own positive control.

    Written against a constructed module rather than a real one, because the
    thing being proved is that the walker descends into a function body. This
    package writes most of its imports inside functions, so a rule that only
    read the top of the file would pass on every source in it while missing
    the one place a network call would actually be written.
    """
    nested = ast.parse(
        "def check(doc, ctx):\n"
        "    import urllib.request\n"
        "    return urllib.request.urlopen('https://example.invalid')\n"
    )
    assert _roots(nested) & FORBIDDEN_ROOTS == {"urllib"}

    from_form = ast.parse("def check():\n    from socket import create_connection\n")
    assert _roots(from_form) & FORBIDDEN_ROOTS == {"socket"}


def test_the_rule_does_not_fire_on_the_imports_the_package_uses() -> None:
    """The other positive control: it is not simply refusing everything."""
    ordinary = ast.parse("import hashlib\nimport json\nimport re\nimport pypdf\n")
    assert not _roots(ordinary) & FORBIDDEN_ROOTS


def test_the_readme_still_makes_the_claim_this_file_enforces() -> None:
    """If the claim is ever withdrawn, this file should be reconsidered, not
    left enforcing a promise the project no longer makes."""
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
    assert "The tool is offline." in readme
    assert "No network call, no telemetry" in readme

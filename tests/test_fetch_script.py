"""The refusals the fetch script promises, held rather than remembered.

`scripts/fetch_examples.py` is the one thing in this repository that touches
the network, and the README makes three claims about it: that it "honours
robots.txt, rate limits itself, and refuses to fetch in bulk". CONTRIBUTING
lists bulk fetching among the things this project will not accept. Nothing
enforced any of it, so the cap could have been raised, the robots.txt call
deleted, or the pause dropped, and every gate in the repository would have
stayed green. An invariant stated in the README and enforced nowhere is a
wish, which is the argument `tests/test_properties.py` already makes about
the ADRs.

Every test here is offline. The script's own `urlopen` is replaced, and the
replacement records what it was asked for, so a test that accidentally
depended on the network would fail rather than reach out. `_never_opens`
makes that an assertion rather than a hope.
"""

from __future__ import annotations

import importlib.util
import urllib.error
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "fetch_examples.py"

EXAMPLE = "https://labels.example.invalid/one.pdf"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fetch_examples_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


@pytest.fixture
def script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """The script with its cache redirected and its clock stilled."""
    module = _load()
    monkeypatch.setattr(module, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    return module


def _never_opens(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    """Any network call at all fails the test that installed this."""

    def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("the script reached the network")

    monkeypatch.setattr(module.urllib.request, "urlopen", refuse)


def _serving(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, robots: bytes, body: bytes = b"%PDF-1.7\n"
) -> list[str]:
    """Serve a robots.txt and a document, recording every URL requested."""
    asked: list[str] = []

    def fake(request: Any, timeout: float | None = None) -> _Response:
        url = request.full_url
        asked.append(url)
        return _Response(robots if url.endswith("/robots.txt") else body)

    monkeypatch.setattr(module.urllib.request, "urlopen", fake)
    return asked


class TestItRefusesToFetchInBulk:
    def test_the_cap_is_a_real_cap(
        self,
        script: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """One more than the cap is refused, without a single request made."""
        _never_opens(script, monkeypatch)
        urls = [f"https://labels.example.invalid/{n}.pdf" for n in range(script.MAX_DOCUMENTS + 1)]
        assert script.main(urls) == 2
        assert "Refusing to fetch" in capsys.readouterr().out

    def test_the_cap_is_not_so_high_that_it_is_not_a_cap(self, script: ModuleType) -> None:
        """A handful of examples, not a corpus, is a claim about a number.

        Ninety one 2024 labels are published. A cap above that would refuse
        nothing anyone would actually try, and the script would be describing
        a limit it does not impose.
        """
        assert 0 < script.MAX_DOCUMENTS <= 10

    def test_the_boundary_itself_is_allowed(
        self,
        script: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The positive control on the cap: exactly the cap is not refused.

        Without this the cap could be set to zero and the refusal test above
        would still pass, which is a gate that only ever says no.
        """
        asked = _serving(script, monkeypatch, robots=b"User-agent: *\nAllow: /\n")
        urls = [f"https://labels.example.invalid/{n}.pdf" for n in range(script.MAX_DOCUMENTS)]
        assert script.main(urls) == 0
        assert "Refusing to fetch" not in capsys.readouterr().out
        assert len([url for url in asked if url == urls[0]]) == 1

    def test_it_pauses_between_requests(
        self,
        script: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Rate limiting, counted. The pause is between, so two URLs pause once."""
        slept: list[float] = []
        monkeypatch.setattr(script.time, "sleep", lambda seconds: slept.append(seconds))
        _serving(script, monkeypatch, robots=b"User-agent: *\nAllow: /\n")
        assert script.main([EXAMPLE, "https://labels.example.invalid/two.pdf"]) == 0
        capsys.readouterr()
        assert slept == [script.PAUSE_SECONDS]
        assert script.PAUSE_SECONDS > 0


class TestItHonoursRobots:
    def test_a_disallowed_url_is_not_fetched(
        self,
        script: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        asked = _serving(script, monkeypatch, robots=b"User-agent: *\nDisallow: /\n")
        assert script.main([EXAMPLE]) == 1
        assert "robots.txt disallows" in capsys.readouterr().out
        assert asked == ["https://labels.example.invalid/robots.txt"]

    def test_an_allowed_url_is_fetched(
        self,
        script: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The positive control. A rule that refuses everything honours nothing."""
        asked = _serving(script, monkeypatch, robots=b"User-agent: *\nAllow: /\n")
        assert script.main([EXAMPLE]) == 0
        capsys.readouterr()
        assert EXAMPLE in asked

    def test_an_unreadable_robots_file_is_treated_as_disallowing(
        self,
        script: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Guessing in the permissive direction is the wrong way to guess.

        This is the fail-closed rule of the rest of the project, applied to
        someone else's server rather than to a document.
        """

        def fake(request: Any, timeout: float | None = None) -> _Response:
            if request.full_url.endswith("/robots.txt"):
                raise OSError("connection reset")
            raise AssertionError("fetched despite an unreadable robots.txt")

        monkeypatch.setattr(script.urllib.request, "urlopen", fake)
        assert script.main([EXAMPLE]) == 1
        assert "treating as disallowed" in capsys.readouterr().out

    def test_a_missing_robots_file_permits(
        self,
        script: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """404 is the one failure that means permission, and only 404."""
        seen: list[str] = []

        def fake(request: Any, timeout: float | None = None) -> _Response:
            url = request.full_url
            seen.append(url)
            if url.endswith("/robots.txt"):
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)  # type: ignore[arg-type]
            return _Response(b"%PDF-1.7\n")

        monkeypatch.setattr(script.urllib.request, "urlopen", fake)
        assert script.main([EXAMPLE]) == 0
        capsys.readouterr()
        assert EXAMPLE in seen

    def test_a_server_error_on_robots_is_not_permission(
        self,
        script: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The boundary beside the 404 branch, so it cannot widen unnoticed."""

        def fake(request: Any, timeout: float | None = None) -> _Response:
            url = request.full_url
            if url.endswith("/robots.txt"):
                raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)  # type: ignore[arg-type]
            raise AssertionError("fetched despite a 503 on robots.txt")

        monkeypatch.setattr(script.urllib.request, "urlopen", fake)
        assert script.main([EXAMPLE]) == 1
        assert "treating as disallowed" in capsys.readouterr().out


class TestItOnlyFetchesOverHttps:
    def test_a_plain_http_url_is_skipped_without_a_request(
        self,
        script: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _never_opens(script, monkeypatch)
        assert script.main(["http://labels.example.invalid/one.pdf"]) == 1
        assert "only https URLs are fetched" in capsys.readouterr().out

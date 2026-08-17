#!/usr/bin/env python3
"""Cache a small number of published Power Content Labels locally.

Not part of the package and never invoked by the CLI, which is offline. This
exists so that the checker can be exercised against real documents without this
repository redistributing anyone's published label.

Deliberate limits:

* A hard cap on how many documents one invocation will fetch. Bulk collection
  is not a supported use of this script and raising the cap is not a supported
  workaround.
* robots.txt is fetched and honoured for every host, and a disallowed URL is
  skipped with a message rather than fetched anyway.
* A pause between requests.
* Files land in a directory that .gitignore excludes.

Usage:

    python3 scripts/fetch_examples.py <url> [<url> ...]
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "examples" / "cache"
USER_AGENT = (
    "power-content-check-example-fetcher/0.1 (+https://github.com/ChelseaKR/power-content-check)"
)
MAX_DOCUMENTS = 5
PAUSE_SECONDS = 2.0
TIMEOUT_SECONDS = 30


def robots_allows(url: str) -> bool:
    """True when the host's robots.txt permits this fetcher to read the URL.

    A host with no robots.txt is treated as permitting. A host whose robots.txt
    cannot be read at all is treated as forbidding, because guessing in the
    permissive direction is the wrong way to guess.
    """
    parts = urllib.parse.urlsplit(url)
    robots_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
    parser = urllib.robotparser.RobotFileParser()
    request = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return True
        print(f"  robots.txt at {robots_url} returned HTTP {exc.code}; treating as disallowed")
        return False
    except OSError as exc:
        print(f"  robots.txt at {robots_url} could not be read ({exc}); treating as disallowed")
        return False
    parser.parse(body.splitlines())
    return parser.can_fetch(USER_AGENT, url)


def target_path(url: str, index: int) -> Path:
    parts = urllib.parse.urlsplit(url)
    stem = Path(parts.path).name or f"label-{index:02d}"
    if not stem.lower().endswith((".pdf", ".txt")):
        stem = f"{stem or 'label'}-{index:02d}.pdf"
    return CACHE / stem


def fetch(url: str, destination: Path) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = response.read()
    except OSError as exc:
        print(f"  fetch failed: {exc}")
        return False
    destination.write_bytes(payload)
    print(f"  saved {len(payload)} bytes to {destination}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("urls", nargs="+", help="URLs of published labels to cache")
    args = parser.parse_args(argv)

    if len(args.urls) > MAX_DOCUMENTS:
        print(
            f"Refusing to fetch {len(args.urls)} documents. The cap is {MAX_DOCUMENTS} "
            "per invocation. This script is for a handful of examples, not for "
            "collecting a corpus."
        )
        return 2

    CACHE.mkdir(parents=True, exist_ok=True)
    failures = 0
    for index, url in enumerate(args.urls, start=1):
        print(f"[{index}/{len(args.urls)}] {url}")
        if not url.lower().startswith("https://"):
            print("  skipped: only https URLs are fetched")
            failures += 1
            continue
        if not robots_allows(url):
            print("  skipped: robots.txt disallows this URL for this fetcher")
            failures += 1
            continue
        if not fetch(url, target_path(url, index)):
            failures += 1
        if index < len(args.urls):
            time.sleep(PAUSE_SECONDS)

    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

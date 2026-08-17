"""Reading a label off disk.

This module is where the tool decides whether it can see a document at all.
That decision is the whole safety property, so it is made in one place and it
is made pessimistically: anything that is not a clean read of real text is
UNREADABLE, and an unreadable document never reaches a check.

The failure this guards against is a document the tool could not read being
reported as clean. Silence from an extractor is not evidence of conformance.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pypdf

from .normalize import normalize, normalize_lines

#: A PDF whose text layer yields fewer than this many characters is treated as
#: unreadable rather than as a label with very little on it.
#:
#: This is an engineering threshold chosen by this project. It is NOT a
#: regulatory quantity and no check cites it. A scanned or image-only label
#: typically extracts to zero characters; a real single-portfolio label
#: extracts to well over a thousand. The gap between those is wide, so the
#: exact value is not load bearing, but it is configurable so that a caller who
#: disagrees is not stuck with it.
DEFAULT_MIN_TEXT_CHARS = 200

SUPPORTED_SUFFIXES = (".pdf", ".txt")


@dataclass(frozen=True)
class LabelDocument:
    """A document the tool was able to read.

    An instance of this class existing is the proof that extraction succeeded.
    Checks take one of these, so a check cannot be run against a document that
    was never read.
    """

    path: Path
    sha256: str
    page_count: int | None
    raw_text: str
    normalized: str
    normalized_lines: list[str]


@dataclass(frozen=True)
class UnreadableDocument:
    """A document the tool could not read, and why."""

    path: Path
    sha256: str | None
    reason: str


ExtractResult = LabelDocument | UnreadableDocument


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build(path: Path, digest: str, page_count: int | None, text: str) -> LabelDocument:
    return LabelDocument(
        path=path,
        sha256=digest,
        page_count=page_count,
        raw_text=text,
        normalized=normalize(text),
        normalized_lines=normalize_lines(text),
    )


def _open_pdf(path: Path, digest: str) -> pypdf.PdfReader | UnreadableDocument:
    """Open a PDF, or say why it will not open.

    Encryption gets its own branch because pypdf hands back an empty string for
    an encrypted file rather than refusing, and an empty string is exactly the
    shape of a document with nothing wrong with it.
    """
    try:
        reader = pypdf.PdfReader(path)
    except Exception as exc:
        return UnreadableDocument(
            path, digest, f"the PDF could not be parsed: {type(exc).__name__}"
        )

    if getattr(reader, "is_encrypted", False):
        try:
            opened = reader.decrypt("") != 0
        except Exception:
            opened = False
        if not opened:
            return UnreadableDocument(path, digest, "the PDF is encrypted")
    return reader


def _pdf_text(
    reader: pypdf.PdfReader, path: Path, digest: str
) -> tuple[str, int] | UnreadableDocument:
    try:
        pages = list(reader.pages)
    except Exception as exc:
        return UnreadableDocument(
            path, digest, f"the PDF page tree could not be read: {type(exc).__name__}"
        )

    if not pages:
        return UnreadableDocument(path, digest, "the PDF contains no pages")

    chunks: list[str] = []
    for index, page in enumerate(pages):
        try:
            chunks.append(page.extract_text() or "")
        except Exception as exc:
            return UnreadableDocument(
                path,
                digest,
                f"text extraction failed on page {index + 1}: {type(exc).__name__}",
            )
    return "\n".join(chunks), len(pages)


def _extract_pdf(path: Path, data: bytes, digest: str, min_chars: int) -> ExtractResult:
    reader = _open_pdf(path, digest)
    if isinstance(reader, UnreadableDocument):
        return reader

    extracted = _pdf_text(reader, path, digest)
    if isinstance(extracted, UnreadableDocument):
        return extracted

    text, page_count = extracted
    if len(text.strip()) < min_chars:
        return UnreadableDocument(
            path,
            digest,
            (
                f"the PDF yielded {len(text.strip())} characters of text, below the "
                f"{min_chars} character minimum; it is most likely a scan or an image "
                "with no text layer"
            ),
        )
    return _build(path, digest, page_count, text)


def _extract_text(path: Path, data: bytes, digest: str, min_chars: int) -> ExtractResult:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("latin-1")
        except Exception:
            return UnreadableDocument(path, digest, "the file is not decodable as text")

    if len(text.strip()) < min_chars:
        return UnreadableDocument(
            path,
            digest,
            (
                f"the file yielded {len(text.strip())} characters of text, below the "
                f"{min_chars} character minimum"
            ),
        )
    return _build(path, digest, None, text)


def extract(path: Path, min_chars: int = DEFAULT_MIN_TEXT_CHARS) -> ExtractResult:
    """Read one document, or explain why it could not be read.

    This function never raises for a bad input. Every failure mode returns an
    :class:`UnreadableDocument`, because a traceback that a caller catches
    loosely is one refactor away from becoming a silent pass.
    """
    if not path.exists():
        return UnreadableDocument(path, None, "the file does not exist")
    if path.is_dir():
        return UnreadableDocument(path, None, "the path is a directory, not a file")

    try:
        data = path.read_bytes()
    except OSError as exc:
        return UnreadableDocument(path, None, f"the file could not be opened: {exc.strerror}")

    digest = _sha256(data)

    if not data:
        return UnreadableDocument(path, digest, "the file is empty")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path, data, digest, min_chars)
    if suffix == ".txt":
        return _extract_text(path, data, digest, min_chars)
    return UnreadableDocument(
        path,
        digest,
        (
            f"'{suffix or path.name}' is not a supported label format; "
            f"supported formats are {', '.join(SUPPORTED_SUFFIXES)}"
        ),
    )


def discover(paths: list[Path]) -> list[Path]:
    """Expand the paths given on the command line into documents to check.

    A directory contributes its supported files, sorted. A file contributes
    itself whatever its suffix, so that an unsupported file named explicitly is
    reported as unreadable rather than quietly dropped from the denominator.
    """
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_SUFFIXES:
                    found.append(child)
        else:
            found.append(path)

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in found:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique

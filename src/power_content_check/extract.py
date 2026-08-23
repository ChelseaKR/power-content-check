"""Reading a label off disk.

This module is where the tool decides whether it can see a document at all.
That decision is the whole safety property, so it is made in one place and it
is made pessimistically: anything that is not a clean read of real text is
UNREADABLE, and an unreadable document never reaches a check.

The failure this guards against is a document the tool could not read being
reported as clean. Silence from an extractor is not evidence of conformance.

A second, quieter version of the same failure is a document the tool could
only partly read. Extraction reads a text layer; a PDF can also draw text as a
picture, and a picture is invisible here. Every finding this tool reports is
therefore a statement about extracted text, and this module measures what else
the document is carrying so that the limit travels with the finding. See
:func:`count_images`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pypdf

from .geometry import document_cells
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

#: How far to follow Form XObjects when counting the images a page declares.
#: A page nested deeper than this is pathological, and the count stops rather
#: than descending forever.
MAX_FORM_DEPTH = 4

#: Appended to every deviation this tool reports, so that the basis on which it
#: looked is attached to the finding rather than left in the documentation.
TEXT_INPUT_BASIS = (
    "Basis: the characters in this plain text file. If the file was produced "
    "from another document, anything that document drew as a picture is not here."
)

IMAGES_UNCOUNTABLE_BASIS = (
    "Basis: the text layer of this PDF. Its image resources could not be "
    "enumerated, so text that is present only as a picture cannot be ruled out."
)

#: Operators that paint a path. Each occurrence is one thing drawn: a filled
#: wedge, a stroked rule, a shape. Construction operators (``m``, ``l``, ``re``
#: and kin) are not counted, because constructing without painting draws
#: nothing. See ADR 0012.
_PATH_PAINT_OPERATORS = frozenset({b"f", b"F", b"f*", b"S", b"s", b"B", b"B*", b"b", b"b*"})


def _paint_clause(paint_count: int | None) -> str:
    if paint_count is None:
        return "though its painted shapes could not be enumerated"
    if paint_count == 0:
        return "and paints no vector shape"
    noun = "shape" if paint_count == 1 else "shapes"
    return f"and paints {paint_count} vector {noun}"


def _pdf_basis(image_count: int, paint_count: int | None) -> str:
    noun = "image" if image_count == 1 else "images"
    shapes = _paint_clause(paint_count)
    if image_count == 0 and paint_count == 0:
        return (
            "Basis: the text layer of this PDF, which declares no image and "
            "paints no vector shape. A picture is not an available explanation "
            "for text this tool did not find."
        )
    if image_count == 0:
        return (
            "Basis: the text layer of this PDF, which declares no image "
            f"{shapes}. Text that is drawn as a filled or stroked outline is "
            "not read."
        )
    return (
        f"Basis: the text layer of this PDF, which also embeds {image_count} "
        f"{noun} {shapes}. Text that is drawn inside a picture or as a vector "
        "outline is not read."
    )


def _resolve_form(
    operands: Any,
    resources: Any,
) -> tuple[Any, Any, tuple[int, int] | None] | None:
    """The stream and resources behind a ``Do`` of a Form XObject, or None.

    A ``Do`` that names anything but a form draws nothing this counter is
    measuring: images are counted separately by :func:`count_images`.
    """
    xobjects = resources.get("/XObject") if resources is not None else None
    if xobjects is None:
        return None
    try:
        named = xobjects.get_object().get(operands[0])
        if named is None:
            return None
        obj = named.get_object()
    except Exception:
        return None
    if obj.get("/Subtype") != "/Form":
        return None
    key = getattr(named, "idnum", None)
    marker = (int(key), int(named.generation)) if key is not None else None
    return obj, obj.get("/Resources"), marker


def _paints_in(
    stream_object: Any,
    resources: Any,
    pdf: Any,
    seen: set[tuple[int, int]],
    depth: int,
) -> int | None:
    """Count path-painting operators in one content stream, forms included."""
    from pypdf.generic import ContentStream

    if depth > MAX_FORM_DEPTH:
        return 0
    try:
        operations = ContentStream(stream_object, pdf).operations
    except Exception:
        return None

    total = 0
    for operands, operator in operations:
        if operator in _PATH_PAINT_OPERATORS:
            total += 1
            continue
        if operator != b"Do":
            continue
        resolved = _resolve_form(operands, resources)
        if resolved is None:
            continue
        obj, form_resources, marker = resolved
        if marker is not None:
            if marker in seen:
                continue
            seen.add(marker)
        paints = _paints_in(obj, form_resources, pdf, seen, depth + 1)
        if paints is None:
            return None
        total += paints
    return total


def count_vector_paints(pages: list[Any]) -> int | None:
    """How many times the pages paint a vector path, or ``None`` if unknown.

    The companion to :func:`count_images`: images are what the page declares,
    painted paths are what the page does. Between them they cover the two ways
    a label can carry something its text layer lacks. What is not counted:
    inline images (as with ``count_images``) and shading patterns. See ADR
    0012 for why the sentence carries a number rather than a threshold.
    """
    try:
        total = 0
        for page in pages:
            contents = page.get("/Contents")
            if contents is None:
                continue
            paints = _paints_in(contents.get_object(), page.get("/Resources"), page.pdf, set(), 0)
            if paints is None:
                return None
            total += paints
        return total
    except Exception:
        # Never fatal, exactly like an uncountable image set: an unknown count
        # downgrades the claim the tool makes about an absence.
        return None


@dataclass(frozen=True)
class LabelDocument:
    """A document the tool was able to read.

    An instance of this class existing is the proof that extraction succeeded.
    Checks take one of these, so a check cannot be run against a document that
    was never read.

    ``image_count`` and ``extraction_basis`` describe how much of the document
    the tool actually saw. They are not regulatory quantities and no check
    cites them; they qualify what an absence finding is entitled to mean.

    ``cells`` is the same document read column by column instead of line by
    line, and is ``None`` whenever that reading could not be recovered. It is
    not a second opinion about the document's contents. See
    :mod:`power_content_check.geometry` and ADR 0008 for the single narrow
    thing it is allowed to settle.
    """

    path: Path
    sha256: str
    page_count: int | None
    raw_text: str
    normalized: str
    normalized_lines: list[str]
    image_count: int | None
    extraction_basis: str
    #: How many times the pages paint a vector path, or None when that is
    #: unknown or the input is plain text. The companion to ``image_count``:
    #: what the page declares, and what the page does. No check reads either.
    vector_shape_count: int | None = None
    cells: tuple[str, ...] | None = None


@dataclass(frozen=True)
class UnreadableDocument:
    """A document the tool could not read, and why."""

    path: Path
    sha256: str | None
    reason: str


ExtractResult = LabelDocument | UnreadableDocument


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _images_in(resources: Any, seen: set[tuple[int, int]], depth: int) -> int:
    """Count image XObjects reachable from one resource dictionary."""
    if resources is None or depth > MAX_FORM_DEPTH:
        return 0
    xobjects = resources.get_object().get("/XObject")
    if xobjects is None:
        return 0
    count = 0
    for ref in xobjects.get_object().values():
        key = getattr(ref, "idnum", None)
        if key is not None:
            marker = (int(key), int(ref.generation))
            if marker in seen:
                continue
            seen.add(marker)
        obj = ref.get_object()
        subtype = obj.get("/Subtype")
        if subtype == "/Image":
            count += 1
        elif subtype == "/Form":
            count += _images_in(obj.get("/Resources"), seen, depth + 1)
    return count


def count_images(pages: list[Any]) -> int | None:
    """How many raster images the pages declare, or ``None`` if that is unknown.

    Why this is here at all: every deviation this tool reports is the absence
    of something from a text layer. That statement is only worth as much as the
    tool's ability to say the missing element is not sitting in a picture the
    extractor cannot read. Counting the pictures does not read them, but it
    tells a reader which of the two explanations is even available.

    What is counted: image XObjects reachable from each page's resources,
    including those nested inside Form XObjects. What is not counted: inline
    images, and text drawn as vector paths. A count of zero therefore narrows
    the possibilities without closing them, and the sentence the tool prints
    for a zero count says exactly that.
    """
    try:
        return sum(_images_in(page.get("/Resources"), set(), 0) for page in pages)
    except Exception:
        # Never fatal. An unknown count downgrades the claim the tool makes
        # about an absence; it does not stop the document being checked.
        return None


def _build(
    path: Path,
    digest: str,
    page_count: int | None,
    text: str,
    image_count: int | None,
    extraction_basis: str,
    cells: tuple[str, ...] | None = None,
    vector_shape_count: int | None = None,
) -> LabelDocument:
    return LabelDocument(
        path=path,
        sha256=digest,
        page_count=page_count,
        raw_text=text,
        normalized=normalize(text),
        normalized_lines=normalize_lines(text),
        image_count=image_count,
        extraction_basis=extraction_basis,
        cells=cells,
        vector_shape_count=vector_shape_count,
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
) -> tuple[str, list[Any]] | UnreadableDocument:
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
    return "\n".join(chunks), pages


def _extract_pdf(path: Path, data: bytes, digest: str, min_chars: int) -> ExtractResult:
    reader = _open_pdf(path, digest)
    if isinstance(reader, UnreadableDocument):
        return reader

    extracted = _pdf_text(reader, path, digest)
    if isinstance(extracted, UnreadableDocument):
        return extracted

    text, pages = extracted
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
    images = count_images(pages)
    paints = count_vector_paints(pages)
    if images is None:
        basis = IMAGES_UNCOUNTABLE_BASIS
    else:
        basis = _pdf_basis(images, paints)
    return _build(
        path,
        digest,
        len(pages),
        text,
        images,
        basis,
        document_cells(pages),
        vector_shape_count=paints,
    )


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
    return _build(path, digest, None, text, None, TEXT_INPUT_BASIS)


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


def unsupported_in(paths: list[Path]) -> list[Path]:
    """Files inside the directories given that are not a supported label format.

    :func:`discover` drops these, and it should: expanding a directory into
    every file inside it would report a stylesheet as an unreadable label.
    Dropping them without a word is the part worth fixing. The Energy
    Commission publishes a second rendering of each label beside it, a
    spreadsheet, and someone who points this tool at a folder holding both is
    entitled to be told which of the two was read. The tool reads the one it
    reads, and says so, rather than deciding on a reader's behalf that the
    other file was not there. See ADR 0009.
    """
    skipped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if not path.is_dir():
            continue
        for child in sorted(path.rglob("*")):
            if not child.is_file() or child.suffix.lower() in SUPPORTED_SUFFIXES:
                continue
            resolved = child.resolve()
            if resolved not in seen:
                seen.add(resolved)
                skipped.append(child)
    return skipped

#!/usr/bin/env python3
"""Report the artwork on a PDF page, so an absence finding can be judged.

Why this exists. The checker reads a text layer. When it reports that a
prescribed element does not appear, there are two explanations: the element is
not on the label, or it is on the label as a picture that no text extractor can
read. The difference matters, because the labels this tool reads belong to
named organisations, and reporting a limit of PDF extraction as a property of
someone's document is a way of being wrong about a person.

This script does not settle that question by itself. It narrows it, by printing
every image the page declares and the size at which the page places it, in
points. An image too small to hold a legible telephone number is not where a
telephone number is hiding. Where the printout leaves any doubt, render the
page and look at it. That is the step that actually settles it, and no script
substitutes for it:

    pdftoppm -r 150 -png label.pdf out    # poppler
    magick -density 150 label.pdf out.png # imagemagick

"Declares" includes images reached through a Form XObject, and the size is the
one the page actually draws them at, with the form's own transform composed in.
That is the set the checker counts, and an auditor comparing this printout
against a finding must get the same answer from both.

What this does not do: it does not count inline images, it does not see text
drawn as vector paths, and it does not read the pictures it finds.

Not part of the package, and never invoked by the CLI, which is offline and
opens only the files it is given.

Usage:

    python3 scripts/inspect_artwork.py <file.pdf> [<file.pdf> ...]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pypdf
from pypdf.generic import ContentStream

#: Below roughly this width in points, an image is too small to carry a legible
#: telephone number at any plausible type size. It is a reading aid for whoever
#: runs this script and nothing in the checker cites it. It is not a threshold
#: any published source supplies, and it decides nothing on its own.
NARROW_POINTS = 120.0

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

#: How far to follow Form XObjects, matching ``extract.MAX_FORM_DEPTH``.
#:
#: Deliberately a copy rather than an import, so this script keeps needing
#: nothing but pypdf and an auditor can run it against a checkout they have not
#: installed. `tests/test_inspect_artwork.py` asserts the two values are equal,
#: so the copy cannot drift into a disagreement about which images exist.
MAX_FORM_DEPTH = 4


def _multiply(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, ...]:
    """Compose two PDF transformation matrices, a then b."""
    return (
        a[0] * b[0] + a[1] * b[2],
        a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2],
        a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4],
        a[4] * b[1] + a[5] * b[3] + b[5],
    )


def _xobjects(resources: Any) -> dict[str, Any]:
    """The ``/XObject`` entries of one resource dictionary, unresolved."""
    if resources is None:
        return {}
    entries = resources.get_object().get("/XObject")
    if entries is None:
        return {}
    return {str(name): ref for name, ref in entries.get_object().items()}


def _draw_stream(
    stream_object: Any,
    resources: Any,
    reader: Any,
    outer: tuple[float, ...],
    depth: int,
    prefix: str,
    found: dict[str, tuple[float, float, float, float]],
) -> None:
    """Record where each image is drawn, descending through Form XObjects.

    A form is drawn by the same ``Do`` that draws an image, and it carries its
    own content stream and its own resources. An image inside one is placed by
    the form's ``cm`` operators composed with the matrix in force where the form
    itself was drawn, and with the form's own ``/Matrix`` between them. Walking
    only the page stream, as this script used to, finds no ``Do`` naming a
    nested image and reports it as unplaced.
    """
    if stream_object is None or depth > MAX_FORM_DEPTH:
        return
    entries = _xobjects(resources)
    matrix = outer
    stack: list[tuple[float, ...]] = []
    for operands, operator in ContentStream(stream_object, reader).operations:
        if operator == b"q":
            stack.append(matrix)
        elif operator == b"Q":
            matrix = stack.pop() if stack else outer
        elif operator == b"cm":
            matrix = _multiply(tuple(float(v) for v in operands), matrix)
        elif operator == b"Do":
            name = str(operands[0])
            ref = entries.get(name)
            obj = ref.get_object() if ref is not None else None
            path = f"{prefix}{name}"
            if obj is not None and obj.get("/Subtype") == "/Form":
                inner = matrix
                form_matrix = obj.get("/Matrix")
                if form_matrix is not None:
                    inner = _multiply(tuple(float(v) for v in form_matrix), matrix)
                _draw_stream(obj, obj.get("/Resources"), reader, inner, depth + 1, f"{path}", found)
                continue
            width = abs(matrix[0]) + abs(matrix[2])
            height = abs(matrix[1]) + abs(matrix[3])
            found[path] = (width, height, matrix[4], matrix[5])


def _placements(page: Any, reader: Any) -> dict[str, tuple[float, float, float, float]]:
    """Every image the page draws, with where and how big it is drawn."""
    found: dict[str, tuple[float, float, float, float]] = {}
    _draw_stream(page.get_contents(), page.get("/Resources"), reader, IDENTITY, 0, "", found)
    return found


def _declared_images(
    resources: Any,
    seen: set[tuple[int, int]],
    depth: int = 0,
    prefix: str = "",
) -> dict[str, Any]:
    """Every image XObject reachable from a resource dictionary, forms included.

    This is the script's half of the contract ADR 0003 states for both halves.
    It mirrors ``extract._images_in``, which is what the checker counts: the
    same descent into ``/Subtype /Form``, the same depth bound, and the same
    guard against following one object twice, so that a document referencing an
    image from two places is counted once by each.

    Keys are paths rather than bare names, because two forms on one page may
    each declare an ``/Im0`` and a bare name could not tell them apart.
    """
    if resources is None or depth > MAX_FORM_DEPTH:
        return {}
    found: dict[str, Any] = {}
    for name, ref in _xobjects(resources).items():
        key = getattr(ref, "idnum", None)
        if key is not None:
            marker = (int(key), int(ref.generation))
            if marker in seen:
                continue
            seen.add(marker)
        obj = ref.get_object()
        subtype = obj.get("/Subtype")
        path = f"{prefix}{name}"
        if subtype == "/Image":
            found[path] = obj
        elif subtype == "/Form":
            found.update(_declared_images(obj.get("/Resources"), seen, depth + 1, path))
    return found


def inspect(path: Path) -> int:
    print(f"\n{path}")
    print("-" * len(str(path)))
    try:
        reader = pypdf.PdfReader(path)
    except Exception as exc:
        print(f"  could not be opened: {type(exc).__name__}")
        return 1

    total = 0
    for number, page in enumerate(reader.pages, start=1):
        images = _declared_images(page.get("/Resources"), set())
        total += len(images)
        print(f"  page {number}: {len(images)} images declared, media box {page.mediabox}")
        try:
            placed = _placements(page, reader)
        except Exception as exc:
            print(f"    placements could not be read: {type(exc).__name__}")
            placed = {}
        for name, obj in sorted(images.items()):
            pixels = f"{obj.get('/Width')}x{obj.get('/Height')} px"
            box = placed.get(name)
            if box is None:
                print(f"    {name:14s} {pixels:16s} placement not found in the content stream")
                continue
            width, height, x, y = box
            note = "too small for a legible phone number" if width < NARROW_POINTS else "large"
            print(
                f"    {name:14s} {pixels:16s} drawn {width:.0f}x{height:.0f} pt "
                f"at ({x:.0f}, {y:.0f}), {note}"
            )

    if total == 0:
        print("  No image XObject is declared on any page. An image drawn inline, or")
        print("  text drawn as vector paths, would still not be read, so render the")
        print("  page if anything remains in doubt.")
    else:
        print(f"  {total} images in total. Render the page to see what they are.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("paths", nargs="+", type=Path, help="PDFs to inspect")
    args = parser.parse_args(argv)
    return max(inspect(path) for path in args.paths)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

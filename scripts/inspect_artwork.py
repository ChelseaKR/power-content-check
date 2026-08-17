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


def _placements(page: Any, reader: Any) -> list[tuple[str, float, float, float, float]]:
    """Every XObject the page draws, with where and how big it is drawn."""
    stream = ContentStream(page.get_contents(), reader)
    matrix: tuple[float, ...] = IDENTITY
    stack: list[tuple[float, ...]] = []
    drawn: list[tuple[str, float, float, float, float]] = []
    for operands, operator in stream.operations:
        if operator == b"q":
            stack.append(matrix)
        elif operator == b"Q":
            matrix = stack.pop() if stack else IDENTITY
        elif operator == b"cm":
            matrix = _multiply(tuple(float(v) for v in operands), matrix)
        elif operator == b"Do":
            width = abs(matrix[0]) + abs(matrix[2])
            height = abs(matrix[1]) + abs(matrix[3])
            drawn.append((str(operands[0]), width, height, matrix[4], matrix[5]))
    return drawn


def _resources(page: Any) -> dict[str, Any]:
    resources = page.get("/Resources")
    if resources is None:
        return {}
    xobjects = resources.get_object().get("/XObject")
    if xobjects is None:
        return {}
    return {str(name): ref.get_object() for name, ref in xobjects.get_object().items()}


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
        objects = _resources(page)
        images = {name: obj for name, obj in objects.items() if obj.get("/Subtype") == "/Image"}
        total += len(images)
        print(f"  page {number}: {len(images)} images declared, media box {page.mediabox}")
        try:
            placed = {name: box for name, *box in _placements(page, reader)}
        except Exception as exc:
            print(f"    placements could not be read: {type(exc).__name__}")
            placed = {}
        for name, obj in sorted(images.items()):
            pixels = f"{obj.get('/Width')}x{obj.get('/Height')} px"
            box = placed.get(name)
            if box is None:
                print(f"    {name:8s} {pixels:16s} placement not found in the content stream")
                continue
            width, height, x, y = box
            note = "too small for a legible phone number" if width < NARROW_POINTS else "large"
            print(
                f"    {name:8s} {pixels:16s} drawn {width:.0f}x{height:.0f} pt "
                f"at ({x:.0f}, {y:.0f}), {note}"
            )

    if total == 0:
        print("  No image is declared on any page. Text drawn as vector paths would")
        print("  still not be read, so render the page if anything remains in doubt.")
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

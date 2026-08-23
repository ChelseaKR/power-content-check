"""Shared fixtures.

The label fixtures are synthetic. They imitate the shape of the format the
California Energy Commission issues; they are not copies of any published
label and they do not carry any real supplier's figures.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pypdf
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def conforming_label() -> Path:
    return FIXTURES / "conforming_label.txt"


@pytest.fixture
def deficient_label() -> Path:
    return FIXTURES / "deficient_label.txt"


def _pdf(objects: list[bytes]) -> bytes:
    """Assemble numbered objects into a PDF with a correct cross reference table.

    Written by hand rather than with a PDF library because these fixtures need
    to control exactly what the page declares: a text layer, and a chosen
    number of images, including images reached through a Form XObject. That is
    the shape the image counter has to get right, and no writer API in the
    dependency set produces it.
    """
    out = bytearray(b"%PDF-1.7\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    start = len(out)
    size = len(objects) + 1
    out += f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    return bytes(out)


def _image_object() -> bytes:
    return (
        b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray "
        b"/BitsPerComponent 8 /Length 1 >>\nstream\n\xff\nendstream"
    )


def _stream(dictionary: str, payload: bytes) -> bytes:
    return (
        f"<< {dictionary} /Length {len(payload)} >>\nstream\n".encode() + payload + b"\nendstream"
    )


LABEL_LINES = (
    "2024 POWER CONTENT LABEL",
    "Example Municipal Utility District",
    "Greenhouse Gas Emissions Intensity in lbs of CO2e per megawatt hour: 410",
    "Renewables and Zero-Carbon Resources",
    "RPS Eligible Renewables 40%",
    "Solar 20%  Wind 12%  Geothermal 5%  Biomass and Biogas 2%",
    "Eligible Hydroelectric 1%  Large Hydroelectric 8%  Nuclear 9%",
    "Fossil Fuels  Natural Gas 30%  Coal and Petroleum 3%",
    "Unspecified Power (primarily fossil fuels) 10%",
    "Total 100%",
)


#: Extra strings to draw at chosen coordinates, as (x, y, text).
#:
#: A label's column headings are not prose, and where they sit is what tells one
#: heading from the one beside it. Fixtures that need real geometry, rather than
#: a line of text that happens to contain the right words, place their own.
Placed = tuple[tuple[float, float, str], ...]


def synthetic_label_pdf(
    path: Path,
    images: int = 0,
    nested_images: int = 0,
    placed: Placed = (),
) -> Path:
    """A one page PDF carrying a readable text layer and a chosen image count."""
    drawing = ["BT /F1 11 Tf"]
    for index, line in enumerate(LABEL_LINES):
        drawing.append(f"1 0 0 1 40 {740 - index * 18} Tm ({line}) Tj")
    for x, y, text in placed:
        drawing.append(f"1 0 0 1 {x} {y} Tm ({text}) Tj")
    drawing.append("ET")
    for slot in range(images):
        drawing.append(f"q 10 0 0 10 {60 + slot * 20} 300 cm /Im{slot} Do Q")
    if nested_images:
        drawing.append("q 10 0 0 10 60 200 cm /Fm0 Do Q")
    content = "\n".join(drawing).encode("ascii")

    first_image = 6
    resources = ["/Font << /F1 5 0 R >>"]
    xobjects = [f"/Im{slot} {first_image + slot} 0 R" for slot in range(images)]
    form_number = first_image + images
    nested_first = form_number + 1
    if nested_images:
        xobjects.append(f"/Fm0 {form_number} 0 R")
    if xobjects:
        resources.append(f"/XObject << {' '.join(xobjects)} >>")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            f"/Resources << {' '.join(resources)} >> >>"
        ).encode("ascii"),
        _stream("", content),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    objects += [_image_object() for _ in range(images)]
    if nested_images:
        nested_refs = " ".join(f"/In{n} {nested_first + n} 0 R" for n in range(nested_images))
        objects.append(
            _stream(
                "/Type /XObject /Subtype /Form /BBox [0 0 1 1] "
                f"/Resources << /XObject << {nested_refs} >> >>",
                b"q Q",
            )
        )
        objects += [_image_object() for _ in range(nested_images)]

    path.write_bytes(_pdf(objects))
    return path


@pytest.fixture
def text_layer_pdf(tmp_path: Path) -> Path:
    """A readable PDF with no image on it."""
    return synthetic_label_pdf(tmp_path / "plain_label.pdf")


@pytest.fixture
def illustrated_pdf(tmp_path: Path) -> Path:
    """A readable PDF that also carries artwork, two of it nested in a form."""
    return synthetic_label_pdf(tmp_path / "illustrated_label.pdf", images=3, nested_images=2)


#: A statewide column heading too long for its column, wrapped onto a second
#: line, with the supplier's own column heading wrapped beside it. Reading the
#: page line by line, which is what a text extractor does, yields "2024 Example
#: CA Utility" and then "Power Mix Average", so neither heading survives as a
#: phrase. Reading it column by column yields both. This is the shape of the
#: artefact ADR 0006 found on published labels and ADR 0008 repairs.
#:
#: The second line of each heading is centred under the first, which is how the
#: issued labels set them, so its extent sits inside the first line's. The first
#: heading arrives in two pieces that touch, which is how the issued labels
#: arrive too: a page draws a phrase in as many runs as it likes, and the pieces
#: have to be put back together before there is a cell to place.
WRAPPED_HEADING: Placed = (
    (200, 540, "2024 "),
    (227.7, 540, "Example"),
    (400, 540, "CA Utility"),
    (210, 528, "Power Mix"),
    (402, 528, "Average"),
)

#: The words of an accepted rendering, present on the page and belonging to
#: nothing. They sit too far apart vertically to be lines of one cell and their
#: extents do not nest, so reading the page column by column puts them in three
#: different cells and the check still refuses to decide.
SCATTERED_WORDS: Placed = (
    (40, 540, "Average Rate Table"),
    (300, 480, "CA"),
    (450, 420, "Utility"),
)


@pytest.fixture
def wrapped_heading_pdf(tmp_path: Path) -> Path:
    """A readable PDF whose statewide column heading wraps onto a second line."""
    return synthetic_label_pdf(tmp_path / "wrapped_heading.pdf", placed=WRAPPED_HEADING)


@pytest.fixture
def scattered_words_pdf(tmp_path: Path) -> Path:
    """A readable PDF carrying the words of a rendering but not the rendering."""
    return synthetic_label_pdf(tmp_path / "scattered_words.pdf", placed=SCATTERED_WORDS)


@pytest.fixture
def image_only_pdf(tmp_path: Path) -> Path:
    """A structurally valid PDF with a page and no text layer.

    This is the shape of a scanned label. An extractor hands back an empty
    string for it, and an empty string is exactly what "nothing wrong here"
    also looks like. That collision is the defect this project exists to avoid.
    """
    path = tmp_path / "scanned_label.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


@pytest.fixture
def encrypted_pdf(tmp_path: Path) -> Path:
    """A password-protected PDF.

    pypdf hands back an empty string for one of these rather than refusing, so
    without an explicit branch this would look like a label with nothing on it.
    """
    path = tmp_path / "encrypted_label.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("correct horse battery staple")
    with path.open("wb") as handle:
        writer.write(handle)
    return path


@pytest.fixture
def corrupt_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "corrupt_label.pdf"
    path.write_bytes(b"%PDF-1.7\nthis is not actually a pdf body\n")
    return path


@pytest.fixture
def empty_file(tmp_path: Path) -> Path:
    path = tmp_path / "empty_label.pdf"
    path.write_bytes(b"")
    return path


@pytest.fixture
def unsupported_file(tmp_path: Path) -> Path:
    path = tmp_path / "label.docx"
    path.write_bytes(b"PK\x03\x04 not really a docx either")
    return path


@pytest.fixture
def empty_directory(tmp_path: Path) -> Path:
    path = tmp_path / "no_labels_here"
    path.mkdir()
    return path


def synthetic_multipage_pdf(
    path: Path,
    pages: Sequence[tuple[tuple[str, ...], Placed]],
) -> Path:
    """A PDF of several pages, each carrying chosen lines and placed spans.

    Pages share one font and nothing else. Geometry is reconstructed per page
    by construction, because ``document_cells`` walks the page list and never
    sees two pages at once; the point of this fixture is to hold that visible
    rather than assumed, and to prove that text split across a page boundary
    still reaches the checks through the ordinary line join.
    """
    count = len(pages)
    font_number = 3 + 2 * count

    def drawing(lines: tuple[str, ...], placed: Placed) -> bytes:
        ops = ["BT /F1 11 Tf"]
        for index, line in enumerate(lines):
            ops.append(f"1 0 0 1 40 {740 - index * 18} Tm ({line}) Tj")
        for x, y, text in placed:
            ops.append(f"1 0 0 1 {x} {y} Tm ({text}) Tj")
        ops.append("ET")
        return _stream("", "\n".join(ops).encode("ascii"))

    page_objects = [
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {3 + count + k} 0 R /Resources << /Font << /F1 {font_number} 0 R >> "
            f">> >>"
        ).encode("ascii")
        for k in range(count)
    ]
    content_objects = [drawing(lines, placed) for lines, placed in pages]
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (
            f"<< /Type /Pages /Kids [{' '.join(f'{3 + k} 0 R' for k in range(count))}] "
            f"/Count {count} >>"
        ).encode("ascii"),
        *page_objects,
        *content_objects,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    path.write_bytes(_pdf(objects))
    return path

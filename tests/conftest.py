"""Shared fixtures.

The label fixtures are synthetic. They imitate the shape of the format the
California Energy Commission issues; they are not copies of any published
label and they do not carry any real supplier's figures.
"""

from __future__ import annotations

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

"""Reading documents, and refusing to."""

from __future__ import annotations

from pathlib import Path

from power_content_check.extract import (
    SUPPORTED_SUFFIXES,
    LabelDocument,
    UnreadableDocument,
    discover,
    extract,
)


class TestReadable:
    def test_a_text_label_reads(self, conforming_label: Path) -> None:
        result = extract(conforming_label)
        assert isinstance(result, LabelDocument)
        assert result.sha256
        assert result.page_count is None
        assert "power content label" in result.normalized

    def test_the_digest_is_the_file_digest(self, conforming_label: Path) -> None:
        import hashlib

        result = extract(conforming_label)
        assert isinstance(result, LabelDocument)
        assert result.sha256 == hashlib.sha256(conforming_label.read_bytes()).hexdigest()

    def test_latin1_fallback(self, tmp_path: Path) -> None:
        path = tmp_path / "latin.txt"
        path.write_bytes("Cost is 12 \xa3 per unit. ".encode("latin-1") * 20)
        assert isinstance(extract(path), LabelDocument)


class TestUnreadable:
    def test_missing_file(self, tmp_path: Path) -> None:
        result = extract(tmp_path / "nope.pdf")
        assert isinstance(result, UnreadableDocument)
        assert result.reason == "the file does not exist"
        assert result.sha256 is None

    def test_directory(self, tmp_path: Path) -> None:
        result = extract(tmp_path)
        assert isinstance(result, UnreadableDocument)
        assert "directory" in result.reason

    def test_empty_file(self, empty_file: Path) -> None:
        result = extract(empty_file)
        assert isinstance(result, UnreadableDocument)
        assert result.reason == "the file is empty"

    def test_corrupt_pdf(self, corrupt_pdf: Path) -> None:
        result = extract(corrupt_pdf)
        assert isinstance(result, UnreadableDocument)
        assert "could not be parsed" in result.reason or "no pages" in result.reason

    def test_image_only_pdf(self, image_only_pdf: Path) -> None:
        result = extract(image_only_pdf)
        assert isinstance(result, UnreadableDocument)
        assert "text layer" in result.reason

    def test_encrypted_pdf(self, encrypted_pdf: Path) -> None:
        result = extract(encrypted_pdf)
        assert isinstance(result, UnreadableDocument)
        assert result.reason == "the PDF is encrypted"

    def test_unsupported_suffix(self, unsupported_file: Path) -> None:
        result = extract(unsupported_file)
        assert isinstance(result, UnreadableDocument)
        assert "not a supported label format" in result.reason

    def test_short_text_file(self, tmp_path: Path) -> None:
        path = tmp_path / "stub.txt"
        path.write_text("2025 Power Content Label")
        result = extract(path)
        assert isinstance(result, UnreadableDocument)
        assert "below the" in result.reason

    def test_the_threshold_is_adjustable(self, tmp_path: Path) -> None:
        path = tmp_path / "stub.txt"
        path.write_text("2025 Power Content Label")
        assert isinstance(extract(path, min_chars=5), LabelDocument)

    def test_extract_never_raises(self, tmp_path: Path) -> None:
        weird = tmp_path / "weird.pdf"
        weird.write_bytes(bytes(range(256)) * 8)
        assert isinstance(extract(weird), UnreadableDocument)


class TestDiscover:
    def test_a_directory_expands_to_supported_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.pdf").write_bytes(b"x")
        (tmp_path / "c.md").write_text("x")
        (tmp_path / "nested").mkdir()
        (tmp_path / "nested" / "d.txt").write_text("x")
        found = {p.name for p in discover([tmp_path])}
        assert found == {"a.txt", "b.pdf", "d.txt"}

    def test_an_empty_directory_finds_nothing(self, empty_directory: Path) -> None:
        assert discover([empty_directory]) == []

    def test_a_named_file_survives_even_if_unsupported(self, unsupported_file: Path) -> None:
        """So that an unsupported file is reported, not silently dropped."""
        assert discover([unsupported_file]) == [unsupported_file]

    def test_duplicates_collapse(self, conforming_label: Path) -> None:
        assert len(discover([conforming_label, conforming_label])) == 1

    def test_supported_suffixes_are_what_they_claim(self) -> None:
        assert SUPPORTED_SUFFIXES == (".pdf", ".txt")

"""The auditor's script must answer the same question as the checker.

ADR 0003 states the contract for both halves in one breath: `extract.py`
counts the images each page declares, following Form XObjects, and
`scripts/inspect_artwork.py` "makes the enumeration and placement
reproducible for anyone who wants to repeat the resolution above on a document
of their own".

Both landed in the same commit and they disagreed. The script read only the
direct entries of a page's `/XObject` dictionary, so an image reached through
a form was invisible to it, and its zero path prints a conclusion rather than
a number: "No image is declared on any page." An auditor following the
documented procedure sees a deviation, runs the script to judge whether the
element could be inside a picture, and is told there is no picture to consider
on a page the checker just said embeds two.

Nothing covered the script at all, which is why the disagreement survived. The
agreement is asserted here rather than remembered.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pypdf
import pytest

from power_content_check import extract as checker

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "inspect_artwork.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("inspect_artwork_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT_MODULE = _load()


def _checker_count(path: Path) -> int | None:
    return checker.count_images(list(pypdf.PdfReader(path).pages))


def _script_count(path: Path) -> int:
    reader = pypdf.PdfReader(path)
    return sum(
        len(SCRIPT_MODULE._declared_images(page.get("/Resources"), set())) for page in reader.pages
    )


def _drawn_nested_image_pdf(path: Path) -> Path:
    """A page that scales a form which then draws an image inside itself.

    The one shape that separates composing the matrices from ignoring them.
    The page draws the form at 2x, translated to (100, 100); inside, the form
    draws its image at 30x15, translated to (5, 5). Composed, the image is
    drawn 60x30 points at (110, 110). A walk of the page stream alone finds no
    `Do` naming the image at all.
    """
    from conftest import _image_object, _pdf, _stream

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /XObject << /Fm0 5 0 R >> >> >>",
        _stream("", b"q 2 0 0 2 100 100 cm /Fm0 Do Q\n"),
        _stream(
            "/Type /XObject /Subtype /Form /BBox [0 0 100 100] "
            "/Resources << /XObject << /In0 6 0 R >> >>",
            b"q 30 0 0 15 5 5 cm /In0 Do Q\n",
        ),
        _image_object(),
    ]
    path.write_bytes(_pdf(objects))
    return path


class TestTheTwoHalvesAgree:
    """The script's total must equal the checker's, on any document."""

    def test_the_depth_bound_is_the_same_number(self) -> None:
        """A copied constant that drifts is a disagreement about what exists."""
        assert SCRIPT_MODULE.MAX_FORM_DEPTH == checker.MAX_FORM_DEPTH

    def test_the_totals_agree_on_the_illustrated_fixture(self, illustrated_pdf: Path) -> None:
        assert _script_count(illustrated_pdf) == _checker_count(illustrated_pdf) == 5

    @pytest.mark.parametrize(
        ("images", "nested"),
        [(0, 0), (3, 0), (0, 2), (2, 3), (1, 1)],
    )
    def test_the_totals_agree_however_the_artwork_is_reached(
        self, tmp_path: Path, images: int, nested: int
    ) -> None:
        from conftest import synthetic_label_pdf

        path = synthetic_label_pdf(
            tmp_path / f"mix_{images}_{nested}.pdf", images=images, nested_images=nested
        )
        assert _script_count(path) == _checker_count(path) == images + nested

    def test_the_totals_agree_on_every_cached_label(self) -> None:
        """The published labels the calibration record rests on, when present.

        `examples/cache/` is gitignored on purpose, so this runs for whoever
        has fetched the corpus with `scripts/fetch_examples.py` and skips in
        CI, which has no network. It is an extra reading of the same contract
        the synthetic cases above pin unconditionally, not the only one: those
        run everywhere, so skipping here cannot leave the agreement untested.

        Checked against all ten cached labels on 6 September 2026; every one
        agrees, which is why this defect was latent rather than firing.
        """
        cached = sorted((ROOT / "examples" / "cache").glob("*.pdf"))
        if not cached:
            pytest.skip("no cached labels; run scripts/fetch_examples.py to include them")
        for path in cached:
            assert _script_count(path) == _checker_count(path), path.name


class TestTheZeroPathDoesNotDenyAPicture:
    """Its zero path prints a conclusion, so it must not be reached wrongly."""

    def test_an_image_only_inside_a_form_is_not_reported_as_none(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from conftest import synthetic_label_pdf

        path = synthetic_label_pdf(tmp_path / "nested_only.pdf", images=0, nested_images=2)
        # The precondition: the checker really does say there are two, so this
        # is a disagreement between the halves and not an empty document.
        assert _checker_count(path) == 2

        assert SCRIPT_MODULE.inspect(path) == 0
        out = capsys.readouterr().out
        assert "No image" not in out
        assert "2 images declared" in out
        assert "2 images in total" in out

    def test_a_page_with_no_artwork_at_all_still_says_so(
        self, text_layer_pdf: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The negative control: the zero path must still be reachable."""
        assert SCRIPT_MODULE.inspect(text_layer_pdf) == 0
        assert "No image XObject is declared on any page." in capsys.readouterr().out

    def test_an_unopenable_file_is_reported_rather_than_counted(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        broken = tmp_path / "broken.pdf"
        broken.write_bytes(b"not a pdf at all")
        assert SCRIPT_MODULE.inspect(broken) == 1
        assert "could not be opened" in capsys.readouterr().out


class TestPlacementFollowsTheFormTransform:
    """A drawn size is the reading aid NARROW_POINTS exists for.

    Descending in the enumeration alone would report every nested image as
    "placement not found in the content stream", which is a worse answer than
    the one it replaced: the auditor is told the tool cannot say how big the
    picture is, on the documents where the question is live.
    """

    def test_a_nested_image_is_placed_with_the_matrices_composed(self, tmp_path: Path) -> None:
        path = _drawn_nested_image_pdf(tmp_path / "drawn_nested.pdf")
        reader = pypdf.PdfReader(path)
        placed = SCRIPT_MODULE._placements(reader.pages[0], reader)

        assert set(placed) == {"/Fm0/In0"}
        width, height, x, y = placed["/Fm0/In0"]
        assert (round(width), round(height)) == (60, 30)
        assert (round(x), round(y)) == (110, 110)

    def test_the_drawn_size_reaches_the_printout(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = _drawn_nested_image_pdf(tmp_path / "drawn_nested_print.pdf")
        assert SCRIPT_MODULE.inspect(path) == 0
        out = capsys.readouterr().out
        assert "placement not found" not in out
        assert "drawn 60x30 pt at (110, 110)" in out

    def test_two_forms_declaring_the_same_name_are_told_apart(self, tmp_path: Path) -> None:
        """Bare names collide across forms; the paths the script keys on do not."""
        from conftest import _image_object, _pdf, _stream

        form = (
            "/Type /XObject /Subtype /Form /BBox [0 0 100 100] "
            "/Resources << /XObject << /In0 {ref} 0 R >> >>"
        )
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /XObject << /Fm0 5 0 R /Fm1 6 0 R >> >> >>",
            _stream("", b"q 1 0 0 1 0 0 cm /Fm0 Do Q\nq 1 0 0 1 0 0 cm /Fm1 Do Q\n"),
            _stream(form.format(ref=7), b"q 10 0 0 10 0 0 cm /In0 Do Q\n"),
            _stream(form.format(ref=8), b"q 10 0 0 10 0 0 cm /In0 Do Q\n"),
            _image_object(),
            _image_object(),
        ]
        path = tmp_path / "colliding_names.pdf"
        path.write_bytes(_pdf(objects))

        declared: dict[str, Any] = SCRIPT_MODULE._declared_images(
            pypdf.PdfReader(path).pages[0].get("/Resources"), set()
        )
        assert set(declared) == {"/Fm0/In0", "/Fm1/In0"}
        assert _script_count(path) == _checker_count(path) == 2

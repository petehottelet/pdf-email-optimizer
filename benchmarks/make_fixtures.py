#!/usr/bin/env python3
"""Generate small, redistributable benchmark/test fixtures.

Every PDF produced here is synthesized from scratch with ``Pillow``,
``reportlab``, and ``pypdf``. No user, commercial, downloaded, or otherwise
copyrighted content is used, so the output is safe to redistribute (CC0).

The fixtures intentionally exercise the optimizer's distinct code paths:
photo-heavy rasters, sharp screenshots, vector text, scans, transparency,
forms/annotations, private payloads, duplicate images, embedded metadata, and
encrypted files. Regenerate with::

    python benchmarks/make_fixtures.py
"""

from __future__ import annotations

import argparse
import io
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "benchmarks" / "fixtures"

# A fixed seed keeps regenerated fixtures byte-stable enough for review diffs.
SEED = 1234


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _photo_like_image(width: int, height: int, seed: int) -> Image.Image:
    """A smooth, noisy, gradient image that behaves like a photograph.

    Photographs recompress well with JPEG, so this drives the image-recompress
    ladder and produces a real size reduction.
    """

    rng = random.Random(seed)
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    base_r = rng.randint(40, 200)
    base_g = rng.randint(40, 200)
    base_b = rng.randint(40, 200)
    for y in range(height):
        for x in range(width):
            r = int(base_r + 60 * math.sin(x / 40.0) + 40 * math.cos(y / 55.0))
            g = int(base_g + 50 * math.sin((x + y) / 60.0))
            b = int(base_b + 45 * math.cos(x / 70.0) + 30 * math.sin(y / 35.0))
            noise = rng.randint(-12, 12)
            pixels[x, y] = (
                max(0, min(255, r + noise)),
                max(0, min(255, g + noise)),
                max(0, min(255, b + noise)),
            )
    return image


def _screenshot_like_image(width: int, height: int) -> Image.Image:
    """Sharp, high-frequency UI content that JPEG damages badly.

    Recompressing this destroys text legibility, so the optimizer should keep
    a high quality floor / protect it under the quality profile.
    """

    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = _load_font(16)
    draw.rectangle([0, 0, width, 48], fill=(33, 102, 172))
    draw.text((16, 14), "Quarterly Metrics Dashboard", fill="white", font=font)
    for row in range(8):
        top = 70 + row * 60
        draw.rectangle([16, top, width - 16, top + 48], outline=(180, 180, 180))
        draw.text((28, top + 14), f"Row {row + 1}: value = {row * 137 % 1000}", fill=(20, 20, 20), font=font)
        draw.rectangle([width - 220, top + 10, width - 220 + (row * 25) % 180, top + 38], fill=(70, 160, 90))
    for x in range(0, width, 7):
        draw.line([(x, height - 120), (x, height - 120 - (x % 90))], fill=(120, 120, 200))
    return image


def _scan_like_image(width: int, height: int) -> Image.Image:
    """Grayscale page with text + speckle, like a flatbed scan."""

    image = Image.new("L", (width, height), 245)
    draw = ImageDraw.Draw(image)
    font = _load_font(20)
    rng = random.Random(SEED + 7)
    for line in range(28):
        y = 60 + line * 30
        words = rng.randint(6, 11)
        x = 50
        for _ in range(words):
            length = rng.randint(30, 90)
            draw.text((x, y), "lorem " * 1, fill=rng.randint(20, 70), font=font)
            draw.line([(x, y + 24), (x + length, y + 24)], fill=rng.randint(40, 90))
            x += length + 18
    for _ in range(4000):
        draw.point((rng.randint(0, width - 1), rng.randint(0, height - 1)), fill=rng.randint(0, 120))
    return image


def _image_to_pdf_bytes(image: Image.Image, *, dpi: int = 150) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PDF", resolution=dpi)
    return buffer.getvalue()


def _merge_image_pages(writer: PdfWriter, image: Image.Image, *, dpi: int = 150) -> None:
    reader = PdfReader(io.BytesIO(_image_to_pdf_bytes(image, dpi=dpi)))
    for page in reader.pages:
        writer.add_page(page)


def _write(writer: PdfWriter, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


# --------------------------------------------------------------------------- #
# Individual fixtures
# --------------------------------------------------------------------------- #
def make_photo_brochure(path: Path) -> Path:
    writer = PdfWriter()
    for index in range(4):
        _merge_image_pages(writer, _photo_like_image(1600, 1200, SEED + index), dpi=150)
    return _write(writer, path)


def make_screenshot_report(path: Path) -> Path:
    writer = PdfWriter()
    for _ in range(3):
        _merge_image_pages(writer, _screenshot_like_image(1400, 1000), dpi=150)
    return _write(writer, path)


def make_scanned_pdf(path: Path) -> Path:
    writer = PdfWriter()
    for _ in range(3):
        _merge_image_pages(writer, _scan_like_image(1700, 2200), dpi=200)
    return _write(writer, path)


def make_text_vector_document(path: Path) -> Path:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    for page in range(3):
        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawString(72, height - 80, f"Vector Document - Page {page + 1}")
        pdf.setFont("Helvetica", 11)
        for line in range(40):
            pdf.drawString(72, height - 120 - line * 16, f"Line {line + 1}: the quick brown fox jumps over the lazy dog.")
        pdf.setStrokeColorRGB(0.2, 0.3, 0.7)
        for i in range(20):
            pdf.line(72 + i * 8, 60, 72 + i * 8, 120)
        pdf.showPage()
    pdf.save()
    reader = PdfReader(buffer)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    return _write(writer, path)


def make_mixed_transparency(path: Path) -> Path:
    """Page carrying images with real alpha + an ExtGState (blend) entry."""

    writer = PdfWriter()
    base = _photo_like_image(1200, 900, SEED + 50).convert("RGBA")
    overlay = Image.new("RGBA", (1200, 900), (255, 0, 0, 90))
    blended = Image.alpha_composite(base, overlay)
    _merge_image_pages(writer, blended, dpi=150)
    page = writer.pages[0]
    resources = page.get("/Resources")
    if resources is not None:
        ext_gstate = DictionaryObject(
            {
                NameObject("/GS1"): DictionaryObject(
                    {
                        NameObject("/Type"): NameObject("/ExtGState"),
                        NameObject("/ca"): NumberObject(0.5),
                        NameObject("/BM"): NameObject("/Multiply"),
                    }
                )
            }
        )
        resources[NameObject("/ExtGState")] = ext_gstate
    return _write(writer, path)


def make_forms_annotations(path: Path) -> Path:
    """AcroForm with a text field + a link/text annotation."""

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(72, height - 80, "Registration Form")
    pdf.acroForm.textfield(
        name="full_name",
        tooltip="Full name",
        x=72,
        y=height - 140,
        width=300,
        height=24,
        borderStyle="inset",
    )
    pdf.acroForm.checkbox(name="subscribe", x=72, y=height - 180, size=20)
    pdf.showPage()
    pdf.save()
    reader = PdfReader(buffer)
    writer = PdfWriter()
    writer.append(reader)

    page = writer.pages[0]
    annotation = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Text"),
            NameObject("/Rect"): ArrayObject(
                [NumberObject(72), NumberObject(200), NumberObject(120), NumberObject(240)]
            ),
            NameObject("/Contents"): TextStringObject("Reviewer note: confirm details."),
            NameObject("/Open"): BooleanObject(False),
        }
    )
    annotation_ref = writer._add_object(annotation)
    existing = page.get("/Annots")
    if existing is None:
        page[NameObject("/Annots")] = ArrayObject([annotation_ref])
    else:
        existing.append(annotation_ref)
    return _write(writer, path)


def make_creator_metadata(path: Path) -> Path:
    """Fixture that carries creator-only payloads (``/PieceInfo``, ``/LastModified``).

    These keys are added by design tools and are routinely safe to drop on export;
    the optimizer's structural-cleanup pass removes them. Named to describe the
    behaviour, not to alarm the reader.
    """

    writer = PdfWriter()
    _merge_image_pages(writer, _photo_like_image(1200, 900, SEED + 60), dpi=150)
    for page in writer.pages:
        page[NameObject("/PieceInfo")] = DictionaryObject(
            {NameObject("/ADBE_Private"): TextStringObject("creator-only payload")}
        )
        page[NameObject("/LastModified")] = TextStringObject("D:20260101000000")
    writer.add_metadata(
        {
            "/Creator": "FixtureSuite",
            "/Producer": "FixtureSuite Exporter",
            "/Subject": "creator metadata fixture",
        }
    )
    return _write(writer, path)


def make_embedded_metadata(path: Path) -> Path:
    writer = PdfWriter()
    _merge_image_pages(writer, _photo_like_image(1000, 800, SEED + 70), dpi=150)
    writer.add_metadata(
        {
            "/Title": "Embedded Metadata Fixture",
            "/Author": "Synthetic Author",
            "/Keywords": "synthetic, cc0, fixture",
            "/Creator": "FixtureSuite",
        }
    )
    return _write(writer, path)


def make_repeated_images(path: Path) -> Path:
    """Same image placed on many pages to exercise object dedupe."""

    shared = _photo_like_image(1100, 850, SEED + 80)
    shared_pdf = _image_to_pdf_bytes(shared, dpi=150)
    writer = PdfWriter()
    for _ in range(6):
        reader = PdfReader(io.BytesIO(shared_pdf))
        for page in reader.pages:
            writer.add_page(page)
    return _write(writer, path)


def make_encrypted_pdf(path: Path) -> Path:
    writer = PdfWriter()
    _merge_image_pages(writer, _photo_like_image(900, 700, SEED + 90), dpi=120)
    writer.encrypt("fixture-password")
    return _write(writer, path)


def make_illustrator_export(path: Path) -> Path:
    """Heavy vector art + CMYK fills, mimicking an Illustrator save-as-PDF."""

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    for layer in range(120):
        pdf.setFillColorCMYK(
            (layer % 5) / 5.0,
            (layer % 7) / 7.0,
            (layer % 3) / 3.0,
            0.1,
        )
        radius = 30 + (layer % 40) * 4
        cx = 150 + (layer * 13) % 300
        cy = 200 + (layer * 29) % 400
        pdf.circle(cx, cy, radius, stroke=1, fill=1)
    pdf.setFont("Helvetica-Bold", 24)
    pdf.setFillColorCMYK(0, 0, 0, 1)
    pdf.drawString(72, height - 60, "Illustrator-style Vector Export")
    pdf.showPage()
    pdf.save()
    reader = PdfReader(buffer)
    writer = PdfWriter()
    writer.append(reader)
    return _write(writer, path)


def make_indesign_export(path: Path) -> Path:
    """Mixed text + placed photos + vector rules, like an InDesign export."""

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    for page in range(2):
        pdf.setFont("Helvetica-Bold", 22)
        pdf.drawString(72, height - 70, f"InDesign Layout - Spread {page + 1}")
        pdf.setFont("Helvetica", 10)
        for line in range(25):
            pdf.drawString(72, height - 110 - line * 14, "Body copy flows across the column with consistent leading.")
        photo = _photo_like_image(700, 500, SEED + 100 + page)
        photo_buffer = io.BytesIO()
        photo.save(photo_buffer, "PNG")
        photo_buffer.seek(0)
        from reportlab.lib.utils import ImageReader

        pdf.drawImage(ImageReader(photo_buffer), 320, 120, width=220, height=160)
        pdf.setStrokeColorRGB(0.1, 0.1, 0.1)
        pdf.line(72, 110, width - 72, 110)
        pdf.showPage()
    pdf.save()
    reader = PdfReader(buffer)
    writer = PdfWriter()
    writer.append(reader)
    return _write(writer, path)


FIXTURES = {
    "photo_brochure": make_photo_brochure,
    "screenshot_report": make_screenshot_report,
    "scanned_pdf": make_scanned_pdf,
    "text_vector_document": make_text_vector_document,
    "mixed_transparency": make_mixed_transparency,
    "forms_annotations": make_forms_annotations,
    "creator_metadata": make_creator_metadata,
    "embedded_metadata": make_embedded_metadata,
    "repeated_images": make_repeated_images,
    "encrypted_pdf": make_encrypted_pdf,
    "illustrator_export": make_illustrator_export,
    "indesign_export": make_indesign_export,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--only", nargs="*", choices=sorted(FIXTURES), help="Generate only these fixtures.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    selected = args.only or list(FIXTURES)

    for name in selected:
        path = output_dir / f"{name}.pdf"
        FIXTURES[name](path)
        size_kb = path.stat().st_size / 1024
        print(f"Wrote {path.name} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

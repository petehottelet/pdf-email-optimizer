#!/usr/bin/env python3
"""Render before/after gallery art for the demonstration brochures.

For each brochure produced by ``make_demo_brochures.py`` this:

1. builds the email copy with the real optimizer (``quality`` profile),
2. renders the cover original vs. optimized side by side with the measured
   size reduction and render-QA PSNR, and
3. renders a 100%-scale detail crop of an interior page so a skeptical viewer
   can confirm the photos are not visibly degraded.

Output (committed, small PNGs) lands in ``docs/gallery/``. Run::

    python benchmarks/make_demo_brochures.py        # build the large sources
    python benchmarks/make_demo_gallery.py          # render the gallery
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from pdf_email_optimizer.optimizer import build_parser, optimize  # noqa: E402
from pdf_email_optimizer.render_qa import render_page  # noqa: E402

SOURCE_DIR = PROJECT_ROOT / "demo" / "originals"
OUTPUT_DIR = PROJECT_ROOT / "docs" / "gallery"

# (source stem, label, detail page index, crop box as fractions L,T,R,B)
CASES = [
    ("real_estate_listing", "Real-estate listing", 1, (0.04, 0.30, 0.40, 0.78)),
    ("travel_lookbook", "Travel lookbook", 2, (0.05, 0.22, 0.45, 0.74)),
    ("restaurant_menu", "Restaurant menu", 1, (0.05, 0.25, 0.42, 0.80)),
]

THUMB_LONG_EDGE = 980
HEADER = 64
ACCENT = (196, 142, 58)
INK = (24, 26, 30)
MUTED = (110, 114, 120)


def _font(size: int, bold: bool = False):
    names = (["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"] if bold
             else ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"])
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _thumb(image: Image.Image) -> Image.Image:
    out = image.copy()
    out.thumbnail((THUMB_LONG_EDGE, THUMB_LONG_EDGE), Image.Resampling.LANCZOS)
    return out


def _before_after(original: Image.Image, optimized: Image.Image, *, left: str, right: str) -> Image.Image:
    left_img, right_img = _thumb(original), _thumb(optimized)
    h = max(left_img.height, right_img.height)
    gap = 20
    w = left_img.width + right_img.width + gap
    canvas = Image.new("RGB", (w, h + HEADER), "white")
    canvas.paste(left_img, (0, HEADER))
    canvas.paste(right_img, (left_img.width + gap, HEADER))
    d = ImageDraw.Draw(canvas)
    d.text((6, 14), "ORIGINAL", font=_font(15, True), fill=MUTED)
    d.text((6, 36), left, font=_font(20, True), fill=INK)
    rx = left_img.width + gap + 6
    d.text((rx, 14), "EMAIL COPY", font=_font(15, True), fill=ACCENT)
    d.text((rx, 36), right, font=_font(20, True), fill=INK)
    return canvas


def _detail(original: Image.Image, optimized: Image.Image, box) -> Image.Image:
    w, h = original.size
    left, top, right, bottom = box
    crop = (int(left * w), int(top * h), int(right * w), int(bottom * h))
    a = original.crop(crop)
    c = optimized.crop(crop)
    scale = min(2.0, 760 / a.width)
    size = (int(a.width * scale), int(a.height * scale))
    a = a.resize(size, Image.Resampling.LANCZOS)
    c = c.resize(size, Image.Resampling.LANCZOS)
    gap = 16
    canvas = Image.new("RGB", (a.width + c.width + gap, a.height + HEADER), "white")
    canvas.paste(a, (0, HEADER))
    canvas.paste(c, (a.width + gap, HEADER))
    d = ImageDraw.Draw(canvas)
    d.text((6, 14), "ORIGINAL — 100% crop", font=_font(15, True), fill=MUTED)
    d.text((a.width + gap + 6, 14), "EMAIL COPY — 100% crop", font=_font(15, True), fill=ACCENT)
    return canvas


def build_case(stem: str, label: str, detail_page: int, crop, out_dir: Path) -> dict[str, Any]:
    source = SOURCE_DIR / f"{stem}.pdf"
    if not source.exists():
        return {"case": stem, "status": "skipped", "reason": "source missing — run make_demo_brochures.py"}

    with tempfile.TemporaryDirectory(prefix="demo-gallery-") as tmp:
        optimized = Path(tmp) / f"{stem}_email.pdf"
        args = build_parser().parse_args(
            [str(source), str(optimized), "--target-mb", "7", "--quality", "--force"]
        )
        summary = optimize(args)
        cover_o = render_page(source, 0, scale=2.0)
        cover_c = render_page(optimized, 0, scale=2.0)
        detail_o = render_page(source, detail_page, scale=2.0)
        detail_c = render_page(optimized, detail_page, scale=2.0)

    in_mb, out_mb = summary["input_mb"], summary["output_mb"]
    reduction = round((1 - out_mb / in_mb) * 100, 1) if in_mb else 0.0
    psnr = summary["render_qa"]["worst_psnr"]
    psnr_txt = "lossless" if psnr == "inf" else f"PSNR {psnr:.1f} dB"

    out_dir.mkdir(parents=True, exist_ok=True)
    # Photographic composites: optimized JPEG keeps them crisp at GitHub display
    # size while staying small enough to commit.
    before = _before_after(
        cover_o, cover_c,
        left=f"{in_mb:.1f} MB",
        right=f"{out_mb:.1f} MB  ·  {reduction:.0f}% smaller",
    )
    before.save(out_dir / f"{stem}.jpg", "JPEG", quality=90, optimize=True)
    _detail(detail_o, detail_c, crop).save(
        out_dir / f"{stem}_detail.jpg", "JPEG", quality=93, optimize=True
    )

    return {
        "case": stem,
        "status": "ok",
        "label": label,
        "input_mb": round(in_mb, 2),
        "output_mb": round(out_mb, 2),
        "reduction_percent": reduction,
        "worst_psnr": None if psnr == "inf" else round(psnr, 2),
        "quality_label": psnr_txt,
        "strategy": summary["strategy"],
        "pages": summary["pages"],
        "met_target": summary["met_target"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()
    out_dir = Path(args.output_dir).expanduser().resolve()

    results = [build_case(stem, label, page, crop, out_dir) for stem, label, page, crop in CASES]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "demo_gallery.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    for r in results:
        if r["status"] == "ok":
            print(f"{r['case']}: {r['input_mb']} MB -> {r['output_mb']} MB "
                  f"({r['reduction_percent']}%, {r['quality_label']})")
        else:
            print(f"{r['case']}: {r['status']} ({r.get('reason')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

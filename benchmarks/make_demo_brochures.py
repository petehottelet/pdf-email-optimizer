#!/usr/bin/env python3
"""Build large, realistic demonstration brochures for the README gallery.

These are the kind of files real users actually try (and fail) to email: a
photo-heavy real-estate listing, a travel lookbook, and a restaurant menu,
each exported at "design-tool" quality. The brochures are assembled from the
curated, **synthetic** stock images in ``benchmarks/demo_assets/`` (see that
folder's ``PROVENANCE.md`` — no real people, places, or trademarks, safe to
redistribute).

To make the "before" file honestly large, placed photos are embedded
losslessly (FlateDecode) at print-ish resolution, mimicking an Illustrator /
InDesign / Canva / Keynote export. ``pdf-email-optimizer`` then downsamples and
recompresses them to an email-safe copy — which is exactly what the gallery
demonstrates.

Run::

    python benchmarks/make_demo_brochures.py            # -> demo/originals/*.pdf

These source PDFs are intentionally multi-megabyte and are **not** checked in
(see ``.gitignore``); regenerate them on demand.
"""

from __future__ import annotations

import argparse
import io
from pathlib import Path

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = PROJECT_ROOT / "benchmarks" / "demo_assets"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "demo" / "originals"

# US Letter, landscape — matches the 16:9 source photography with no cropping.
PAGE_W, PAGE_H = 792.0, 612.0

# Embed photos at ~1.5x native so the source mimics a high-quality print export.
EMBED_SCALE = 1.5


# --------------------------------------------------------------------------- #
# Low-level drawing helpers
# --------------------------------------------------------------------------- #
def _load(demo: str, index: int) -> Image.Image:
    return Image.open(ASSET_DIR / demo / f"{index:02d}.jpg").convert("RGB")


def _reader(image: Image.Image) -> ImageReader:
    """Wrap a PIL image as a lossless (PNG/Flate) reader for a large source."""
    buf = io.BytesIO()
    image.save(buf, "PNG")
    buf.seek(0)
    return ImageReader(buf)


def _cover_fill(image: Image.Image, w: float, h: float) -> Image.Image:
    """Center-crop to the target aspect ratio, then upscale for embedding."""
    target = w / h
    iw, ih = image.size
    if iw / ih > target:
        new_w = int(ih * target)
        left = (iw - new_w) // 2
        image = image.crop((left, 0, left + new_w, ih))
    else:
        new_h = int(iw / target)
        top = (ih - new_h) // 2
        image = image.crop((0, top, iw, top + new_h))
    out_w = int(w * EMBED_SCALE)
    out_h = int(h * EMBED_SCALE)
    return image.resize((out_w, out_h), Image.Resampling.LANCZOS)


def _full_bleed(c: canvas.Canvas, image: Image.Image, x=0.0, y=0.0, w=PAGE_W, h=PAGE_H) -> None:
    c.drawImage(_reader(_cover_fill(image, w, h)), x, y, width=w, height=h)


def _gradient_band(c: canvas.Canvas, y: float, h: float, rgb, *, top_alpha=0.0, bottom_alpha=0.85) -> None:
    """Vertical dark-to-clear band for legible text over photos."""
    steps = 40
    for i in range(steps):
        a = bottom_alpha + (top_alpha - bottom_alpha) * (i / (steps - 1))
        c.setFillColorRGB(*rgb)
        c.setFillAlpha(a)
        c.rect(0, y + h * i / steps, PAGE_W, h / steps + 1, stroke=0, fill=1)
    c.setFillAlpha(1)


def _rule(c: canvas.Canvas, x1, y, x2, rgb, width=1.2) -> None:
    c.setStrokeColorRGB(*rgb)
    c.setLineWidth(width)
    c.line(x1, y, x2, y)


def _wrap(c: canvas.Canvas, text: str, x: float, y: float, font: str, size: float, max_w: float, leading: float, rgb):
    c.setFillColorRGB(*rgb)
    c.setFont(font, size)
    words = text.split()
    line = ""
    for word in words:
        trial = (line + " " + word).strip()
        if c.stringWidth(trial, font, size) <= max_w:
            line = trial
        else:
            c.drawString(x, y, line)
            y -= leading
            line = word
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


# --------------------------------------------------------------------------- #
# Page templates
# --------------------------------------------------------------------------- #
def cover_page(c, demo, theme, kicker, title, subtitle):
    _full_bleed(c, _load(demo, 0))
    _gradient_band(c, 0, 320, theme["ink"], bottom_alpha=0.82)
    accent = theme["accent"]
    c.setFillColorRGB(*accent)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(56, 150, kicker.upper())
    _rule(c, 56, 138, 56 + c.stringWidth(kicker.upper(), "Helvetica-Bold", 13), accent, 2)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 46)
    c.drawString(54, 86, title)
    c.setFont("Helvetica", 15)
    c.setFillColorRGB(0.92, 0.92, 0.92)
    c.drawString(56, 58, subtitle)
    c.showPage()


def feature_page(c, demo, theme, index, heading, body, caption, page_no):
    """Large photo on the left two-thirds, text rail on the right."""
    img_w = PAGE_W * 0.62
    _full_bleed(c, _load(demo, index), 0, 0, img_w, PAGE_H)
    # text rail
    c.setFillColorRGB(*theme["paper"])
    c.rect(img_w, 0, PAGE_W - img_w, PAGE_H, stroke=0, fill=1)
    rail_x = img_w + 34
    rail_w = PAGE_W - img_w - 68
    c.setFillColorRGB(*theme["accent"])
    c.setFont("Helvetica-Bold", 12)
    c.drawString(rail_x, PAGE_H - 78, theme["section"].upper())
    _rule(c, rail_x, PAGE_H - 92, rail_x + 40, theme["accent"], 2)
    y = PAGE_H - 132
    y = _wrap(c, heading, rail_x, y, "Helvetica-Bold", 24, rail_w, 28, theme["ink"])
    y -= 14
    y = _wrap(c, body, rail_x, y, "Helvetica", 11.5, rail_w, 17, theme["body"])
    # caption strip over the photo
    _gradient_band(c, 0, 88, theme["ink"], bottom_alpha=0.7)
    c.setFillColorRGB(0.96, 0.96, 0.96)
    c.setFont("Helvetica-Oblique", 11)
    c.drawString(40, 28, caption)
    c.setFillColorRGB(*theme["accent"])
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(PAGE_W - 28, 24, f"{page_no:02d}")
    c.showPage()


def duo_page(c, demo, theme, a, b, title, items, page_no):
    """Two stacked photos on the right, a titled list on the left."""
    pad = 40
    col = PAGE_W * 0.42
    c.setFillColorRGB(*theme["paper"])
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    # photos
    ph = (PAGE_H - 3 * pad) / 2
    pw = PAGE_W - col - 2 * pad
    _full_bleed(c, _load(demo, a), col + pad, PAGE_H - pad - ph, pw, ph)
    _full_bleed(c, _load(demo, b), col + pad, pad, pw, ph)
    # list
    c.setFillColorRGB(*theme["accent"])
    c.setFont("Helvetica-Bold", 12)
    c.drawString(pad, PAGE_H - 70, theme["section"].upper())
    _rule(c, pad, PAGE_H - 84, pad + 40, theme["accent"], 2)
    c.setFillColorRGB(*theme["ink"])
    c.setFont("Helvetica-Bold", 26)
    c.drawString(pad, PAGE_H - 124, title)
    y = PAGE_H - 168
    for name, desc in items:
        c.setFillColorRGB(*theme["ink"])
        c.setFont("Helvetica-Bold", 13)
        c.drawString(pad, y, name)
        y -= 17
        y = _wrap(c, desc, pad, y, "Helvetica", 10.5, col - pad, 14, theme["body"])
        y -= 12
    c.setFillColorRGB(*theme["accent"])
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(PAGE_W - 28, 22, f"{page_no:02d}")
    c.showPage()


def back_page(c, demo, theme, index, headline, lines):
    _full_bleed(c, _load(demo, index))
    _gradient_band(c, 0, PAGE_H, theme["ink"], top_alpha=0.15, bottom_alpha=0.8)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(PAGE_W / 2, PAGE_H / 2 + 30, headline)
    _rule(c, PAGE_W / 2 - 60, PAGE_H / 2 + 12, PAGE_W / 2 + 60, theme["accent"], 2)
    c.setFont("Helvetica", 13)
    y = PAGE_H / 2 - 20
    for line in lines:
        c.setFillColorRGB(0.92, 0.92, 0.92)
        c.drawCentredString(PAGE_W / 2, y, line)
        y -= 22
    c.showPage()


# --------------------------------------------------------------------------- #
# Brochure definitions
# --------------------------------------------------------------------------- #
def build_real_estate(path: Path) -> Path:
    theme = {
        "ink": (0.10, 0.12, 0.16), "body": (0.30, 0.32, 0.36),
        "paper": (0.98, 0.97, 0.95), "accent": (0.72, 0.55, 0.26),
        "section": "Sterling Ridge",
    }
    c = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    cover_page(c, "real_estate", theme, "Private Listing · For Sale",
               "Sterling Ridge Residence", "A landmark penthouse estate above the harbor")
    feature_page(c, "real_estate", theme, 1,
                 "Living, reimagined",
                 "Floor-to-ceiling glazing wraps the great room in afternoon light, "
                 "framing uninterrupted water views. White-oak floors, a sculpted "
                 "limestone hearth, and concealed automation set a calm, gallery-like tone.",
                 "Great room — west-facing, 11-ft ceilings", 2)
    feature_page(c, "real_estate", theme, 3,
                 "The dining gallery",
                 "Designed for entertaining, the dining gallery seats twelve beneath a "
                 "linear pendant and opens to a chef's pantry. Bleaded glass and live "
                 "greenery soften the architecture into something genuinely warm.",
                 "Formal dining — seats 12", 3)
    duo_page(c, "real_estate", theme, 2, 5,
             "Residence highlights",
             [("Chef's kitchen", "Honed marble island, integrated appliances, and a walk-in scullery."),
              ("Owner's wing", "Private terrace, dual dressing rooms, and a spa bath in book-matched stone."),
              ("Grounds & terrace", "1,400 sq ft of terrace with an outdoor kitchen and harbor frontage."),
              ("Provenance", "Architect-designed in 2024; offered fully furnished by appointment.")],
             4)
    feature_page(c, "real_estate", theme, 4,
                 "Beyond the door",
                 "Set within a tree-lined enclave, the residence is minutes from the marina, "
                 "the arts district, and protected open land. A rare balance of city access "
                 "and the quiet of a private estate.",
                 "Neighborhood — harborside enclave", 5)
    back_page(c, "real_estate", theme, 6, "Arrange a private viewing",
              ["Sterling Ridge Realty  ·  +1 (555) 0142",
               "viewings@sterlingridge.example  ·  Offered at price upon request",
               "By appointment only"])
    c.save()
    return path


def build_travel(path: Path) -> Path:
    theme = {
        "ink": (0.08, 0.10, 0.14), "body": (0.28, 0.30, 0.34),
        "paper": (0.97, 0.96, 0.94), "accent": (0.85, 0.42, 0.24),
        "section": "Wander",
    }
    c = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    cover_page(c, "travel", theme, "Destination Lookbook · Issue 12",
               "Wander", "Seven journeys for the slow traveler")
    feature_page(c, "travel", theme, 2,
                 "Old towns after dark",
                 "When the day-trippers leave, the medieval lanes belong to you. We map "
                 "the quiet hours — lamplit squares, late bakeries, and the rooftop bars "
                 "locals never advertise — across four storied European capitals.",
                 "Prague · the blue hour", 2)
    feature_page(c, "travel", theme, 1,
                 "Coastlines worth the detour",
                 "From boardwalk sunsets to cliffside villages, our editors trace the "
                 "shorelines where the light does the work. Includes ferry timetables, "
                 "tide windows, and the cafés that open early for swimmers.",
                 "Tropical coast · golden hour", 3)
    duo_page(c, "travel", theme, 3, 6,
             "In this issue",
             [("Markets & rails", "A steam-line route through highland market towns."),
              ("Summit season", "Three teahouse treks for first-time high-altitude hikers."),
              ("Slow cities", "Where to stay a week instead of a weekend."),
              ("Field notes", "Packing lists, visa timing, and shoulder-season pricing.")],
             4)
    feature_page(c, "travel", theme, 5,
                 "Into the cloud forest",
                 "Some of the world's great rail journeys climb through rainforest, not "
                 "over it. We ride the misted highland lines — switchbacks, viaducts, and "
                 "tea stops — where the canopy opens onto valleys you reach no other way.",
                 "Highland railway · morning mist", 5)
    back_page(c, "travel", theme, 4, "Wander further",
              ["Subscribe at wander.example  ·  Four issues a year",
               "Photography & itineraries by the Wander field desk",
               "Printed on recycled stock"])
    c.save()
    return path


def build_food(path: Path) -> Path:
    theme = {
        "ink": (0.12, 0.09, 0.07), "body": (0.32, 0.28, 0.24),
        "paper": (0.98, 0.96, 0.92), "accent": (0.70, 0.45, 0.20),
        "section": "The Copper Table",
    }
    c = canvas.Canvas(str(path), pagesize=(PAGE_W, PAGE_H))
    cover_page(c, "food", theme, "Seasonal Menu · Autumn",
               "The Copper Table", "A farm-to-table kitchen and craft bar")
    feature_page(c, "food", theme, 1,
                 "From the bakery",
                 "Every service begins at 5 a.m. with the ovens. We mill heritage grains "
                 "in-house and bake to order — crackling sourdough, soft milk rolls, and "
                 "the laminated pastries that sell out by mid-morning.",
                 "Morning bake · wood-fired hearth", 2)
    feature_page(c, "food", theme, 2,
                 "The kitchen, working",
                 "Our open kitchen runs on fire and timing. Seasonal plates land fast and "
                 "honest: charred vegetables, slow stocks, and a paella that has become a "
                 "Friday-night ritual for regulars.",
                 "Service · the line at full tilt", 3)
    duo_page(c, "food", theme, 4, 6,
             "At the bar",
             [("House preserves", "Sun-cured citrus and stone fruit, jarred at peak season."),
              ("Small-batch spirits", "Copper-still gins and a rotating barrel-aged list."),
              ("Tasting flights", "Four-pour journeys through our cellar and taproom."),
              ("Zero-proof", "Cold-pressed and fermented sodas made daily.")],
             4)
    feature_page(c, "food", theme, 3,
                 "Morning rituals",
                 "Breakfast is unhurried here. Pour-over by the window, a grain bowl bright "
                 "with seeds and fruit, and a counter that fills with neighbors before the "
                 "lunch rush turns the room over.",
                 "Counter · seasonal grain bowl", 5)
    back_page(c, "food", theme, 5, "Reserve a table",
              ["The Copper Table  ·  41 Mill Lane",
               "reservations@coppertable.example  ·  +1 (555) 0190",
               "Dinner Tue–Sun  ·  Brunch weekends"])
    c.save()
    return path


BROCHURES = {
    "real_estate_listing": build_real_estate,
    "travel_lookbook": build_travel,
    "restaurant_menu": build_food,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--only", nargs="*", choices=sorted(BROCHURES))
    args = parser.parse_args()

    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in args.only or list(BROCHURES):
        path = out_dir / f"{name}.pdf"
        BROCHURES[name](path)
        print(f"Wrote {path.name} ({path.stat().st_size / 1024 / 1024:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

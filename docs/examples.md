# Examples

## Worked Demonstration: A Brochure That Won't Send

The [gallery](../README.md#gallery) brochures are reproducible end to end. Each
source is a photo-heavy export (10–14 MB) built from synthetic, redistributable
stock — exactly the kind of file that bounces off a mail server.

```bash
# 1. Build the large source brochures into demo/originals/
python benchmarks/make_demo_brochures.py

# 2. Shrink one to an email-safe copy, with a Markdown report and JSON summary
pdf-email-optimizer demo/originals/real_estate_listing.pdf \
  demo/optimized/real_estate_listing_email.pdf \
  --target-mb 7 --quality --report demo/reports/real_estate_listing.md --json

# 3. (optional) Regenerate all before/after gallery PNGs
python benchmarks/make_demo_gallery.py
```

Measured result (`quality` profile, 7 MB target):

| Brochure | Original | Email copy | Reduction | Worst PSNR | Render QA | Target |
|---|---:|---:|---:|---:|---|---|
| Real-estate listing | 12.1 MB | 2.0 MB | 83% | 44.7 dB | passed | met |
| Travel lookbook | 13.9 MB | 2.7 MB | 81% | 43.5 dB | passed | met |
| Restaurant menu | 9.8 MB | 1.9 MB | 81% | 44.7 dB | passed | met |

The layout, text, and vectors are left untouched; only the placed photos are
downsampled and recompressed, and render QA confirms every page stays well above
the 38 dB quality floor. See `benchmarks/demo_assets/PROVENANCE.md` for image
origins.

## Preserve Image Quality

```bash
pdf-email-optimizer brochure.pdf brochure_email.pdf --target 7mb --quality --report brochure_report.md
```

Use this for photos, maps, screenshots, small UI captures, and anything where visible fidelity matters.

## Ordinary Email Copy

```bash
pdf-email-optimizer report.pdf report_email.pdf --target-mb 7 --balanced
```

This is the default behavior.

## Requested Range

```bash
pdf-email-optimizer deck.pdf deck_email.pdf --range 5-7mb --quality
```

The upper value is the hard ceiling. If cleanup alone makes the PDF smaller than the range, the optimizer does not add meaningless padding.

## Smallest File

```bash
pdf-email-optimizer large.pdf large_tiny.pdf --target-mb 5 --aggressive
```

Use this only when visible quality loss is acceptable.

## Visual Comparison

```bash
pdf-email-render-compare original.pdf optimized.pdf --output-dir qa-renders
```

Inspect the rendered pages and amplified diff images before sending high-stakes documents.

# Benchmark Fixtures

Every PDF in this directory is **synthetic and CC0**. They are generated from
scratch by [`benchmarks/make_fixtures.py`](../make_fixtures.py) using `Pillow`,
`reportlab`, and `pypdf`. No user, client, commercial, downloaded, or otherwise
copyrighted content is included, so all fixtures are safe to redistribute.

Regenerate everything:

```bash
python -m pip install -e ".[dev]"   # or: pip install reportlab
python benchmarks/make_fixtures.py
```

Generate a single fixture:

```bash
python benchmarks/make_fixtures.py --only photo_brochure
```

## Files

| Fixture | Exercises |
|---|---|
| `photo_brochure.pdf` | Photographic rasters; image-recompression ladder + quality floor |
| `screenshot_report.pdf` | Sharp UI/screenshot detail that must be protected |
| `scanned_pdf.pdf` | Grayscale scan-like pages |
| `text_vector_document.pdf` | Pure vector text; should be preserved losslessly |
| `mixed_transparency.pdf` | Alpha images + `/ExtGState` blend; transparency warnings |
| `forms_annotations.pdf` | AcroForm fields + annotations; form/annotation warnings |
| `creator_metadata.pdf` | Creator-tool `/PieceInfo` + `/LastModified` entries; structural cleanup safely drops them |
| `embedded_metadata.pdf` | Document metadata stripping |
| `repeated_images.pdf` | Duplicate image objects; structural dedupe |
| `encrypted_pdf.pdf` | Encrypted input; graceful failure path |
| `illustrator_export.pdf` | Heavy CMYK vector art (Illustrator-style export) |
| `indesign_export.pdf` | Mixed text + placed photos + rules (InDesign-style export) |

A fixed RNG seed keeps regenerated output stable enough for review diffs, but
exact bytes can still shift across `Pillow`/`reportlab` versions.

# Compatibility

## Python

Supported Python versions:

- 3.9
- 3.10
- 3.11
- 3.12
- 3.13, when dependencies support it

## Platforms

The project is intended to run on macOS, Linux, and Windows.

## PDF Behavior

The optimizer uses `pypdf` for structural cleanup and image replacement, `Pillow` for image handling, and `pypdfium2` for render QA.

Two optional backends extend it:

- **pikepdf/qpdf** (`pip install "pdf-email-optimizer[pikepdf]"`) adds a lossless structural pass (object streams, flate recompression, garbage collection). It bundles qpdf in its wheels, so no system binary is required. It runs automatically when installed and is accepted only when it produces a smaller, pixel-identical result. Disable with `--no-pikepdf`.
- **Ghostscript** is an external binary used only as an aggressive last-resort raster rewrite when requested or allowed by the selected profile.

High-stakes output should be manually checked because PDF renderers can disagree.

#!/usr/bin/env python3
"""Bilevel (1-bit) CCITT Group 4 compression strategy.

This is the right strategy for archival typeset scans - books, microfilm-style
documents, line-art technical reports, government archives - where the page is
fundamentally black ink on a tinted background and the gray information is
noise rather than signal. After conversion, every page is a single
``CCITTFaxDecode``-filtered image XObject: pure black or pure white, no
photographic data preserved.

For photo-bearing or color content, do not use this strategy. It is a deliberate
opt-in via ``--bilevel`` and is never selected automatically by the main
optimizer ladder.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from PIL import Image  # noqa: F401  # ensure Pillow is importable for TIFF G4 plugin

try:
    import img2pdf
except ImportError:  # pragma: no cover - exercised via _check_dependencies
    img2pdf = None

try:
    import pypdfium2 as pdfium
except ImportError:  # pragma: no cover - exercised via _check_dependencies
    pdfium = None

DEFAULT_DPI = 100
DEFAULT_THRESHOLD = 200
MIN_DPI = 50
MAX_DPI = 300
MIN_THRESHOLD = 1
MAX_THRESHOLD = 254


def _check_dependencies() -> None:
    """Raise a friendly error when img2pdf or pypdfium2 aren't importable."""

    missing: list[str] = []
    if pdfium is None:
        missing.append("pypdfium2")
    if img2pdf is None:
        missing.append("img2pdf")
    if missing:
        raise RuntimeError(
            "Bilevel strategy requires "
            f"{' and '.join(missing)}. Install with "
            f"`pip install 'pdf-email-optimizer[bilevel]'` (or `pip install {' '.join(missing)}`)."
        )


def _validate(dpi: int, threshold: int) -> None:
    if not (MIN_DPI <= dpi <= MAX_DPI):
        raise ValueError(f"--bilevel DPI must be in [{MIN_DPI}, {MAX_DPI}] (got {dpi}).")
    if not (MIN_THRESHOLD <= threshold <= MAX_THRESHOLD):
        raise ValueError(
            f"--bilevel-threshold must be in [{MIN_THRESHOLD}, {MAX_THRESHOLD}] (got {threshold})."
        )


def _render_bilevel_tiff(page, dpi: int, threshold: int) -> bytes:
    """Render one PDF page as a single-strip CCITT Group 4 TIFF.

    The TIFF carries explicit DPI tags so that ``img2pdf`` derives a PDF page
    of the original point dimensions (within sub-point rounding).
    """

    scale = dpi / 72.0
    pil = page.render(scale=scale).to_pil().convert("L")
    bilevel = pil.point(lambda value: 255 if value > threshold else 0, mode="1")
    buf = io.BytesIO()
    bilevel.save(buf, "TIFF", compression="group4", dpi=(dpi, dpi))
    return buf.getvalue()


def optimize_bilevel(
    input_path: Path,
    output_path: Path,
    *,
    dpi: int = DEFAULT_DPI,
    threshold: int = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Write a 1-bit, CCITT G4 PDF copy of ``input_path`` at ``output_path``.

    Returns a result dict consistent with the other strategy candidates produced
    by :mod:`pdf_email_optimizer.optimizer` (``size_bytes``, ``pages``,
    ``strategy``, plus a ``warnings`` list explaining the destructive
    conversion).
    """

    _check_dependencies()
    _validate(dpi, threshold)
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pdf = pdfium.PdfDocument(str(input_path))
    try:
        page_count = len(pdf)
        if page_count == 0:
            raise ValueError(f"Input PDF has no pages: {input_path}")
        pages_bytes: list[bytes] = [
            _render_bilevel_tiff(pdf[i], dpi=dpi, threshold=threshold) for i in range(page_count)
        ]
    finally:
        pdf.close()

    pdf_bytes = img2pdf.convert(pages_bytes)
    output_path.write_bytes(pdf_bytes)

    warnings = [
        "Bilevel strategy: all color and grayscale information was thresholded to 1-bit black/white. "
        "Use only on typeset / line-art scans; do not use on photo content.",
    ]
    return {
        "path": str(output_path),
        "size_bytes": output_path.stat().st_size,
        "pages": page_count,
        "strategy": "bilevel-g4",
        "bilevel_dpi": dpi,
        "bilevel_threshold": threshold,
        "quality_ok": True,
        "warnings": warnings,
    }


__all__ = [
    "DEFAULT_DPI",
    "DEFAULT_THRESHOLD",
    "MIN_DPI",
    "MAX_DPI",
    "MIN_THRESHOLD",
    "MAX_THRESHOLD",
    "optimize_bilevel",
]

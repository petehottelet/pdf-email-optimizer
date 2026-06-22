#!/usr/bin/env python3
"""Ghostscript fallback integration.

Ghostscript is the optimizer's last-resort, encoding-agnostic image rewriter.
It reprocesses every image at the PostScript level, which is exactly what's
needed for inputs the pypdf image ladder can't touch (JPEG2000 / CCITT / JBIG2)
or pathological exports with thousands of tiny rasters.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .utils import file_size


def run_ghostscript(
    input_path: Path,
    output_path: Path,
    *,
    target_mb: float,
    warnings: list[str],
) -> dict[str, Any] | None:
    gs = shutil.which("gswin64c") or shutil.which("gs") or shutil.which("gswin32c")
    if not gs:
        warnings.append("Ghostscript was not found; skipped last-resort raster/image rewrite fallback.")
        return None

    target_bytes = int(target_mb * 1024 * 1024)
    best: dict[str, Any] | None = None
    settings = [
        (180, 86),
        (150, 82),
        (120, 78),
        (96, 74),
    ]

    with tempfile.TemporaryDirectory(prefix="pdf-email-gs-") as tmp_name:
        tmp_dir = Path(tmp_name)
        for dpi, quality in settings:
            candidate = tmp_dir / f"gs_{dpi}_{quality}.pdf"
            command = [
                gs,
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.6",
                "-dNOPAUSE",
                "-dBATCH",
                "-dSAFER",
                "-dDetectDuplicateImages=true",
                "-dCompressFonts=true",
                "-dSubsetFonts=true",
                "-dDownsampleColorImages=true",
                "-dDownsampleGrayImages=true",
                "-dColorImageDownsampleType=/Bicubic",
                "-dGrayImageDownsampleType=/Bicubic",
                f"-dColorImageResolution={dpi}",
                f"-dGrayImageResolution={dpi}",
                f"-dJPEGQ={quality}",
                f"-sOutputFile={candidate}",
                str(input_path),
            ]
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            if completed.returncode != 0 or not candidate.exists():
                warnings.append(f"Ghostscript failed at {dpi} dpi / JPEGQ {quality}: {completed.stderr.strip()}")
                continue

            result = {
                "path": str(candidate),
                "size_bytes": file_size(candidate),
                "ghostscript": {"dpi": dpi, "jpeg_quality": quality},
                "warnings": [],
            }
            if best is None or result["size_bytes"] < best["size_bytes"]:
                best = result
            if result["size_bytes"] <= target_bytes:
                shutil.copy2(candidate, output_path)
                result["path"] = str(output_path)
                return result

        if best:
            shutil.copy2(best["path"], output_path)
            best["path"] = str(output_path)
            return best
    return None


__all__ = ["run_ghostscript"]

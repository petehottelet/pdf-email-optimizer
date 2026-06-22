#!/usr/bin/env python3
"""Resolve a user-supplied input into a working PDF.

PDF inputs pass through untouched. Office documents (``.docx`` / ``.pptx`` /
``.xlsx`` / ...) are converted to a temporary PDF via LibreOffice so the rest
of the pipeline only ever deals with PDFs, while still being able to report the
original source size for an honest end-to-end reduction figure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import office_convert
from .errors import UnsupportedInputError
from .utils import bytes_to_mb, file_size


def resolve_input_source(
    raw_path: str,
) -> tuple[Path, Path, dict[str, Any] | None, Path | None]:
    """Return ``(source_path, working_pdf, source_metadata, temp_dir)``.

    ``source_path`` is the original file the user passed in (PDF or Office
    document). ``working_pdf`` is the PDF the optimizer should actually
    process: identical to ``source_path`` for PDF inputs, or a freshly
    converted temp PDF for Office inputs.

    When an Office document is converted, ``source_metadata`` carries the
    original size / format / intermediate PDF size so the optimizer can
    report a meaningful end-to-end reduction (e.g. ``.pptx -> .pdf``).
    ``temp_dir`` is the temporary directory that holds the intermediate PDF;
    the caller is responsible for removing it in a ``finally`` block.
    """

    source_path = Path(raw_path).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Input file not found: {source_path}")

    if source_path.suffix.lower() == ".pdf":
        return source_path, source_path, None, None

    if not office_convert.is_office_document(source_path):
        raise UnsupportedInputError(
            f"Unsupported input format '{source_path.suffix}'. Supported inputs: "
            ".pdf plus Office formats ("
            + ", ".join(sorted(office_convert.OFFICE_SUFFIXES))
            + ")."
        )

    source_bytes = file_size(source_path)
    try:
        working_pdf = office_convert.convert_to_pdf(source_path)
    except office_convert.OfficeConversionError as exc:
        raise RuntimeError(str(exc)) from exc

    temp_dir = working_pdf.parent
    intermediate_bytes = file_size(working_pdf)
    metadata = {
        "source_path": str(source_path),
        "source_bytes": source_bytes,
        "source_mb": round(bytes_to_mb(source_bytes), 3),
        "source_format": source_path.suffix.lower(),
        "intermediate_pdf_bytes": intermediate_bytes,
        "intermediate_pdf_mb": round(bytes_to_mb(intermediate_bytes), 3),
        "converted_via": "libreoffice",
    }
    return source_path, working_pdf, metadata, temp_dir


def attach_source_metadata(
    summary: dict[str, Any], source_metadata: dict[str, Any] | None
) -> None:
    """Fold Office-source metadata into a summary/audit dict.

    When the optimizer converted an Office source to PDF first, this surfaces
    the original source alongside the PDF metrics so callers can report an
    end-to-end reduction (e.g. ``38 MB .pptx -> 6 MB .pdf``).
    """

    if not source_metadata:
        return
    summary["source"] = source_metadata["source_path"]
    summary["source_bytes"] = source_metadata["source_bytes"]
    summary["source_mb"] = source_metadata["source_mb"]
    summary["source_format"] = source_metadata["source_format"]
    summary["intermediate_pdf_bytes"] = source_metadata["intermediate_pdf_bytes"]
    summary["intermediate_pdf_mb"] = source_metadata["intermediate_pdf_mb"]
    summary["converted_via"] = source_metadata["converted_via"]


__all__ = ["attach_source_metadata", "resolve_input_source"]

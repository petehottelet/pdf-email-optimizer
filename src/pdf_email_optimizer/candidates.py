#!/usr/bin/env python3
"""Candidate generation: structural cleanup, recompression, and selection.

A "candidate" is one optimized copy of the PDF produced with a particular set
of knobs (cleanup-only, a given JPEG quality, a long-edge cap, ...). The
pipeline produces several and then :func:`choose_best_result` picks the one
that best fits the target window.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import NameObject

from .images import recompress_images
from .utils import file_size

PRIVATE_PAGE_KEYS = ("/PieceInfo", "/Metadata", "/LastModified")
PRIVATE_ROOT_KEYS = ("/Metadata",)


def normalize_quality_ladder(start: int, minimum: int, ladder: tuple[int, ...]) -> list[int]:
    values = [start, *ladder, minimum]
    return sorted({max(1, min(95, value)) for value in values if value >= minimum}, reverse=True)


def normalize_long_edges(
    first: int | None,
    minimum: int,
    ladder: tuple[int | None, ...],
) -> list[int | None]:
    values: list[int | None] = [first, *ladder]
    result: list[int | None] = []
    for value in values:
        if value is not None and value < minimum:
            continue
        if value not in result:
            result.append(value)
    return result


def remove_private_page_keys(page: Any, counts: Counter[str]) -> None:
    for key in PRIVATE_PAGE_KEYS:
        pdf_key = NameObject(key)
        if pdf_key in page:
            del page[pdf_key]
            counts[key] += 1


def remove_private_root_keys(writer: PdfWriter, counts: Counter[str]) -> None:
    for key in PRIVATE_ROOT_KEYS:
        pdf_key = NameObject(key)
        if pdf_key in writer._root_object:
            del writer._root_object[pdf_key]
            counts[f"root {key}"] += 1


def compress_page_streams(writer: PdfWriter, warnings: list[str]) -> int:
    compressed = 0
    for page_number, page in enumerate(writer.pages, start=1):
        try:
            page.compress_content_streams()
            compressed += 1
        except Exception as exc:  # noqa: BLE001 - keep optimizing other pages.
            warnings.append(f"Could not compress content stream on page {page_number}: {exc}")
    return compressed


def dedupe_writer_objects(writer: PdfWriter, warnings: list[str]) -> None:
    try:
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    except TypeError:
        try:
            writer.compress_identical_objects()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not deduplicate PDF objects: {exc}")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Could not deduplicate PDF objects: {exc}")


def write_candidate(
    input_path: Path,
    output_path: Path,
    *,
    strip_private: bool,
    image_quality: int | None,
    long_edge: int | None,
    min_image_pixels: int,
    min_image_bytes: int,
    flatten_alpha: bool,
) -> dict[str, Any]:
    warnings: list[str] = []
    private_counts: Counter[str] = Counter()
    reader = PdfReader(str(input_path))
    if reader.is_encrypted:
        raise PdfReadError("Encrypted PDFs must be unlocked before optimization.")

    writer = PdfWriter()
    for page in reader.pages:
        if strip_private:
            remove_private_page_keys(page, private_counts)
        writer.add_page(page)

    if strip_private:
        remove_private_root_keys(writer, private_counts)

    compressed_pages = compress_page_streams(writer, warnings)
    image_stats: dict[str, Any] | None = None
    if image_quality is not None:
        image_stats = recompress_images(
            writer,
            quality=image_quality,
            long_edge=long_edge,
            min_image_pixels=min_image_pixels,
            min_image_bytes=min_image_bytes,
            flatten_alpha=flatten_alpha,
            warnings=warnings,
        )

    dedupe_writer_objects(writer, warnings)
    writer.add_metadata({"/Producer": "optimize-pdf-email"})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        writer.write(handle)

    return {
        "path": str(output_path),
        "size_bytes": file_size(output_path),
        "pages": len(reader.pages),
        "compressed_pages": compressed_pages,
        "private_removed": dict(private_counts),
        "image_stats": image_stats,
        "warnings": warnings,
    }


def result_in_target_window(result: dict[str, Any], min_bytes: int | None, max_bytes: int) -> bool:
    size = result["size_bytes"]
    if size > max_bytes:
        return False
    return min_bytes is None or size >= min_bytes


def choose_best_result(
    results: list[dict[str, Any]],
    *,
    min_bytes: int | None,
    max_bytes: int,
    preferred_bytes: int | None,
) -> dict[str, Any]:
    acceptable = [result for result in results if result.get("quality_ok", True)]
    if not acceptable:
        acceptable = results

    in_window = [result for result in acceptable if result_in_target_window(result, min_bytes, max_bytes)]
    if in_window:
        if preferred_bytes is not None:
            return min(in_window, key=lambda item: abs(item["size_bytes"] - preferred_bytes))
        return in_window[0]

    under_max = [result for result in acceptable if result["size_bytes"] <= max_bytes]
    if under_max:
        if preferred_bytes is not None:
            return min(under_max, key=lambda item: abs(item["size_bytes"] - preferred_bytes))
        if min_bytes is not None:
            return max(under_max, key=lambda item: item["size_bytes"])
        return under_max[0]

    return min(acceptable, key=lambda item: item["size_bytes"])


__all__ = [
    "PRIVATE_PAGE_KEYS",
    "PRIVATE_ROOT_KEYS",
    "choose_best_result",
    "compress_page_streams",
    "dedupe_writer_objects",
    "normalize_long_edges",
    "normalize_quality_ladder",
    "remove_private_page_keys",
    "remove_private_root_keys",
    "result_in_target_window",
    "write_candidate",
]

#!/usr/bin/env python3
"""Image recompression for the pypdf-based candidate writer.

This is the lossy heart of the optimizer: it walks every page's images,
optionally downscales them to a long-edge cap, and re-encodes them as JPEG at a
target quality. Images that would be damaged (tiny rasters, bilevel scans,
transparent art without ``--flatten-alpha``) are skipped and reported.

Note the limits this inherits from pypdf: streams encoded with JPEG2000
(``/JPXDecode``), CCITT fax (``/CCITTFaxDecode``), or JBIG2 (``/JBIG2Decode``)
often cannot be decoded/replaced here. Those inputs are detected up front in
:mod:`pdf_email_optimizer.pdf_inspect` and routed to Ghostscript (or
``--bilevel``) by the pipeline instead of being silently left unoptimized.
"""

from __future__ import annotations

from typing import Any

from PIL import Image
from pypdf import PdfWriter


def has_alpha(image: Image.Image) -> bool:
    return image.mode in ("RGBA", "LA") or ("transparency" in image.info)


def resized_copy(image: Image.Image, long_edge: int | None) -> Image.Image:
    new_image = image.copy()
    if long_edge and max(new_image.size) > long_edge:
        new_image.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
    if new_image.mode not in ("RGB", "L"):
        new_image = new_image.convert("RGB")
    return new_image


def recompress_images(
    writer: PdfWriter,
    *,
    quality: int,
    long_edge: int | None,
    min_image_pixels: int,
    min_image_bytes: int,
    flatten_alpha: bool,
    warnings: list[str],
) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "attempted": 0,
        "changed": 0,
        "skipped": 0,
        "skipped_small": 0,
        "skipped_low_value": 0,
        "before_bytes": 0,
        "after_bytes": 0,
        "quality": quality,
        "long_edge": long_edge,
    }
    seen_refs: set[tuple[int, int]] = set()

    for page_number, page in enumerate(writer.pages, start=1):
        for image_file in list(page.images):
            ref = image_file.indirect_reference
            if ref is None:
                stats["skipped"] += 1
                continue
            ref_key = (ref.idnum, ref.generation)
            if ref_key in seen_refs:
                continue
            seen_refs.add(ref_key)

            image = image_file.image
            if image is None:
                stats["skipped"] += 1
                continue
            before = len(image_file.data or b"")
            if image.width * image.height < min_image_pixels:
                stats["skipped"] += 1
                stats["skipped_small"] += 1
                continue
            if before < min_image_bytes:
                stats["skipped"] += 1
                stats["skipped_low_value"] += 1
                continue
            if image.mode == "1":
                stats["skipped"] += 1
                continue
            if has_alpha(image) and not flatten_alpha:
                stats["skipped"] += 1
                warnings.append(
                    f"Skipped transparent image {image_file.name} on page {page_number}; use --flatten-alpha to force JPEG flattening."
                )
                continue

            replacement = resized_copy(image, long_edge)
            if has_alpha(replacement):
                background = Image.new("RGB", replacement.size, "white")
                if replacement.mode != "RGBA":
                    replacement = replacement.convert("RGBA")
                background.paste(replacement, mask=replacement.getchannel("A"))
                replacement = background

            try:
                image_file.replace(replacement, quality=quality, optimize=True)
            except Exception as exc:  # noqa: BLE001
                stats["skipped"] += 1
                warnings.append(f"Could not recompress image {image_file.name} on page {page_number}: {exc}")
                continue

            after = len(image_file.data or b"")
            stats["attempted"] += 1
            stats["before_bytes"] += before
            stats["after_bytes"] += after
            if after and (after < before or replacement.size != image.size):
                stats["changed"] += 1

    return stats


__all__ = ["has_alpha", "recompress_images", "resized_copy"]

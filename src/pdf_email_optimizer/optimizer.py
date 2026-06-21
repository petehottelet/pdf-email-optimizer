#!/usr/bin/env python3
"""Optimize a PDF for email delivery while preserving visual quality."""

from __future__ import annotations

import argparse
import json
import logging
import math
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import NameObject

from .pikepdf_backend import structural_optimize as pikepdf_structural_optimize

logging.getLogger("pypdf").setLevel(logging.ERROR)

PRIVATE_PAGE_KEYS = ("/PieceInfo", "/Metadata", "/LastModified")
PRIVATE_ROOT_KEYS = ("/Metadata",)
PROFILE_DEFAULTS: dict[str, dict[str, Any]] = {
    "quality": {
        "image_quality": 92,
        "min_image_quality": 88,
        "quality_ladder": (92, 90, 88),
        "long_edge_ladder": (None, 3200, 2800, 2400),
        "min_long_edge": 2400,
        "min_image_pixels": 500_000,
        "min_image_bytes": 350_000,
        "ghostscript": "never",
        "pikepdf": "auto",
        "render_qa": True,
        "min_render_psnr": 38.0,
        "max_render_rms": 8.0,
        "qa_scale": 1.5,
        "qa_max_pages": 12,
    },
    "balanced": {
        "image_quality": 88,
        "min_image_quality": 76,
        "quality_ladder": (88, 86, 84, 82, 80, 78, 76),
        "long_edge_ladder": (None, 2400, 2200, 2000, 1800),
        "min_long_edge": 1800,
        "min_image_pixels": 250_000,
        "min_image_bytes": 120_000,
        "ghostscript": "never",
        "pikepdf": "auto",
        "render_qa": False,
        "min_render_psnr": None,
        "max_render_rms": None,
        "qa_scale": 1.0,
        "qa_max_pages": 8,
    },
    "aggressive": {
        "image_quality": 86,
        "min_image_quality": 60,
        "quality_ladder": (86, 82, 78, 74, 70, 66, 62, 60),
        "long_edge_ladder": (None, 2400, 2000, 1800, 1600, 1400, 1200),
        "min_long_edge": 1200,
        "min_image_pixels": 120_000,
        "min_image_bytes": 0,
        "ghostscript": "auto",
        "pikepdf": "auto",
        "render_qa": False,
        "min_render_psnr": None,
        "max_render_rms": None,
        "qa_scale": 1.0,
        "qa_max_pages": 8,
    },
}


def bytes_to_mb(value: int) -> float:
    return value / (1024 * 1024)


def fmt_mb(value: int) -> str:
    return f"{bytes_to_mb(value):.2f} MB"


def profile_value(args: argparse.Namespace, key: str) -> Any:
    return PROFILE_DEFAULTS[args.profile][key]


def apply_profile_defaults(args: argparse.Namespace) -> argparse.Namespace:
    for key in (
        "image_quality",
        "min_image_quality",
        "min_long_edge",
        "min_image_pixels",
        "min_image_bytes",
        "ghostscript",
        "pikepdf",
        "render_qa",
        "min_render_psnr",
        "max_render_rms",
        "qa_scale",
        "qa_max_pages",
    ):
        if getattr(args, key) is None:
            setattr(args, key, profile_value(args, key))
    return args


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


def output_path_for(input_path: Path, output_arg: str | None) -> Path:
    if output_arg:
        return Path(output_arg).expanduser().resolve()
    return input_path.with_name(f"{input_path.stem}_email.pdf").resolve()


def parse_mb_range(value: str) -> tuple[float, float]:
    normalized = value.strip().lower().replace("mb", "").replace(" ", "")
    for separator in ("-", ":", ","):
        if separator in normalized:
            left, right = normalized.split(separator, 1)
            low = float(left)
            high = float(right)
            if low <= 0 or high <= 0:
                raise ValueError("Target range values must be positive.")
            if low > high:
                low, high = high, low
            return low, high
    exact = float(normalized)
    if exact <= 0:
        raise ValueError("Target value must be positive.")
    return exact, exact


def resolve_target_window(args: argparse.Namespace) -> dict[str, Any]:
    if args.target_range_mb:
        min_mb, max_mb = parse_mb_range(args.target_range_mb)
    elif getattr(args, "target", None):
        parsed_min, parsed_max = parse_mb_range(args.target)
        min_mb = parsed_min if parsed_min != parsed_max else args.target_min_mb
        max_mb = parsed_max
    else:
        min_mb = args.target_min_mb
        max_mb = args.target_mb

    if max_mb is None:
        max_mb = 7.0
    if min_mb is not None and min_mb > max_mb:
        min_mb, max_mb = max_mb, min_mb

    preferred_mb = args.preferred_mb
    if preferred_mb is None and args.target_range_mb:
        preferred_mb = max_mb
    if preferred_mb is not None and preferred_mb <= 0:
        raise ValueError("Preferred target must be positive.")

    return {
        "min_mb": min_mb,
        "max_mb": max_mb,
        "preferred_mb": preferred_mb,
        "min_bytes": int(min_mb * 1024 * 1024) if min_mb is not None else None,
        "max_bytes": int(max_mb * 1024 * 1024),
        "preferred_bytes": int(preferred_mb * 1024 * 1024) if preferred_mb is not None else None,
        "label": f"{min_mb:g}-{max_mb:g} MB" if min_mb is not None and min_mb != max_mb else f"{max_mb:g} MB",
    }


def file_size(path: Path) -> int:
    return path.stat().st_size


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


def render_pdf_page(pdf_path: Path, page_index: int, scale: float) -> Image.Image:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RuntimeError("pypdfium2 is required for render QA.") from exc

    document = pdfium.PdfDocument(str(pdf_path))
    try:
        return document[page_index].render(scale=scale).to_pil().convert("RGB")
    finally:
        document.close()


def compare_render_quality(
    original_path: Path,
    candidate_path: Path,
    *,
    scale: float,
    max_pages: int,
) -> dict[str, Any]:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise RuntimeError("pypdfium2 is required for render QA.") from exc

    original_doc = pdfium.PdfDocument(str(original_path))
    candidate_doc = pdfium.PdfDocument(str(candidate_path))
    try:
        original_pages = len(original_doc)
        candidate_pages = len(candidate_doc)
    finally:
        original_doc.close()
        candidate_doc.close()

    page_count = min(original_pages, candidate_pages, max_pages)
    page_results: list[dict[str, Any]] = []
    worst_rms = 0.0
    worst_psnr = float("inf")

    for page_index in range(page_count):
        original_image = render_pdf_page(original_path, page_index, scale)
        candidate_image = render_pdf_page(candidate_path, page_index, scale)
        if original_image.size != candidate_image.size:
            page_results.append(
                {
                    "page": page_index + 1,
                    "same_size": False,
                    "original_size": original_image.size,
                    "candidate_size": candidate_image.size,
                }
            )
            worst_rms = float("inf")
            worst_psnr = 0.0
            continue

        diff = ImageChops.difference(original_image, candidate_image)
        stat = ImageStat.Stat(diff)
        rms = (sum(value * value for value in stat.rms) / len(stat.rms)) ** 0.5
        mse = rms * rms
        psnr = float("inf") if mse == 0 else 20 * math.log10(255.0 / math.sqrt(mse))
        worst_rms = max(worst_rms, rms)
        worst_psnr = min(worst_psnr, psnr)
        page_results.append(
            {
                "page": page_index + 1,
                "same_size": True,
                "rms": round(rms, 6),
                "psnr": "inf" if math.isinf(psnr) else round(psnr, 3),
            }
        )

    return {
        "original_pages": original_pages,
        "candidate_pages": candidate_pages,
        "compared_pages": page_count,
        "worst_rms": "inf" if math.isinf(worst_rms) else round(worst_rms, 6),
        "worst_psnr": "inf" if math.isinf(worst_psnr) else round(worst_psnr, 3),
        "pages": page_results,
    }


def mark_render_quality(
    result: dict[str, Any],
    original_path: Path,
    *,
    render_qa: bool,
    min_render_psnr: float | None,
    max_render_rms: float | None,
    qa_scale: float,
    qa_max_pages: int,
) -> dict[str, Any]:
    result["quality_ok"] = True
    if not render_qa:
        return result

    try:
        qa = compare_render_quality(original_path, Path(result["path"]), scale=qa_scale, max_pages=qa_max_pages)
    except Exception as exc:  # noqa: BLE001
        result["quality_ok"] = False
        result.setdefault("warnings", []).append(f"Render QA unavailable; rejected lossy candidate: {exc}")
        return result

    result["render_qa"] = qa
    worst_psnr = qa["worst_psnr"]
    worst_rms = qa["worst_rms"]
    numeric_psnr = float("inf") if isinstance(worst_psnr, str) else float(worst_psnr)
    numeric_rms = float("inf") if isinstance(worst_rms, str) else float(worst_rms)

    if min_render_psnr is not None and numeric_psnr < min_render_psnr:
        result["quality_ok"] = False
        result.setdefault("warnings", []).append(
            f"Rejected candidate: render PSNR {numeric_psnr:.2f} is below {min_render_psnr:.2f}."
        )
    if max_render_rms is not None and numeric_rms > max_render_rms:
        result["quality_ok"] = False
        result.setdefault("warnings", []).append(
            f"Rejected candidate: render RMS {numeric_rms:.2f} is above {max_render_rms:.2f}."
        )
    return result


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


def unique_warnings(warnings: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        unique.append(warning)
    return unique


def object_value(value: Any) -> Any:
    try:
        return value.get_object()
    except Exception:  # noqa: BLE001 - feature detection should stay best-effort.
        return value


def count_items(value: Any) -> int:
    value = object_value(value)
    if value is None:
        return 0
    try:
        return len(value)
    except TypeError:
        return 1


def inspect_pdf_features(input_path: Path) -> dict[str, Any]:
    """Best-effort PDF feature audit used for warnings and audit-only mode."""

    warnings: list[str] = []
    features: dict[str, Any] = {
        "input": str(input_path),
        "input_bytes": file_size(input_path),
        "input_mb": round(bytes_to_mb(file_size(input_path)), 3),
        "encrypted": False,
        "pdf_version": None,
        "pages": None,
        "forms": False,
        "annotations": 0,
        "transparency": False,
        "masks": False,
        "uncommon_color_spaces": [],
        "small_raster_images": 0,
        "bilevel_images": 0,
        "image_count": 0,
        "largest_images": [],
        "private_payload_indicators": {},
        "warnings": warnings,
    }

    try:
        reader = PdfReader(str(input_path))
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Could not fully inspect PDF before optimization: {exc}")
        return features

    features["encrypted"] = reader.is_encrypted
    features["pdf_version"] = getattr(reader, "pdf_header", None)
    if reader.is_encrypted:
        warnings.append("Encrypted PDF detected. Unlock the PDF before optimization.")
        return features

    root = object_value(reader.trailer.get("/Root", {}))
    features["forms"] = bool(root.get("/AcroForm")) if hasattr(root, "get") else False
    private_counts: Counter[str] = Counter()
    uncommon_spaces: set[str] = set()
    largest_images: list[dict[str, Any]] = []

    try:
        pages = list(reader.pages)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Could not enumerate pages during feature detection: {exc}")
        return features

    features["pages"] = len(pages)
    for page in pages:
        for key in PRIVATE_PAGE_KEYS:
            if NameObject(key) in page:
                private_counts[key] += 1

        annotations = page.get("/Annots")
        features["annotations"] += count_items(annotations)

        resources = object_value(page.get("/Resources", {}))
        if not hasattr(resources, "get"):
            continue
        if resources.get("/ExtGState"):
            features["transparency"] = True

        xobjects = object_value(resources.get("/XObject", {}))
        if not hasattr(xobjects, "items"):
            continue
        for _, raw_xobject in xobjects.items():
            xobject = object_value(raw_xobject)
            if not hasattr(xobject, "get") or xobject.get("/Subtype") != "/Image":
                continue
            width = int(xobject.get("/Width", 0) or 0)
            height = int(xobject.get("/Height", 0) or 0)
            encoded_size = len(getattr(xobject, "_data", b"") or b"")
            bits = int(xobject.get("/BitsPerComponent", 0) or 0)
            color_space = str(xobject.get("/ColorSpace", "unknown"))

            features["image_count"] += 1
            if width * height < 120_000:
                features["small_raster_images"] += 1
            if bits == 1:
                features["bilevel_images"] += 1
            if xobject.get("/SMask") or xobject.get("/Mask"):
                features["masks"] = True
            if color_space not in {"/DeviceRGB", "/DeviceGray", "/DeviceCMYK", "unknown"}:
                uncommon_spaces.add(color_space)
            largest_images.append(
                {
                    "width": width,
                    "height": height,
                    "encoded_bytes": encoded_size,
                    "color_space": color_space,
                    "bits_per_component": bits or None,
                }
            )

    for key in PRIVATE_ROOT_KEYS:
        if hasattr(root, "get") and root.get(key):
            private_counts[f"root {key}"] += 1

    features["private_payload_indicators"] = dict(private_counts)
    features["uncommon_color_spaces"] = sorted(uncommon_spaces)
    features["largest_images"] = sorted(
        largest_images,
        key=lambda item: item["encoded_bytes"],
        reverse=True,
    )[:5]

    if features["forms"]:
        warnings.append("Form fields detected. Check the optimized copy before sending.")
    if features["annotations"]:
        warnings.append("Annotations detected. Check comments, links, and markup in the optimized copy.")
    if features["transparency"]:
        warnings.append("Transparency or blend state resources detected; conservative image handling is recommended.")
    if features["masks"]:
        warnings.append("Image masks detected; transparent images may be skipped unless --flatten-alpha is used.")
    if features["uncommon_color_spaces"]:
        warnings.append("Uncommon image color spaces detected; recompression may be conservative.")
    if features["small_raster_images"]:
        warnings.append("Small raster images detected; these are protected because recompression can damage detail.")
    if features["bilevel_images"]:
        warnings.append("Bilevel scan images detected; these are skipped by image recompression.")
    if features["private_payload_indicators"]:
        warnings.append("Private creator metadata/payload indicators detected; structural cleanup may help.")

    return features


def audit_pdf(input_path: Path) -> dict[str, Any]:
    audit = inspect_pdf_features(input_path)
    if audit["encrypted"]:
        audit["recommended_profile"] = None
        audit["structural_cleanup_likely"] = False
        audit["image_recompression_likely_required"] = False
        return audit

    private_count = sum(audit["private_payload_indicators"].values())
    image_count = int(audit["image_count"] or 0)
    audit["structural_cleanup_likely"] = private_count > 0
    audit["image_recompression_likely_required"] = image_count > 0
    if audit["transparency"] or audit["small_raster_images"] or audit["masks"]:
        audit["recommended_profile"] = "quality"
    elif image_count:
        audit["recommended_profile"] = "balanced"
    else:
        audit["recommended_profile"] = "balanced"
    return audit


def optimize(args: argparse.Namespace) -> dict[str, Any]:
    args = apply_profile_defaults(args)
    input_path = Path(args.input_pdf).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_path}")
    output_path = output_path_for(input_path, args.output_pdf)
    if input_path == output_path:
        raise ValueError("Output path must be different from input path.")
    if output_path.exists() and not args.force:
        raise FileExistsError(f"Output already exists: {output_path}. Use --force to replace it.")

    target = resolve_target_window(args)
    min_target_bytes = target["min_bytes"]
    max_target_bytes = target["max_bytes"]
    preferred_target_bytes = target["preferred_bytes"]
    inspection = inspect_pdf_features(input_path)
    if inspection["encrypted"]:
        raise PdfReadError("Encrypted PDFs must be unlocked before optimization.")
    all_warnings: list[str] = list(inspection.get("warnings", []))
    results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="pdf-email-opt-") as tmp_name:
        tmp_dir = Path(tmp_name)
        cleanup_path = tmp_dir / "cleanup.pdf"
        cleanup = write_candidate(
            input_path,
            cleanup_path,
            strip_private=not args.no_strip_private,
            image_quality=None,
            long_edge=None,
            min_image_pixels=args.min_image_pixels,
            min_image_bytes=args.min_image_bytes,
            flatten_alpha=args.flatten_alpha,
        )
        cleanup["strategy"] = "structural-cleanup"
        cleanup["quality_ok"] = True
        results.append(cleanup)

        if args.pikepdf != "never":
            pikepdf_path = tmp_dir / "pikepdf.pdf"
            pikepdf_result = pikepdf_structural_optimize(cleanup_path, pikepdf_path, warnings=all_warnings)
            if pikepdf_result is not None:
                pikepdf_candidate = {
                    "path": pikepdf_result["path"],
                    "size_bytes": pikepdf_result["size_bytes"],
                    "pages": cleanup["pages"],
                    "compressed_pages": cleanup.get("compressed_pages"),
                    "private_removed": cleanup.get("private_removed", {}),
                    "image_stats": None,
                    "strategy": "pikepdf-structural",
                    "quality_ok": True,
                    "warnings": pikepdf_result.get("warnings", []),
                }
                results.append(pikepdf_candidate)

        lossless_floor = min(result["size_bytes"] for result in results)
        if lossless_floor > max_target_bytes and not args.no_image_recompress:
            quality_values = normalize_quality_ladder(
                args.image_quality,
                args.min_image_quality,
                profile_value(args, "quality_ladder"),
            )
            long_edges = normalize_long_edges(
                args.long_edge,
                args.min_long_edge,
                profile_value(args, "long_edge_ladder"),
            )
            for long_edge in long_edges:
                for quality in quality_values:
                    candidate_path = tmp_dir / f"images_q{quality}_edge{long_edge or 'native'}.pdf"
                    candidate = write_candidate(
                        input_path,
                        candidate_path,
                        strip_private=not args.no_strip_private,
                        image_quality=quality,
                        long_edge=long_edge,
                        min_image_pixels=args.min_image_pixels,
                        min_image_bytes=args.min_image_bytes,
                        flatten_alpha=args.flatten_alpha,
                    )
                    candidate["strategy"] = "image-recompress"
                    mark_render_quality(
                        candidate,
                        input_path,
                        render_qa=args.render_qa,
                        min_render_psnr=args.min_render_psnr,
                        max_render_rms=args.max_render_rms,
                        qa_scale=args.qa_scale,
                        qa_max_pages=args.qa_max_pages,
                    )
                    results.append(candidate)
                    if candidate.get("quality_ok", True) and result_in_target_window(
                        candidate,
                        min_target_bytes,
                        max_target_bytes,
                    ):
                        break
                if results[-1].get("quality_ok", True) and result_in_target_window(
                    results[-1],
                    min_target_bytes,
                    max_target_bytes,
                ):
                    break

        best = choose_best_result(
            results,
            min_bytes=min_target_bytes,
            max_bytes=max_target_bytes,
            preferred_bytes=preferred_target_bytes,
        )
        shutil.copy2(best["path"], output_path)
        best = {**best, "path": str(output_path)}

        if best["size_bytes"] > max_target_bytes and args.ghostscript != "never":
            gs_input = output_path if args.ghostscript == "auto" else input_path
            gs_result = run_ghostscript(gs_input, output_path, target_mb=target["max_mb"], warnings=all_warnings)
            if gs_result and gs_result["size_bytes"] < best["size_bytes"]:
                best = {**gs_result, "strategy": "ghostscript-fallback"}

    for result in results:
        all_warnings.extend(result.get("warnings", []))
    output_bytes = file_size(output_path)
    within_target_range = result_in_target_window({"size_bytes": output_bytes}, min_target_bytes, max_target_bytes)
    if output_bytes > max_target_bytes and args.profile == "quality":
        all_warnings.append(
            f"Target not met. The requested {target['label']} target conflicts with the selected quality profile. "
            f"Output is {bytes_to_mb(output_bytes):.2f} MB. To go smaller, rerun with --profile aggressive, "
            "split the PDF, remove pages, or accept lower image fidelity."
        )
    if min_target_bytes is not None and output_bytes < min_target_bytes:
        all_warnings.append(
            "Output is below the requested range. It was not padded upward because adding bytes would not improve email quality."
        )
    if (
        min_target_bytes is None
        and preferred_target_bytes is not None
        and output_bytes < int(preferred_target_bytes * 0.9)
    ):
        all_warnings.append(
            "Output is well below the preferred size. It was not padded upward because adding bytes would not improve email quality."
        )
    all_warnings = unique_warnings(all_warnings)

    summary = {
        "input": str(input_path),
        "output": str(output_path),
        "profile": args.profile,
        "input_bytes": file_size(input_path),
        "output_bytes": output_bytes,
        "input_mb": round(bytes_to_mb(file_size(input_path)), 3),
        "output_mb": round(bytes_to_mb(output_bytes), 3),
        "target_mb": target["max_mb"],
        "target_min_mb": target["min_mb"],
        "target_label": target["label"],
        "preferred_mb": target["preferred_mb"],
        "met_target": output_bytes <= max_target_bytes,
        "within_target_range": within_target_range,
        "strategy": best.get("strategy", "unknown"),
        "pages": best.get("pages"),
        "private_removed": best.get("private_removed", {}),
        "image_stats": best.get("image_stats"),
        "render_qa": best.get("render_qa"),
        "quality_ok": best.get("quality_ok", True),
        "feature_warnings": inspection,
        "warnings": all_warnings,
    }
    return summary


def print_summary(summary: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(summary, indent=2))
        return

    print(f"Input:  {summary['input']}")
    print(f"Output: {summary['output']}")
    print(f"Size:   {summary['input_mb']:.2f} MB -> {summary['output_mb']:.2f} MB")
    if summary.get("target_min_mb") is not None:
        target_status = "inside range" if summary["within_target_range"] else "outside range"
    else:
        target_status = "met" if summary["met_target"] else "not met"
    print(f"Target: {summary['target_label']} ({target_status})")
    if summary.get("preferred_mb") is not None:
        print(f"Preferred: {summary['preferred_mb']:.2f} MB")
    print(f"Profile: {summary['profile']} ({'quality ok' if summary['quality_ok'] else 'quality rejected'})")
    print(f"Mode:   {summary['strategy']}")
    if summary.get("private_removed"):
        removed = ", ".join(f"{key} x{value}" for key, value in summary["private_removed"].items())
        print(f"Removed private data: {removed}")
    if summary.get("image_stats"):
        stats = summary["image_stats"]
        print(
            "Images: "
            f"{stats['changed']} changed, {stats['skipped']} skipped, "
            f"{fmt_mb(stats['before_bytes'])} -> {fmt_mb(stats['after_bytes'])}"
        )
        if stats.get("skipped_small") or stats.get("skipped_low_value"):
            print(
                "Protected images: "
                f"{stats.get('skipped_small', 0)} small, "
                f"{stats.get('skipped_low_value', 0)} low-savings"
            )
    if summary.get("render_qa"):
        qa = summary["render_qa"]
        print(f"Render QA: worst RMS {qa['worst_rms']}, worst PSNR {qa['worst_psnr']}")
    if summary.get("report"):
        print(f"Report: {summary['report']}")
    for warning in summary.get("warnings", []):
        print(f"Warning: {warning}", file=sys.stderr)


def build_markdown_report(summary: dict[str, Any]) -> str:
    target_status = "inside range" if summary["within_target_range"] else "outside range"
    if summary.get("target_min_mb") is None:
        target_status = "met" if summary["met_target"] else "not met"

    lines = [
        "# PDF Email Optimizer Report",
        "",
        f"- Input: `{summary['input']}`",
        f"- Output: `{summary['output']}`",
        f"- Size: {summary['input_mb']:.2f} MB -> {summary['output_mb']:.2f} MB",
        f"- Target: {summary['target_label']} ({target_status})",
        f"- Profile: {summary['profile']}",
        f"- Strategy: {summary['strategy']}",
        f"- Quality OK: {'yes' if summary['quality_ok'] else 'no'}",
    ]
    if summary.get("preferred_mb") is not None:
        lines.append(f"- Preferred size: {summary['preferred_mb']:.2f} MB")
    if summary.get("pages") is not None:
        lines.append(f"- Pages: {summary['pages']}")
    if summary.get("render_qa"):
        qa = summary["render_qa"]
        lines.extend(
            [
                "",
                "## Render QA",
                "",
                f"- Compared pages: {qa['compared_pages']}",
                f"- Worst RMS: {qa['worst_rms']}",
                f"- Worst PSNR: {qa['worst_psnr']}",
            ]
        )
    if summary.get("image_stats"):
        stats = summary["image_stats"]
        lines.extend(
            [
                "",
                "## Image Changes",
                "",
                f"- Images changed: {stats['changed']}",
                f"- Images skipped: {stats['skipped']}",
                f"- Encoded image bytes: {stats['before_bytes']} -> {stats['after_bytes']}",
                f"- JPEG quality tried: {stats['quality']}",
                f"- Long edge cap: {stats['long_edge'] or 'native'}",
            ]
        )
    if summary.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in summary["warnings"])
    if not summary["met_target"]:
        lines.extend(
            [
                "",
                "## Recommendation",
                "",
                "The requested target was not met with the selected quality constraints. "
                "Use a larger attachment target, split the PDF, remove pages, replace source images, "
                "or rerun with `--profile aggressive` only if visible quality loss is acceptable.",
            ]
        )
    return "\n".join(lines) + "\n"


def write_report(summary: dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(build_markdown_report(summary), encoding="utf-8")


def print_audit(summary: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(summary, indent=2))
        return

    print(f"Input:  {summary['input']}")
    print(f"Size:   {summary['input_mb']:.2f} MB")
    print(f"Pages:  {summary['pages'] if summary['pages'] is not None else 'unknown'}")
    print(f"PDF:    {summary['pdf_version'] or 'unknown'}")
    print(f"Images: {summary['image_count']}")
    print(f"Forms:  {'yes' if summary['forms'] else 'no'}")
    print(f"Annotations: {summary['annotations']}")
    print(f"Recommended profile: {summary.get('recommended_profile') or 'none'}")
    print(f"Structural cleanup likely: {'yes' if summary.get('structural_cleanup_likely') else 'no'}")
    print(f"Image recompression likely required: {'yes' if summary.get('image_recompression_likely_required') else 'no'}")
    for warning in summary.get("warnings", []):
        print(f"Warning: {warning}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_pdf", help="Source PDF.")
    parser.add_argument("output_pdf", nargs="?", help="Optimized PDF path. Defaults to *_email.pdf next to input.")
    parser.add_argument("--target-mb", type=float, default=7.0, help="Maximum desired output size in MB.")
    parser.add_argument("--target", help="Maximum desired output size, such as 7mb. Ranges are accepted too.")
    parser.add_argument("--target-min-mb", type=float, default=None, help="Optional lower bound for a target size range.")
    parser.add_argument(
        "--target-range-mb",
        "--range",
        dest="target_range_mb",
        help="Target size range in MB, such as 5-7, 5:7, or 5,7. The upper value is still a hard ceiling.",
    )
    parser.add_argument(
        "--preferred-mb",
        type=float,
        default=None,
        help="Preferred output size in MB when multiple acceptable candidates fit the target.",
    )
    profile_group = parser.add_mutually_exclusive_group()
    profile_group.add_argument(
        "--profile",
        choices=tuple(PROFILE_DEFAULTS),
        help="Optimization profile. Use quality when image fidelity matters; aggressive may visibly degrade images.",
    )
    profile_group.add_argument("--quality", dest="profile", action="store_const", const="quality", help="Shortcut for --profile quality.")
    profile_group.add_argument("--balanced", dest="profile", action="store_const", const="balanced", help="Shortcut for --profile balanced.")
    profile_group.add_argument("--aggressive", dest="profile", action="store_const", const="aggressive", help="Shortcut for --profile aggressive.")
    parser.set_defaults(profile="balanced")
    parser.add_argument("--image-quality", type=int, default=None, help="Starting JPEG quality for image recompression.")
    parser.add_argument("--min-image-quality", type=int, default=None, help="Lowest JPEG quality to try.")
    parser.add_argument("--long-edge", type=int, default=None, help="First long-edge pixel cap to try for images.")
    parser.add_argument("--min-long-edge", type=int, default=None, help="Lowest long-edge pixel cap to try.")
    parser.add_argument("--min-image-pixels", type=int, default=None, help="Skip images smaller than this pixel count.")
    parser.add_argument("--min-image-bytes", type=int, default=None, help="Skip images smaller than this encoded byte size.")
    parser.add_argument("--no-strip-private", action="store_true", help="Keep private creator/editing payloads.")
    parser.add_argument("--no-image-recompress", action="store_true", help="Only perform structural cleanup.")
    parser.add_argument("--flatten-alpha", action="store_true", help="Allow transparent images to be flattened onto white.")
    parser.add_argument("--ghostscript", choices=("auto", "always", "never"), default=None, help="Use Ghostscript fallback.")
    parser.add_argument(
        "--pikepdf",
        dest="pikepdf",
        choices=("auto", "never"),
        default=None,
        help="Use the optional pikepdf/qpdf lossless structural backend when available.",
    )
    parser.add_argument(
        "--no-pikepdf",
        dest="pikepdf",
        action="store_const",
        const="never",
        help="Disable the pikepdf/qpdf structural backend.",
    )
    parser.add_argument("--render-qa", dest="render_qa", action="store_true", default=None, help="Reject lossy candidates that fail render QA.")
    parser.add_argument("--skip-render-qa", dest="render_qa", action="store_false", help="Disable render QA.")
    parser.add_argument("--min-render-psnr", type=float, default=None, help="Minimum render PSNR for render QA.")
    parser.add_argument("--max-render-rms", type=float, default=None, help="Maximum render RMS difference for render QA.")
    parser.add_argument("--qa-scale", type=float, default=None, help="Render scale used for QA.")
    parser.add_argument("--qa-max-pages", type=int, default=None, help="Maximum pages to render for QA.")
    parser.add_argument("--force", action="store_true", help="Replace output if it already exists.")
    parser.add_argument("--audit", action="store_true", help="Inspect a PDF and recommend an optimization strategy without writing output.")
    parser.add_argument("--report", help="Write a Markdown optimization report to this path.")
    parser.add_argument("--json", action="store_true", help="Print JSON summary.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.audit:
            summary = audit_pdf(Path(args.input_pdf).expanduser().resolve())
            print_audit(summary, json_output=args.json)
            return 0
        summary = optimize(args)
        if args.report:
            report_path = Path(args.report).expanduser().resolve()
            write_report(summary, report_path)
            summary["report"] = str(report_path)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print_summary(summary, json_output=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

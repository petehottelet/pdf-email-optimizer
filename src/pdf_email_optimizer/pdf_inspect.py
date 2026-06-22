#!/usr/bin/env python3
"""Best-effort PDF feature inspection and audit recommendations.

Drives both ``--audit`` and the warnings attached to every optimize run. As of
v3.0.0 it also detects image stream encodings that the pypdf-based recompressor
can't process (JPEG2000 / CCITT / JBIG2) so the pipeline can route those inputs
to Ghostscript or ``--bilevel`` instead of leaving them silently unoptimized.
"""

from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.generic import NameObject

from .candidates import PRIVATE_PAGE_KEYS, PRIVATE_ROOT_KEYS
from .input_source import attach_source_metadata, resolve_input_source
from .utils import bytes_to_mb, count_items, file_size, object_value

# Image stream filters the pypdf image ladder cannot decode/replace. Detecting
# them lets the pipeline fall back to Ghostscript (or recommend --bilevel)
# instead of producing an output that ignored the heaviest images.
UNSUPPORTED_IMAGE_FILTERS = {
    "/JPXDecode": "jpeg2000_images",
    "/CCITTFaxDecode": "ccitt_images",
    "/JBIG2Decode": "jbig2_images",
}


def _filter_names(xobject: Any) -> list[str]:
    """Return the /Filter entries of an image XObject as a list of names.

    Normalises the three shapes pypdf can hand back: a single name, an array of
    names, or indirect references to either.
    """

    raw = object_value(xobject.get("/Filter")) if hasattr(xobject, "get") else None
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(object_value(item)) for item in raw]
    return [str(raw)]


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
        "jpeg2000_images": 0,
        "ccitt_images": 0,
        "jbig2_images": 0,
        "pypdf_unsupported_images": 0,
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
            filters = _filter_names(xobject)

            features["image_count"] += 1
            if width * height < 120_000:
                features["small_raster_images"] += 1
            if bits == 1:
                features["bilevel_images"] += 1
            if xobject.get("/SMask") or xobject.get("/Mask"):
                features["masks"] = True
            if color_space not in {"/DeviceRGB", "/DeviceGray", "/DeviceCMYK", "unknown"}:
                uncommon_spaces.add(color_space)

            unsupported_hit = False
            for filter_name, feature_key in UNSUPPORTED_IMAGE_FILTERS.items():
                if filter_name in filters:
                    features[feature_key] += 1
                    unsupported_hit = True
            if unsupported_hit:
                features["pypdf_unsupported_images"] += 1

            largest_images.append(
                {
                    "width": width,
                    "height": height,
                    "encoded_bytes": encoded_size,
                    "color_space": color_space,
                    "bits_per_component": bits or None,
                    "filters": filters,
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
    if features["pypdf_unsupported_images"]:
        warnings.append(
            "Images with encodings the built-in recompressor cannot process were detected "
            f"(JPEG2000 x{features['jpeg2000_images']}, CCITT x{features['ccitt_images']}, "
            f"JBIG2 x{features['jbig2_images']}). Ghostscript handles these at the page level; "
            "for typeset / line-art scans consider --bilevel."
        )
    if features["private_payload_indicators"]:
        warnings.append("Private creator metadata/payload indicators detected; structural cleanup may help.")

    return features


def recommend_strategy(features: dict[str, Any]) -> str | None:
    """Suggest a non-default strategy for inputs the pypdf ladder can't handle.

    Returns ``"bilevel"`` when CCITT/JBIG2 (typeset / line-art) dominate the
    unsupported images, ``"ghostscript"`` when any unsupported encoding is
    present, or ``None`` when the standard ladder is fine.
    """

    unsupported = int(features.get("pypdf_unsupported_images") or 0)
    if unsupported <= 0:
        return None
    line_art = int(features.get("ccitt_images") or 0) + int(features.get("jbig2_images") or 0)
    if line_art >= unsupported:
        return "bilevel"
    return "ghostscript"


def audit(input_path: Path | str) -> dict[str, Any]:
    source_path, working_pdf, source_metadata, temp_dir = resolve_input_source(str(input_path))
    try:
        result = inspect_pdf_features(working_pdf)
        if result["encrypted"]:
            result["recommended_profile"] = None
            result["recommended_strategy"] = None
            result["structural_cleanup_likely"] = False
            result["image_recompression_likely_required"] = False
            attach_source_metadata(result, source_metadata)
            return result

        private_count = sum(result["private_payload_indicators"].values())
        image_count = int(result["image_count"] or 0)
        result["structural_cleanup_likely"] = private_count > 0
        result["image_recompression_likely_required"] = image_count > 0
        if result["transparency"] or result["small_raster_images"] or result["masks"]:
            result["recommended_profile"] = "quality"
        elif image_count:
            result["recommended_profile"] = "balanced"
        else:
            result["recommended_profile"] = "balanced"
        result["recommended_strategy"] = recommend_strategy(result)
        attach_source_metadata(result, source_metadata)
        return result
    finally:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)


__all__ = [
    "UNSUPPORTED_IMAGE_FILTERS",
    "audit",
    "inspect_pdf_features",
    "recommend_strategy",
]

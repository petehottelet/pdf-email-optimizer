#!/usr/bin/env python3
"""Render before/after/diff gallery images for the README.

This script has two modes:

1. **Sample mode (default when ``benchmarks/results/samples.json`` exists):**
   Reads the per-sample results produced by ``benchmarks/run_samples.py`` and
   renders ``<sample_id>_before.png``, ``<sample_id>_after.png``, and
   ``<sample_id>_diff.png`` for every successful run, plus a stitched
   ``<sample_id>.png`` side-by-side image with size labels.

2. **Synthetic-fixture fallback:** if there is no sample results file, it falls
   back to a small set of synthetic fixtures from ``benchmarks/fixtures/`` so the
   gallery still regenerates in a clean clone.

Run::

    python benchmarks/make_gallery.py
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from PIL import Image, ImageChops, ImageDraw, ImageFont  # noqa: E402

from pdf_email_optimizer.optimizer import build_parser, optimize  # noqa: E402
from pdf_email_optimizer.render_qa import render_page  # noqa: E402

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "gallery"
SAMPLES_RESULTS = PROJECT_ROOT / "benchmarks" / "results" / "samples.json"
FIXTURE_DIR = PROJECT_ROOT / "benchmarks" / "fixtures"

THUMB_LONG_EDGE = 900
LABEL_HEIGHT = 56

# Fallback fixture cases (used only when samples.json is missing).
FALLBACK_CASES = [
    ("indesign_export", "balanced", 1.0, "InDesign-style export"),
    ("scanned_pdf", "balanced", 0.4, "Scanned document"),
    ("repeated_images", "balanced", 0.5, "Repeated images (dedupe)"),
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _thumbnail(image: Image.Image, long_edge: int = THUMB_LONG_EDGE) -> Image.Image:
    thumb = image.copy()
    thumb.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
    return thumb


def _amplified_diff(original: Image.Image, optimized: Image.Image) -> Image.Image:
    """Return a high-contrast difference image (multiplier 8x), matching pdf-email-render-compare."""

    if original.size != optimized.size:
        return Image.new("RGB", original.size, (0, 0, 0))
    diff = ImageChops.difference(original, optimized)
    return diff.point(lambda value: min(255, value * 8))


def _side_by_side(original: Image.Image, optimized: Image.Image, *, left: str, right: str) -> Image.Image:
    left_img = _thumbnail(original)
    right_img = _thumbnail(optimized)
    height = max(left_img.height, right_img.height)
    gap = 24
    width = left_img.width + right_img.width + gap
    canvas = Image.new("RGB", (width, height + LABEL_HEIGHT), "white")
    canvas.paste(left_img, (0, LABEL_HEIGHT))
    canvas.paste(right_img, (left_img.width + gap, LABEL_HEIGHT))
    draw = ImageDraw.Draw(canvas)
    font = _load_font(22)
    draw.text((8, 16), left, fill=(20, 20, 20), font=font)
    draw.text((left_img.width + gap + 8, 16), right, fill=(20, 20, 20), font=font)
    return canvas


def _render_pair(source: Path, optimized: Path) -> tuple[Image.Image, Image.Image] | None:
    try:
        original_img = render_page(source, 0, scale=2.0)
        optimized_img = render_page(optimized, 0, scale=2.0)
    except Exception as exc:  # noqa: BLE001
        print(f"  render failed: {exc}", flush=True)
        return None
    return original_img, optimized_img


def _write_gallery_set(
    sample_id: str,
    original_img: Image.Image,
    optimized_img: Image.Image,
    *,
    input_mb: float,
    output_mb: float,
    reduction_percent: float,
    output_dir: Path,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    before_path = output_dir / f"{sample_id}_before.png"
    after_path = output_dir / f"{sample_id}_after.png"
    diff_path = output_dir / f"{sample_id}_diff.png"
    combined_path = output_dir / f"{sample_id}.png"

    _thumbnail(original_img).save(before_path, optimize=True)
    _thumbnail(optimized_img).save(after_path, optimize=True)
    _thumbnail(_amplified_diff(original_img, optimized_img)).save(diff_path, optimize=True)

    combined = _side_by_side(
        original_img,
        optimized_img,
        left=f"Original - {input_mb:.2f} MB",
        right=f"Email copy - {output_mb:.2f} MB ({reduction_percent:.1f}% smaller)",
    )
    combined.save(combined_path, optimize=True)
    return {
        "before": before_path.name,
        "after": after_path.name,
        "diff": diff_path.name,
        "combined": combined_path.name,
    }


def _build_from_samples(samples: list[dict[str, Any]], output_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for sample in samples:
        if sample.get("status") != "ok":
            results.append(
                {
                    "case": sample["sample_id"],
                    "status": sample.get("status", "skipped"),
                    "reason": sample.get("reason", "no output"),
                }
            )
            continue

        source = Path(sample["source_path"])
        optimized = Path(sample["output_path"])
        if not source.exists() or not optimized.exists():
            results.append(
                {
                    "case": sample["sample_id"],
                    "status": "skipped",
                    "reason": "source or output missing on disk",
                }
            )
            continue

        print(f"[{sample['sample_id']}] rendering before/after/diff ...", flush=True)
        rendered = _render_pair(source, optimized)
        if rendered is None:
            results.append(
                {
                    "case": sample["sample_id"],
                    "status": "skipped",
                    "reason": "render failure",
                }
            )
            continue

        original_img, optimized_img = rendered
        # Headline numbers use the office-doc source when present so the
        # combined image reads "Original - 36 MB .pptx" rather than the
        # intermediate converted PDF size.
        if sample.get("source_office_mb") is not None:
            display_input_mb = float(sample["source_office_mb"])
            display_reduction = float(sample.get("headline_reduction_percent", sample["reduction_percent"]))
        else:
            display_input_mb = float(sample["input_mb"])
            display_reduction = float(sample["reduction_percent"])

        paths = _write_gallery_set(
            sample["sample_id"],
            original_img,
            optimized_img,
            input_mb=display_input_mb,
            output_mb=sample["output_mb"],
            reduction_percent=display_reduction,
            output_dir=output_dir,
        )
        result = {
            "case": sample["sample_id"],
            "label": sample.get("label", sample["sample_id"]),
            "category": sample.get("category"),
            "status": "ok",
            "input_mb": sample["input_mb"],
            "output_mb": sample["output_mb"],
            "reduction_percent": sample["reduction_percent"],
            "headline_reduction_percent": sample.get("headline_reduction_percent"),
            "source_office_name": sample.get("source_office_name"),
            "source_office_mb": sample.get("source_office_mb"),
            "profile": sample.get("profile"),
            "strategy": sample.get("strategy"),
            "met_target": sample.get("met_target"),
            "worst_psnr": sample.get("worst_psnr"),
            "worst_rms": sample.get("worst_rms"),
            **paths,
        }
        results.append(result)
        print(
            f"  -> {paths['before']}, {paths['after']}, {paths['diff']}, {paths['combined']}",
            flush=True,
        )
    return results


def _build_from_fixtures(output_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name, profile, target_mb, label in FALLBACK_CASES:
        source = FIXTURE_DIR / f"{name}.pdf"
        if not source.exists():
            results.append({"case": name, "status": "skipped", "reason": "fixture missing"})
            continue

        print(f"[{name}] fallback fixture run ({label}) ...", flush=True)
        with tempfile.TemporaryDirectory(prefix="gallery-") as tmp_name:
            optimized = Path(tmp_name) / f"{name}_email.pdf"
            args = build_parser().parse_args(
                [
                    str(source),
                    str(optimized),
                    "--target-mb",
                    str(target_mb),
                    "--profile",
                    profile,
                    "--force",
                    "--skip-render-qa",
                ]
            )
            summary = optimize(args)
            rendered = _render_pair(source, optimized)
            if rendered is None:
                results.append({"case": name, "status": "skipped", "reason": "render failure"})
                continue

            original_img, optimized_img = rendered
            input_mb = summary["input_mb"]
            output_mb = summary["output_mb"]
            reduction = round((1 - output_mb / input_mb) * 100, 1) if input_mb else 0.0
            paths = _write_gallery_set(
                name,
                original_img,
                optimized_img,
                input_mb=input_mb,
                output_mb=output_mb,
                reduction_percent=reduction,
                output_dir=output_dir,
            )
        results.append(
            {
                "case": name,
                "label": label,
                "status": "ok",
                "input_mb": input_mb,
                "output_mb": output_mb,
                "reduction_percent": reduction,
                "profile": profile,
                "strategy": summary["strategy"],
                "met_target": summary["met_target"],
                **paths,
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--samples", default=str(SAMPLES_RESULTS))
    parser.add_argument(
        "--mode",
        choices=("auto", "samples", "fixtures"),
        default="auto",
        help="auto picks samples when samples.json exists, otherwise the synthetic fallback set.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    samples_path = Path(args.samples).expanduser().resolve()

    use_samples = args.mode == "samples" or (args.mode == "auto" and samples_path.exists())
    if use_samples and samples_path.exists():
        print(f"Using samples results: {samples_path}", flush=True)
        samples = json.loads(samples_path.read_text(encoding="utf-8"))
        results = _build_from_samples(samples, output_dir)
    elif use_samples:
        print(f"Requested sample mode but {samples_path} not found; falling back to fixtures.", flush=True)
        results = _build_from_fixtures(output_dir)
    else:
        print("Using synthetic fixture fallback set.", flush=True)
        results = _build_from_fixtures(output_dir)

    index_path = output_dir / "gallery.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote {index_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

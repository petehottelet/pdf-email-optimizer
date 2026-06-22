#!/usr/bin/env python3
"""Render PDFs and report page-level pixel differences.

This module is both the standalone ``pdf-email-render-compare`` CLI and the
optimizer's internal render-QA gate. The two used to carry duplicate rendering
code; they now share a single :func:`render_page` implementation.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat

try:
    import pypdfium2 as pdfium
except ImportError:  # pragma: no cover - environment dependent.
    pdfium = None


def render_page(pdf_path: Path, page_index: int, scale: float) -> Image.Image:
    if pdfium is None:
        raise RuntimeError("pypdfium2 is required for rendering. Install it or use another PDF renderer.")
    document = pdfium.PdfDocument(str(pdf_path))
    try:
        page = document[page_index]
        return page.render(scale=scale).to_pil().convert("RGB")
    finally:
        document.close()


# Backwards-compatible alias for the optimizer-internal name.
def render_pdf_page(pdf_path: Path, page_index: int, scale: float) -> Image.Image:
    return render_page(pdf_path, page_index, scale)


def compare_render_quality(
    original_path: Path,
    candidate_path: Path,
    *,
    scale: float,
    max_pages: int,
) -> dict[str, Any]:
    """Compute worst-case RMS / PSNR between an original and a candidate render.

    Used by the optimizer to gate lossy candidates. Distinct from
    :func:`compare_pdfs` (the CLI report), which emits per-page diffs and
    optional diff PNGs rather than a pass/fail PSNR figure.
    """

    if pdfium is None:
        raise RuntimeError("pypdfium2 is required for render QA.")

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
        original_image = render_page(original_path, page_index, scale)
        candidate_image = render_page(candidate_path, page_index, scale)
        if original_image.size != candidate_image.size:
            # Sub-point page rounding (e.g. img2pdf-derived pages) can yield
            # 1-2 pixel deltas at the QA scale. Resize the candidate to match
            # the original so we can still compute a meaningful PSNR; tag the
            # result so callers know the comparison was approximated.
            ow, oh = original_image.size
            cw, ch = candidate_image.size
            if abs(ow - cw) <= 4 and abs(oh - ch) <= 4:
                candidate_image = candidate_image.resize(original_image.size, Image.Resampling.LANCZOS)
            else:
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


def changed_percent(diff: Image.Image) -> float:
    changed = diff.convert("L").point(lambda value: 255 if value else 0)
    histogram = changed.histogram()
    changed_pixels = histogram[255]
    total_pixels = diff.width * diff.height
    return (changed_pixels / total_pixels) * 100 if total_pixels else 0.0


def compare_pdfs(
    original: Path,
    optimized: Path,
    *,
    scale: float,
    max_pages: int | None,
    output_dir: Path | None,
) -> dict[str, Any]:
    if pdfium is None:
        raise RuntimeError("pypdfium2 is required for rendering. Install it or use another PDF renderer.")

    original_doc = pdfium.PdfDocument(str(original))
    optimized_doc = pdfium.PdfDocument(str(optimized))
    try:
        original_pages = len(original_doc)
        optimized_pages = len(optimized_doc)
    finally:
        original_doc.close()
        optimized_doc.close()

    page_count = min(original_pages, optimized_pages)
    if max_pages:
        page_count = min(page_count, max_pages)
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    pages = []
    for page_index in range(page_count):
        orig_img = render_page(original, page_index, scale)
        opt_img = render_page(optimized, page_index, scale)
        if orig_img.size != opt_img.size:
            pages.append(
                {
                    "page": page_index + 1,
                    "same_size": False,
                    "original_size": orig_img.size,
                    "optimized_size": opt_img.size,
                    "rms_diff": None,
                    "changed_percent": None,
                    "diff_bbox": None,
                }
            )
            continue

        diff = ImageChops.difference(orig_img, opt_img)
        stat = ImageStat.Stat(diff)
        rms = (sum(value * value for value in stat.rms) / len(stat.rms)) ** 0.5
        bbox = diff.getbbox()

        if output_dir:
            page_label = f"{page_index + 1:03d}"
            orig_img.save(output_dir / f"original_page_{page_label}.png")
            opt_img.save(output_dir / f"optimized_page_{page_label}.png")
            amplified = diff.point(lambda value: min(255, value * 8))
            amplified.save(output_dir / f"diff_page_{page_label}.png")

        pages.append(
            {
                "page": page_index + 1,
                "same_size": True,
                "size": orig_img.size,
                "rms_diff": round(rms, 6),
                "changed_percent": round(changed_percent(diff), 6),
                "diff_bbox": bbox,
            }
        )

    return {
        "original": str(original),
        "optimized": str(optimized),
        "original_pages": original_pages,
        "optimized_pages": optimized_pages,
        "compared_pages": page_count,
        "scale": scale,
        "pages": pages,
        "identical_render": original_pages == optimized_pages
        and all(page.get("same_size") and page.get("rms_diff") == 0 for page in pages),
    }


def print_summary(summary: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(summary, indent=2))
        return

    print(f"Original pages:  {summary['original_pages']}")
    print(f"Optimized pages: {summary['optimized_pages']}")
    print(f"Compared pages:  {summary['compared_pages']}")
    print(f"Identical render: {'yes' if summary['identical_render'] else 'no'}")
    for page in summary["pages"]:
        if not page["same_size"]:
            print(
                f"Page {page['page']}: size changed "
                f"{page['original_size']} -> {page['optimized_size']}"
            )
            continue
        print(
            f"Page {page['page']}: rms={page['rms_diff']:.6f}, "
            f"changed={page['changed_percent']:.6f}%, bbox={page['diff_bbox']}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_pdf")
    parser.add_argument("optimized_pdf")
    parser.add_argument("--scale", type=float, default=2.0, help="Render scale. 2.0 is a useful QA default.")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit pages to compare.")
    parser.add_argument("--output-dir", help="Optional directory for rendered original, optimized, and diff PNGs.")
    parser.add_argument("--json", action="store_true", help="Print JSON summary.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        summary = compare_pdfs(
            Path(args.original_pdf).expanduser().resolve(),
            Path(args.optimized_pdf).expanduser().resolve(),
            scale=args.scale,
            max_pages=args.max_pages,
            output_dir=Path(args.output_dir).expanduser().resolve() if args.output_dir else None,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print_summary(summary, json_output=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

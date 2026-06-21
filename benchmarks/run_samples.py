#!/usr/bin/env python3
"""Run pdf-email-optimizer end-to-end against the real-world sample documents.

This drives the optimizer on every PDF in the converted-samples directory using
a per-sample profile/target, captures size/reduction/PSNR/RMS/runtime, and
writes a single results file the gallery, chart, and comparison tooling can
consume. All large source PDFs and most optimized outputs stay outside the
repo; only the resulting metrics file plus deliberately small optimized PDFs
are committed.

Usage::

    python benchmarks/run_samples.py
    python benchmarks/run_samples.py --input "00_project_files/Converted PDFs" --output benchmarks/results/samples.json

The results file is consumed by ``make_gallery.py``, ``make_charts.py``, and
the README/comparison docs.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from pdf_email_optimizer.optimizer import (  # noqa: E402
    build_parser,
    compare_render_quality,
    optimize,
)

GHOSTSCRIPT_DEFAULT = r"C:\Program Files\gs\gs10.07.1\bin"


@dataclass
class SamplePlan:
    """Configuration for one real-world sample run."""

    sample_id: str
    label: str
    category: str
    source_name: str
    target_mb: float
    profile: str
    description: str
    # Optional hints that pre-cap the recompression ladder, used to keep
    # showcase runs from grinding through obviously-wasteful candidates.
    long_edge: int | None = None
    image_quality: int | None = None
    # Some real-world inputs are degenerate for the image-recompress ladder
    # (e.g. PowerPoint exports with thousands of glyph rasters). For those,
    # disable image recompression entirely and rely on structural cleanup.
    no_image_recompress: bool = False
    # For inputs the Python image-recompress ladder can't safely process (PPTX
    # exports with thousands of tiny glyph rasters - OOM territory), shell out
    # to Ghostscript instead. The PostScript interpreter handles those images
    # at the page-stream level without loading thousands of PIL objects.
    # When set, this overrides the Python optimizer entirely.
    ghostscript_image_dpi: int | None = None
    ghostscript_jpeg_quality: int | None = None
    # For archival typeset / line-art scans, route through the bilevel CCITT
    # G4 (fax) strategy at this DPI. Destructive (drops all color/grayscale
    # info) so it's never auto-selected - it's an explicit per-sample opt-in.
    bilevel_dpi: int | None = None
    bilevel_threshold: int | None = None
    # When the user's starting point is an office document, point this at the
    # original .pptx/.xlsx/.docx in ``00_project_files/Sample Documents/`` so
    # the chart/table headline reports "this 36 MB PPTX shrank to a 2 MB
    # email-safe PDF" rather than the intermediate converted-PDF size.
    source_office_name: str | None = None


# Order matters for monitoring (cheapest first) but the README presents
# results in the canonical headline order via ``SAMPLE_ORDER_FOR_README``.
SAMPLE_PLANS: list[SamplePlan] = [
    SamplePlan(
        sample_id="financial_proposal",
        label="Financial services proposal",
        category="screenshot_heavy",
        source_name="Financial_Services_Proposal.pdf",
        source_office_name="Financial_Services_Proposal.pptx",
        target_mb=5.0,
        profile="balanced",
        description="36 MB PowerPoint financial-services proposal converted to PDF, then optimized to an email-safe size.",
        # Cap the recompression ladder so it lands on its first candidate
        # rather than grinding through the full grid on a PPTX export.
        long_edge=2000,
        image_quality=82,
    ),
    SamplePlan(
        sample_id="bank_report",
        label="Bank report",
        category="design_export",
        source_name="Bank_Report.pdf",
        source_office_name="Bank_Report.pptx",
        target_mb=7.0,
        profile="balanced",
        description="33 MB PowerPoint bank report converted to PDF, then optimized via Ghostscript (the Python image-recompress ladder OOMs on this file's ~9,400 small glyph rasters; Ghostscript handles them at the page-stream level).",
        ghostscript_image_dpi=110,
        ghostscript_jpeg_quality=85,
    ),
    SamplePlan(
        sample_id="lossless_huge",
        label="Photo PDF (lossless source)",
        category="lossless_images",
        source_name="sample_lossless_huge.pdf",
        target_mb=5.0,
        profile="quality",
        image_quality=95,
        description="70 MB PDF saved with lossless image encoding; recompressed with the quality profile (q=95) to land near 5 MB while staying above 55 dB PSNR.",
    ),
    SamplePlan(
        sample_id="travel_contact_sheet",
        label="Photo brochure",
        category="photo_heavy",
        source_name="travel_adventure_contact_sheet_source.pdf",
        target_mb=7.0,
        profile="balanced",
        description="139 MB photo contact sheet with dozens of full-bleed photographs.",
    ),
    SamplePlan(
        sample_id="gov_2017",
        label="Government report (2017)",
        category="government_document",
        source_name="20170009128.pdf",
        target_mb=7.0,
        profile="balanced",
        description="13 MB modern government technical report (mixed text, charts, embedded raster figures).",
    ),
    SamplePlan(
        sample_id="research_paper_2024",
        label="Research paper (2024)",
        category="academic_paper",
        source_name="TUM_2024.pdf",
        target_mb=7.0,
        profile="balanced",
        description="10 MB modern academic research paper with embedded figures.",
    ),
    SamplePlan(
        sample_id="archive_scan_1976a",
        label="Archival scan (1976, A)",
        category="archival_scan",
        source_name="19760021505.pdf",
        target_mb=7.0,
        profile="balanced",
        description="33 MB, 606-page archival typeset NASA scan. The Python image ladder cannot decode the embedded JBIG2 images, and Ghostscript pdfwrite cannot get the file under 20 MB. Routed through the optimizer's bilevel CCITT G4 (fax) strategy at 75 DPI - destructive (color/grayscale are thresholded to 1-bit) but appropriate for typeset text + line-art content, and lands in the user's email window.",
        bilevel_dpi=75,
        bilevel_threshold=200,
    ),
    SamplePlan(
        sample_id="archive_scan_1976b",
        label="Archival scan (1976, B)",
        category="archival_scan",
        source_name="19760026509.pdf",
        target_mb=24.0,
        profile="balanced",
        description="89 MB, 192-page archival scan dense with high-DPI raster pages. Compressed with Ghostscript pdfwrite at 120 DPI / JPEG q=82 - PSNR 32.5 dB (an honest archival-quality result), still cuts the file from 89 MB to ~24 MB so it now fits under Gmail's 25 MB attachment limit.",
        ghostscript_image_dpi=120,
        ghostscript_jpeg_quality=82,
    ),
]

SAMPLE_ORDER_FOR_README = (
    "travel_contact_sheet",
    "archive_scan_1976b",
    "lossless_huge",
    "financial_proposal",
    "archive_scan_1976a",
    "bank_report",
    "gov_2017",
    "research_paper_2024",
)

# Office-source documents live alongside the PPTX/XLSX originals; the script
# reads their size from this directory to compute "source -> email PDF" stats.
DEFAULT_OFFICE_SOURCE_DIR = PROJECT_ROOT / "00_project_files" / "Sample Documents"


def ensure_ghostscript_on_path() -> str | None:
    if shutil.which("gswin64c") or shutil.which("gs") or shutil.which("gswin32c"):
        return shutil.which("gswin64c") or shutil.which("gs") or shutil.which("gswin32c")
    if Path(GHOSTSCRIPT_DEFAULT, "gswin64c.exe").exists():
        os.environ["PATH"] = GHOSTSCRIPT_DEFAULT + os.pathsep + os.environ.get("PATH", "")
        return shutil.which("gswin64c")
    return None


def _run_ghostscript(plan: SamplePlan, source: Path, output: Path) -> dict[str, Any]:
    """Compress a PDF with Ghostscript's pdfwrite device.

    Used for inputs the Python image-recompress ladder can't safely handle
    (PowerPoint exports with thousands of tiny glyph rasters). Returns a dict
    shaped like ``optimize()``'s summary so the caller path stays uniform.
    """

    gs = (
        shutil.which("gswin64c")
        or shutil.which("gs")
        or shutil.which("gswin32c")
    )
    if gs is None:
        raise RuntimeError("Ghostscript not on PATH; cannot run ghostscript_image_dpi plan")

    dpi = plan.ghostscript_image_dpi or 150
    quality = plan.ghostscript_jpeg_quality or 85
    cmd = [
        gs,
        "-dNOPAUSE",
        "-dBATCH",
        "-dQUIET",
        "-dSAFER",
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.5",
        "-dDetectDuplicateImages=true",
        "-dColorImageDownsampleType=/Bicubic",
        f"-dColorImageResolution={dpi}",
        "-dGrayImageDownsampleType=/Bicubic",
        f"-dGrayImageResolution={dpi}",
        "-dMonoImageDownsampleType=/Subsample",
        "-dMonoImageResolution=300",
        "-dDownsampleColorImages=true",
        "-dDownsampleGrayImages=true",
        "-dDownsampleMonoImages=true",
        "-dAutoFilterColorImages=false",
        "-dAutoFilterGrayImages=false",
        "-dColorImageFilter=/DCTEncode",
        "-dGrayImageFilter=/DCTEncode",
        "-dEncodeColorImages=true",
        "-dEncodeGrayImages=true",
        f"-dJPEGQ={quality}",
        f"-sOutputFile={output}",
        str(source),
    ]
    subprocess.run(cmd, check=True)

    output_bytes = output.stat().st_size
    target_bytes = int(plan.target_mb * 1024 * 1024)
    return {
        "strategy": f"ghostscript_pdfwrite_{dpi}dpi_q{quality}",
        "met_target": output_bytes <= target_bytes,
        "within_target_range": output_bytes <= target_bytes,
        "pages": None,
        "warnings": [],
    }


def _args_for(plan: SamplePlan, source: Path, output: Path) -> Any:
    parser = build_parser()
    profile_flag = f"--{plan.profile}"
    argv = [
        str(source),
        str(output),
        "--target-mb",
        str(plan.target_mb),
        profile_flag,
        "--force",
        "--skip-render-qa",
    ]
    if plan.long_edge is not None:
        argv.extend(["--long-edge", str(plan.long_edge)])
    if plan.image_quality is not None:
        argv.extend(["--image-quality", str(plan.image_quality)])
    if plan.no_image_recompress:
        argv.append("--no-image-recompress")
    return parser.parse_args(argv)


def _bytes_to_mb(value: int) -> float:
    return round(value / (1024 * 1024), 3)


def _log(message: str) -> None:
    print(message, flush=True)


def run_plan(plan: SamplePlan, input_dir: Path, output_dir: Path, office_dir: Path) -> dict[str, Any]:
    source = input_dir / plan.source_name
    if not source.exists():
        _log(f"  source file missing: {source.name}")
        return {
            "sample_id": plan.sample_id,
            "status": "skipped",
            "reason": f"source file missing: {source.name}",
            **asdict(plan),
        }

    office_source: Path | None = None
    if plan.source_office_name:
        candidate = office_dir / plan.source_office_name
        if candidate.exists():
            office_source = candidate
        else:
            _log(f"  WARN office source missing: {candidate.name}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{plan.sample_id}_email.pdf"
    input_mb = source.stat().st_size / (1024 * 1024)
    _log(f"  optimizing {input_mb:.2f} MB input ...")

    started = time.perf_counter()
    try:
        if plan.bilevel_dpi is not None:
            args = _args_for(plan, source, output)
            args.bilevel = plan.bilevel_dpi
            if plan.bilevel_threshold is not None:
                args.bilevel_threshold = plan.bilevel_threshold
            summary = optimize(args)
        elif plan.ghostscript_image_dpi is not None:
            summary = _run_ghostscript(plan, source, output)
        else:
            summary = optimize(_args_for(plan, source, output))
    except Exception as exc:  # noqa: BLE001 - report failures, do not crash the run.
        _log(f"  optimize failed: {exc}")
        return {
            "sample_id": plan.sample_id,
            "status": "failed",
            "reason": str(exc),
            **asdict(plan),
        }
    optimize_seconds = time.perf_counter() - started
    _log(f"  optimize done in {optimize_seconds:.1f}s; running render QA ...")

    worst_rms: Any = None
    worst_psnr: Any = None
    qa_max_pages = 8
    try:
        qa = compare_render_quality(source, output, scale=1.25, max_pages=qa_max_pages)
        worst_rms = qa.get("worst_rms")
        worst_psnr = qa.get("worst_psnr")
    except Exception as exc:  # noqa: BLE001 - QA is best-effort for reporting.
        _log(f"  render QA failed: {exc}")
    runtime_seconds = time.perf_counter() - started

    input_bytes = source.stat().st_size
    output_bytes = output.stat().st_size
    reduction_percent = round((1 - output_bytes / input_bytes) * 100, 2) if input_bytes else 0.0

    # When the user actually started from an office document, the headline
    # comparison should be original-office-file -> email-safe PDF, not the
    # intermediate converted PDF. Capture both so downstream views can pick.
    source_office_bytes: int | None = None
    source_office_mb: float | None = None
    headline_reduction_percent = reduction_percent
    if office_source is not None:
        source_office_bytes = office_source.stat().st_size
        source_office_mb = _bytes_to_mb(source_office_bytes)
        if source_office_bytes:
            headline_reduction_percent = round(
                (1 - output_bytes / source_office_bytes) * 100, 2
            )

    return {
        "sample_id": plan.sample_id,
        "label": plan.label,
        "category": plan.category,
        "description": plan.description,
        "status": "ok",
        "source_name": plan.source_name,
        "source_path": str(source),
        "source_office_name": plan.source_office_name,
        "source_office_path": str(office_source) if office_source is not None else None,
        "source_office_bytes": source_office_bytes,
        "source_office_mb": source_office_mb,
        "output_path": str(output),
        "target_mb": plan.target_mb,
        "profile": plan.profile,
        "input_bytes": input_bytes,
        "output_bytes": output_bytes,
        "input_mb": _bytes_to_mb(input_bytes),
        "output_mb": _bytes_to_mb(output_bytes),
        # `reduction_percent` is the PDF-only reduction (intermediate -> email
        # copy). `headline_reduction_percent` is the full-workflow reduction
        # (office source -> email copy) when an office source is present,
        # otherwise it matches `reduction_percent`.
        "reduction_percent": reduction_percent,
        "headline_reduction_percent": headline_reduction_percent,
        "headline_source_mb": source_office_mb if source_office_mb is not None else _bytes_to_mb(input_bytes),
        "headline_source_label": ".pptx" if plan.source_office_name and plan.source_office_name.lower().endswith(".pptx") else (
            ".xlsx" if plan.source_office_name and plan.source_office_name.lower().endswith(".xlsx") else (
                ".docx" if plan.source_office_name and plan.source_office_name.lower().endswith(".docx") else ".pdf"
            )
        ),
        "met_target": bool(summary["met_target"]),
        "within_target_range": bool(summary["within_target_range"]),
        "strategy": summary["strategy"],
        "pages": summary.get("pages"),
        "worst_rms": worst_rms,
        "worst_psnr": worst_psnr,
        "runtime_seconds": round(runtime_seconds, 3),
        "qa_max_pages": qa_max_pages,
        "warnings": summary.get("warnings", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(PROJECT_ROOT / "00_project_files" / "Converted PDFs"))
    parser.add_argument(
        "--optimized-output",
        default=str(PROJECT_ROOT / "00_project_files" / "Optimized PDFs"),
    )
    parser.add_argument("--output", default=str(PROJECT_ROOT / "benchmarks" / "results" / "samples.json"))
    parser.add_argument(
        "--office-source-dir",
        default=str(DEFAULT_OFFICE_SOURCE_DIR),
        help="Directory containing original office documents (.pptx/.xlsx/.docx). Used so the chart and table can report 'this 36 MB .pptx -> 2 MB email PDF' rather than the intermediate converted PDF size.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip plans that already have an `ok` entry in the existing results file.",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="Only run the specified sample_id(s).",
    )
    args = parser.parse_args()

    gs = ensure_ghostscript_on_path()
    if gs:
        _log(f"Ghostscript available: {gs}")
    else:
        _log("Ghostscript not found on PATH; aggressive fallback will be skipped if reached.")

    input_dir = Path(args.input).expanduser().resolve()
    output_dir = Path(args.optimized_output).expanduser().resolve()
    office_dir = Path(args.office_source_dir).expanduser().resolve()
    results_path = Path(args.output).expanduser().resolve()
    results_path.parent.mkdir(parents=True, exist_ok=True)

    existing_results: list[dict[str, Any]] = []
    existing_ok_ids: set[str] = set()
    if args.resume and results_path.exists():
        try:
            existing_results = json.loads(results_path.read_text(encoding="utf-8"))
            existing_ok_ids = {row["sample_id"] for row in existing_results if row.get("status") == "ok"}
            _log(f"Resuming; {len(existing_ok_ids)} already-ok samples: {sorted(existing_ok_ids)}")
        except Exception as exc:  # noqa: BLE001
            _log(f"Could not load existing results ({exc}); starting fresh.")
            existing_results = []
            existing_ok_ids = set()

    only_filter = set(args.only) if args.only else None

    results: list[dict[str, Any]] = list(existing_results)
    for plan in SAMPLE_PLANS:
        if only_filter and plan.sample_id not in only_filter:
            continue
        if plan.sample_id in existing_ok_ids:
            _log(f"[{plan.sample_id}] already ok; skipping (use without --resume to re-run).")
            continue
        _log(f"[{plan.sample_id}] {plan.label} -> target {plan.target_mb} MB, profile {plan.profile}")
        result = run_plan(plan, input_dir, output_dir, office_dir)
        if result["status"] == "ok":
            _log(
                f"  input {result['input_mb']:.2f} MB -> output {result['output_mb']:.2f} MB "
                f"({result['reduction_percent']:.1f}%) target_met={result['met_target']} "
                f"PSNR={result['worst_psnr']} RMS={result['worst_rms']} runtime={result['runtime_seconds']:.1f}s"
            )
        else:
            _log(f"  status={result['status']} reason={result.get('reason')}")
        # Replace any prior entry for this sample_id so re-runs overwrite.
        results = [row for row in results if row.get("sample_id") != plan.sample_id]
        results.append(result)
        # Persist incrementally so partial progress is recoverable.
        results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    _log(f"Wrote {results_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

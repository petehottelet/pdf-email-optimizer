#!/usr/bin/env python3
"""Run an honest size/quality comparison against Ghostscript and pikepdf.

For a single source PDF, this script runs:

- ``pdf-email-optimizer`` at quality, balanced, and aggressive profiles
- raw Ghostscript at the ``/screen``, ``/ebook``, and ``/printer`` PDFSETTINGS
- a pikepdf-only lossless rewrite

It records output size, percent reduction, render PSNR/RMS against the
original, and runtime. The exact Ghostscript command is captured so the
comparisons doc can publish reproducible invocations.

Usage::

    python benchmarks/run_comparisons.py --source "00_project_files/Converted PDFs/sample_lossless_huge.pdf" \
        --target-mb 7 --output benchmarks/results/comparisons.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from pdf_email_optimizer.optimizer import build_parser, compare_render_quality, optimize  # noqa: E402
from pdf_email_optimizer.pikepdf_backend import structural_optimize as pikepdf_structural_optimize  # noqa: E402

GHOSTSCRIPT_DEFAULT = r"C:\Program Files\gs\gs10.07.1\bin"


def _ensure_gs_path() -> str | None:
    candidate = shutil.which("gswin64c") or shutil.which("gs") or shutil.which("gswin32c")
    if candidate:
        return candidate
    if Path(GHOSTSCRIPT_DEFAULT, "gswin64c.exe").exists():
        os.environ["PATH"] = GHOSTSCRIPT_DEFAULT + os.pathsep + os.environ.get("PATH", "")
        return shutil.which("gswin64c")
    return None


def _measure_pair(source: Path, output: Path) -> dict[str, Any]:
    input_bytes = source.stat().st_size
    output_bytes = output.stat().st_size
    worst_rms: Any = None
    worst_psnr: Any = None
    try:
        qa = compare_render_quality(source, output, scale=1.25, max_pages=6)
        worst_rms = qa.get("worst_rms")
        worst_psnr = qa.get("worst_psnr")
    except Exception:  # noqa: BLE001
        pass
    return {
        "input_bytes": input_bytes,
        "output_bytes": output_bytes,
        "input_mb": round(input_bytes / (1024 * 1024), 3),
        "output_mb": round(output_bytes / (1024 * 1024), 3),
        "reduction_percent": round((1 - output_bytes / input_bytes) * 100, 2) if input_bytes else 0.0,
        "worst_psnr": worst_psnr,
        "worst_rms": worst_rms,
    }


def run_optimizer(source: Path, target_mb: float, profile: str, output_dir: Path) -> dict[str, Any]:
    output = output_dir / f"optimizer_{profile}.pdf"
    started = time.perf_counter()
    parser = build_parser()
    args = parser.parse_args(
        [
            str(source),
            str(output),
            "--target-mb",
            str(target_mb),
            f"--{profile}",
            "--force",
            "--skip-render-qa",
        ]
    )
    summary = optimize(args)
    runtime = time.perf_counter() - started
    metrics = _measure_pair(source, output)
    return {
        "tool": f"pdf-email-optimizer ({profile})",
        "command": f'pdf-email-optimizer "{source.name}" output.pdf --target-mb {target_mb:g} --{profile}',
        "runtime_seconds": round(runtime, 3),
        "strategy": summary["strategy"],
        "met_target": summary["met_target"],
        **metrics,
    }


def run_ghostscript_setting(gs_binary: str, source: Path, setting: str, output_dir: Path) -> dict[str, Any]:
    output = output_dir / f"ghostscript_{setting}.pdf"
    command = [
        gs_binary,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.6",
        "-dNOPAUSE",
        "-dBATCH",
        "-dQUIET",
        "-dSAFER",
        f"-dPDFSETTINGS=/{setting}",
        f"-sOutputFile={output}",
        str(source),
    ]
    pretty_command = (
        f"gs -sDEVICE=pdfwrite -dPDFSETTINGS=/{setting} -dCompatibilityLevel=1.6 "
        f"-dNOPAUSE -dBATCH -dQUIET -dSAFER -sOutputFile=output.pdf input.pdf"
    )

    started = time.perf_counter()
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    runtime = time.perf_counter() - started

    if completed.returncode != 0 or not output.exists():
        return {
            "tool": f"ghostscript /{setting}",
            "command": pretty_command,
            "runtime_seconds": round(runtime, 3),
            "status": "failed",
            "stderr": completed.stderr.strip()[:240],
        }

    metrics = _measure_pair(source, output)
    return {
        "tool": f"ghostscript /{setting}",
        "command": pretty_command,
        "runtime_seconds": round(runtime, 3),
        "status": "ok",
        **metrics,
    }


def run_pikepdf_only(source: Path, output_dir: Path) -> dict[str, Any]:
    output = output_dir / "pikepdf_only.pdf"
    warnings: list[str] = []
    started = time.perf_counter()
    result = pikepdf_structural_optimize(source, output, warnings=warnings)
    runtime = time.perf_counter() - started
    if result is None:
        return {
            "tool": "pikepdf-only (lossless)",
            "command": "pikepdf save with object_stream_mode=generate, recompress_flate=True",
            "runtime_seconds": round(runtime, 3),
            "status": "failed",
            "warnings": warnings,
        }

    metrics = _measure_pair(source, output)
    return {
        "tool": "pikepdf-only (lossless)",
        "command": "pikepdf save with object_stream_mode=generate, recompress_flate=True",
        "runtime_seconds": round(runtime, 3),
        "status": "ok",
        **metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--target-mb", type=float, default=7.0)
    parser.add_argument("--output", default=str(PROJECT_ROOT / "benchmarks" / "results" / "comparisons.json"))
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "00_project_files" / "Comparison Outputs"),
    )
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        print(f"Source not found: {source}", flush=True)
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    gs_binary = _ensure_gs_path()
    if not gs_binary:
        print("Ghostscript not found; comparisons will be missing the GS rows.", flush=True)
    else:
        print(f"Using Ghostscript: {gs_binary}", flush=True)

    rows: list[dict[str, Any]] = []

    for profile in ("quality", "balanced", "aggressive"):
        print(f"-> optimizer ({profile}) ...", flush=True)
        rows.append(run_optimizer(source, args.target_mb, profile, output_dir))

    if gs_binary:
        for setting in ("screen", "ebook", "printer"):
            print(f"-> ghostscript /{setting} ...", flush=True)
            rows.append(run_ghostscript_setting(gs_binary, source, setting, output_dir))

    print("-> pikepdf-only ...", flush=True)
    rows.append(run_pikepdf_only(source, output_dir))

    summary = {
        "source": str(source),
        "source_name": source.name,
        "target_mb": args.target_mb,
        "results": rows,
    }
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {output_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

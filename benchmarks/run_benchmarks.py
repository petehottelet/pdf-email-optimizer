#!/usr/bin/env python3
"""Run PDF Email Optimizer benchmarks from a small manifest."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from pdf_email_optimizer.optimizer import build_parser, compare_render_quality, optimize  # noqa: E402


def parse_scalar(value: str) -> Any:
    value = value.strip().strip("\"'")
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def load_manifest(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))

    cases: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped == "cases:":
            continue
        if stripped.startswith("- "):
            current = {}
            cases.append(current)
            stripped = stripped[2:].strip()
            if not stripped:
                continue
        if current is None or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        current[key.strip()] = parse_scalar(value)
    return {"cases": cases}


def _psnr_cell(value: Any) -> str:
    """Render the worst-PSNR column. ``inf`` means pixel-identical, which we
    surface as the unicode infinity symbol so the table stays scannable."""

    if value in (None, "-", ""):
        return "-"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if f != f or f == float("inf"):  # NaN or +inf
        return "\u221e (lossless)"
    return f"{f:.1f} dB"


def markdown_table(results: list[dict[str, Any]]) -> str:
    """Five-column, reduction-sorted Markdown table.

    Wide ten-column tables don't fit a README at typical viewport widths and
    bury the headline reductions behind less interesting metadata (profile,
    target, RMS, internal strategy name). This version sorts by reduction
    percent descending and keeps only the columns a reader actually needs to
    decide "does this tool work for files like mine".
    """

    def _sort_key(row: dict[str, Any]) -> tuple[int, float]:
        # Rank ok before skipped/failed, then by reduction percent desc.
        status_rank = 0 if row.get("status") == "ok" else 1
        try:
            reduction = float(row.get("reduction_percent", 0.0))
        except (TypeError, ValueError):
            reduction = 0.0
        return (status_rank, -reduction)

    rows = sorted(results, key=_sort_key)

    lines = [
        "| Case | Input | Email PDF | Reduction | PSNR |",
        "|---|---:|---:|---:|---:|",
    ]
    for result in rows:
        status = result.get("status")
        if status == "skipped":
            lines.append(f"| {result['case_id']} | _missing_ | skipped | - | - |")
            continue
        if status == "failed":
            lines.append(f"| {result['case_id']} | - | failed | - | - |")
            continue
        lines.append(
            "| {case_id} | {input_mb:.2f} MB | **{output_mb:.2f} MB** | **{reduction_percent:.1f}%** | {psnr} |".format(
                case_id=result["case_id"],
                input_mb=result["input_mb"],
                output_mb=result["output_mb"],
                reduction_percent=result["reduction_percent"],
                psnr=_psnr_cell(result.get("worst_psnr")),
            )
        )
    return "\n".join(lines) + "\n"


def run_case(case: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    input_path = (PROJECT_ROOT / str(case["input"])).resolve()
    target_mb = float(case.get("target_mb", 7))
    profile = str(case.get("profile", "balanced"))
    if not input_path.exists():
        return {
            "case_id": case["id"],
            "status": "skipped",
            "reason": "fixture missing",
            "input": str(input_path),
            "target_mb": target_mb,
            "profile": profile,
            "warnings": ["Fixture is not present. Add a redistributable PDF or generated fixture."],
        }

    output_path = output_dir / f"{case['id']}_optimized.pdf"
    args = build_parser().parse_args(
        [
            str(input_path),
            str(output_path),
            "--target-mb",
            str(target_mb),
            "--profile",
            profile,
            "--force",
            "--skip-render-qa",
        ]
    )
    started = time.perf_counter()
    try:
        summary = optimize(args)
    except Exception as exc:  # noqa: BLE001
        return {
            "case_id": case["id"],
            "status": "failed",
            "reason": str(exc),
            "input": str(input_path),
            "target_mb": target_mb,
            "profile": profile,
            "warnings": [str(exc)],
        }
    runtime = time.perf_counter() - started

    # Compute an honest original-vs-output render comparison for every case so
    # the published table always carries real PSNR/RMS numbers, regardless of
    # whether the profile ran render QA internally.
    worst_rms: Any = "-"
    worst_psnr: Any = "-"
    try:
        qa = compare_render_quality(input_path, output_path, scale=1.5, max_pages=12)
        worst_rms = qa.get("worst_rms", "-")
        worst_psnr = qa.get("worst_psnr", "-")
    except Exception:  # noqa: BLE001 - QA is best-effort for reporting only.
        pass

    return {
        "case_id": case["id"],
        "status": "ok",
        "input_mb": summary["input_mb"],
        "output_mb": summary["output_mb"],
        "reduction_percent": round((1 - summary["output_bytes"] / summary["input_bytes"]) * 100, 2),
        "target_mb": summary["target_mb"],
        "met_target": summary["met_target"],
        "profile": summary["profile"],
        "strategy": summary["strategy"],
        "pages": summary["pages"],
        "worst_rms": worst_rms,
        "worst_psnr": worst_psnr,
        "runtime_seconds": round(runtime, 3),
        "warnings": summary["warnings"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="benchmarks/benchmark_manifest.yaml")
    parser.add_argument("--output", default="benchmarks/results/latest.json")
    args = parser.parse_args()

    manifest_path = (PROJECT_ROOT / args.manifest).resolve()
    output_path = (PROJECT_ROOT / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generated_pdf_dir = output_path.parent / "generated-pdfs"
    generated_pdf_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(manifest_path)
    results = [run_case(case, generated_pdf_dir) for case in manifest.get("cases", [])]
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    output_path.with_suffix(".md").write_text(markdown_table(results), encoding="utf-8")
    csv_path = output_path.with_suffix(".csv")
    write_csv(results, csv_path)
    print(f"Wrote {output_path}")
    print(f"Wrote {output_path.with_suffix('.md')}")
    print(f"Wrote {csv_path}")
    return 0


def write_csv(results: list[dict[str, Any]], csv_path: Path) -> None:
    fieldnames = [
        "case_id",
        "status",
        "profile",
        "target_mb",
        "input_mb",
        "output_mb",
        "reduction_percent",
        "met_target",
        "worst_psnr",
        "worst_rms",
        "strategy",
        "pages",
        "runtime_seconds",
        "reason",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for result in results:
            row = {key: result.get(key, "") for key in fieldnames}
            writer.writerow(row)


if __name__ == "__main__":
    raise SystemExit(main())

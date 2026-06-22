#!/usr/bin/env python3
"""Human-readable and Markdown rendering of optimize/audit summaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .utils import fmt_mb


def print_summary(summary: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(summary, indent=2))
        return

    if summary.get("source") and summary["source"] != summary["input"]:
        print(f"Source: {summary['source']} ({summary['source_format']})")
    print(f"Input:  {summary['input']}")
    print(f"Output: {summary['output']}")
    if summary.get("source_mb") is not None:
        print(
            f"Size:   {summary['source_mb']:.2f} MB ({summary['source_format']}) "
            f"-> {summary['intermediate_pdf_mb']:.2f} MB (pdf) "
            f"-> {summary['output_mb']:.2f} MB (email)"
        )
    else:
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
    if summary.get("recommended_strategy"):
        print(f"Recommended strategy: {summary['recommended_strategy']}")
    print(f"Structural cleanup likely: {'yes' if summary.get('structural_cleanup_likely') else 'no'}")
    print(f"Image recompression likely required: {'yes' if summary.get('image_recompression_likely_required') else 'no'}")
    for warning in summary.get("warnings", []):
        print(f"Warning: {warning}", file=sys.stderr)


__all__ = [
    "build_markdown_report",
    "print_audit",
    "print_summary",
    "write_report",
]

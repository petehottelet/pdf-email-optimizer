#!/usr/bin/env python3
"""Command-line interface for the PDF Email Optimizer.

The CLI is a thin shell over the library: it parses arguments, builds an
:class:`~pdf_email_optimizer.config.OptimizeConfig`, calls
:func:`pdf_email_optimizer.pipeline.optimize`, and renders the result.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import bilevel as bilevel_strategy
from .config import OptimizeConfig
from .pdf_inspect import audit
from .pipeline import optimize
from .profiles import PROFILE_DEFAULTS
from .reporting import print_audit, print_summary, write_report

DESCRIPTION = "Optimize a PDF for email delivery while preserving visual quality."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        "input_pdf",
        metavar="input",
        help=(
            "Source document. Accepts .pdf directly; .docx, .doc, .pptx, .ppt, "
            ".xlsx, .xls, .odt, .odp, .ods, and .rtf are converted to PDF first via "
            "LibreOffice (install separately)."
        ),
    )
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
    profile_group.add_argument("--compress", dest="profile", action="store_const", const="compress", help="Shortcut for --profile compress. Prioritises filesize over fidelity while keeping RGB output (no bilevel).")
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
    parser.add_argument(
        "--bilevel",
        type=int,
        nargs="?",
        const=bilevel_strategy.DEFAULT_DPI,
        default=None,
        metavar="DPI",
        help=(
            "Render every page as 1-bit black & white at the given DPI "
            f"(default {bilevel_strategy.DEFAULT_DPI}) and emit a CCITT G4 (fax) PDF. "
            "Use only on typeset / line-art archival scans - all color and "
            "grayscale information is destroyed."
        ),
    )
    parser.add_argument(
        "--bilevel-threshold",
        type=int,
        default=bilevel_strategy.DEFAULT_THRESHOLD,
        metavar="N",
        help=(
            "Brightness cutoff (0-255) for --bilevel conversion. Pixels brighter "
            f"than N become white, the rest black. Default {bilevel_strategy.DEFAULT_THRESHOLD}."
        ),
    )
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
            summary = audit(args.input_pdf)
            print_audit(summary, json_output=args.json)
            return 0
        config = OptimizeConfig.from_cli_args(args)
        summary = optimize(config)
        if args.report:
            report_path = Path(args.report).expanduser().resolve()
            write_report(summary, report_path)
            summary["report"] = str(report_path)
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print_summary(summary, json_output=args.json)
    return 0


__all__ = ["build_parser", "main"]

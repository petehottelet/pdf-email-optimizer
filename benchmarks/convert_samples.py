#!/usr/bin/env python3
"""Headless conversion of sample office documents to PDF via LibreOffice.

The sample documents (PPTX/XLSX) used to produce the README's real-world
results sit in a gitignored ``00_project_files/`` directory because they are
too large or too sample-specific to commit. This script converts every
recognised office file in the input directory into a single working PDF and
writes the converted files to ``00_project_files/Converted PDFs/`` so the
benchmark/gallery/chart scripts can find them.

Usage::

    python benchmarks/convert_samples.py
    python benchmarks/convert_samples.py --input "00_project_files/Sample Documents" --output "00_project_files/Converted PDFs"
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "00_project_files" / "Sample Documents"
DEFAULT_OUTPUT = PROJECT_ROOT / "00_project_files" / "Converted PDFs"

OFFICE_SUFFIXES = {".pptx", ".ppt", ".xlsx", ".xls", ".docx", ".doc", ".odp", ".ods", ".odt"}


def find_soffice() -> str | None:
    candidate = shutil.which("soffice")
    if candidate:
        return candidate
    for known in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/usr/bin/soffice",
        "/usr/local/bin/soffice",
    ):
        if Path(known).exists():
            return known
    return None


def convert_one(soffice: str, source: Path, output_dir: Path) -> Path | None:
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = output_dir / f"{source.stem}.pdf"

    env = os.environ.copy()
    env.setdefault("HOME", str(output_dir))

    cmd = [
        soffice,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(source),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
    if completed.returncode != 0 or not expected.exists():
        sys.stderr.write(f"Conversion failed for {source.name}: {completed.stderr.strip()}\n")
        return None
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--include-pdfs", action="store_true", help="Copy existing PDFs into the output dir too.")
    args = parser.parse_args()

    input_dir = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()

    if not input_dir.exists():
        sys.stderr.write(f"Input directory not found: {input_dir}\n")
        return 1

    soffice = find_soffice()
    if soffice is None:
        sys.stderr.write(
            "LibreOffice (soffice) not found. Install LibreOffice or point --input at already-converted PDFs.\n"
        )
        return 1
    print(f"Using LibreOffice at: {soffice}")

    converted: list[Path] = []
    for source in sorted(input_dir.iterdir()):
        if not source.is_file():
            continue
        suffix = source.suffix.lower()
        if suffix in OFFICE_SUFFIXES:
            print(f"Converting {source.name} ...")
            result = convert_one(soffice, source, output_dir)
            if result:
                size_mb = result.stat().st_size / (1024 * 1024)
                print(f"  -> {result.name} ({size_mb:.2f} MB)")
                converted.append(result)
        elif suffix == ".pdf" and args.include_pdfs:
            destination = output_dir / source.name
            shutil.copy2(source, destination)
            size_mb = destination.stat().st_size / (1024 * 1024)
            print(f"Copied {source.name} ({size_mb:.2f} MB)")
            converted.append(destination)

    print(f"Converted {len(converted)} file(s) into {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

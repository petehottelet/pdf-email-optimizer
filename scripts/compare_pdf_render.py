#!/usr/bin/env python3
"""Backward-compatible wrapper for the PDF render comparison CLI."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
if PROJECT_SRC.exists():
    sys.path.insert(0, str(PROJECT_SRC))

from pdf_email_optimizer.render_qa import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

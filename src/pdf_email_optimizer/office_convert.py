"""Headless conversion of Office documents to PDF via LibreOffice.

The optimizer accepts a PDF directly, but real-world workflows often start in
PowerPoint (`.pptx`), Word (`.docx`), Excel (`.xlsx`), or the LibreOffice
equivalents. Rather than asking users to convert by hand before running the
optimizer, this module shells out to ``soffice --headless --convert-to pdf``
when a non-PDF input is supplied.

Why LibreOffice and not a Python library: LibreOffice's headless mode is the
most faithful renderer of Microsoft Office formats available outside Office
itself, it handles every format we care about with a single tool, and it is
already widely installed (on Linux it ships in most distro repos; on macOS and
Windows it is a one-line install). Treating it as an *optional* system
dependency keeps ``pip install pdf-email-optimizer`` lightweight: only users
who actually need to optimize Office files pay the install cost.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

OFFICE_SUFFIXES: frozenset[str] = frozenset(
    {
        ".doc",
        ".docx",
        ".odp",
        ".ods",
        ".odt",
        ".ppt",
        ".pptx",
        ".rtf",
        ".xls",
        ".xlsx",
    }
)

_KNOWN_SOFFICE_PATHS: tuple[str, ...] = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
    "/opt/homebrew/bin/soffice",
)


class OfficeConversionError(RuntimeError):
    """Raised when LibreOffice is missing or fails to convert a document."""


def is_office_document(path: Path) -> bool:
    """Return True if ``path`` has a suffix we route through LibreOffice."""

    return path.suffix.lower() in OFFICE_SUFFIXES


def find_soffice() -> str | None:
    """Locate the LibreOffice ``soffice`` executable, or return ``None``.

    Honours ``PATH`` first, then falls back to a handful of well-known install
    locations on macOS, Linux, and Windows so users don't need to put
    LibreOffice on ``PATH`` to use the optimizer.
    """

    candidate = shutil.which("soffice")
    if candidate:
        return candidate
    for known in _KNOWN_SOFFICE_PATHS:
        if Path(known).exists():
            return known
    return None


def _install_hint() -> str:
    return (
        "LibreOffice is required to convert Office documents (.docx, .pptx, .xlsx, ...) "
        "to PDF before optimization. Install it from https://www.libreoffice.org/ "
        "(or 'brew install --cask libreoffice' on macOS, "
        "'apt install libreoffice' on Debian/Ubuntu, "
        "'choco install libreoffice-fresh' on Windows), then re-run the command. "
        "If LibreOffice is installed but not on PATH, the optimizer also checks "
        "the default install locations automatically."
    )


def convert_to_pdf(source: Path, *, output_dir: Path | None = None) -> Path:
    """Convert an Office document to PDF using LibreOffice headless mode.

    Parameters
    ----------
    source:
        Path to a ``.docx``, ``.pptx``, ``.xlsx`` (or other supported Office
        format) file. The file is not modified.
    output_dir:
        Directory the converted PDF should be written to. Defaults to a
        per-invocation temporary directory; callers that pass their own
        directory are responsible for cleanup.

    Returns
    -------
    Path
        Path to the resulting ``<stem>.pdf`` inside ``output_dir``.

    Raises
    ------
    OfficeConversionError
        If LibreOffice cannot be located or the conversion subprocess fails.
    """

    source = Path(source).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source document not found: {source}")
    if not is_office_document(source):
        raise OfficeConversionError(
            f"Unsupported source suffix '{source.suffix}'. Supported suffixes: "
            + ", ".join(sorted(OFFICE_SUFFIXES))
        )

    soffice = find_soffice()
    if soffice is None:
        raise OfficeConversionError(_install_hint())

    if output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="pdf-email-optimizer-convert-"))
    else:
        output_dir = Path(output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

    expected = output_dir / f"{source.stem}.pdf"

    # LibreOffice writes a user profile on first use; point HOME at a writable
    # location so the conversion succeeds even when the real HOME is read-only
    # (CI runners, sandboxed agent environments, etc.).
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
        stderr = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic output"
        raise OfficeConversionError(
            f"LibreOffice failed to convert {source.name}: {stderr}"
        )
    return expected


__all__ = [
    "OFFICE_SUFFIXES",
    "OfficeConversionError",
    "convert_to_pdf",
    "find_soffice",
    "is_office_document",
]

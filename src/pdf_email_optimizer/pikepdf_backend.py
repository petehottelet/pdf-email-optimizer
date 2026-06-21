"""Optional pikepdf/qpdf structural optimization backend.

pikepdf bundles qpdf via its wheels, so unlike the Ghostscript fallback it needs
no system binary. It performs *lossless* structural cleanup that complements
pypdf: generating cross-reference object streams, recompressing flate streams,
and garbage-collecting unreferenced objects. Because it never touches rendered
pixels, the result is always safe to accept when it is smaller.

The import is lazy: if pikepdf is not installed the backend reports a warning
and returns ``None`` so the optimizer can carry on with pypdf-only results.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def pikepdf_available() -> bool:
    try:
        import pikepdf  # noqa: F401
    except ImportError:
        return False
    return True


def structural_optimize(
    input_path: Path,
    output_path: Path,
    *,
    warnings: list[str],
    linearize: bool = False,
) -> dict[str, Any] | None:
    """Losslessly restructure ``input_path`` into ``output_path``.

    Returns a result dict on success or ``None`` if pikepdf is unavailable or
    the rewrite fails. Failures are reported via ``warnings`` and never raise,
    so this stays a best-effort optional step.
    """

    try:
        import pikepdf
    except ImportError:
        warnings.append(
            "pikepdf was not found; skipped optional lossless structural optimization. "
            'Install it with: pip install "pdf-email-optimizer[pikepdf]".'
        )
        return None

    save_kwargs: dict[str, Any] = {
        "object_stream_mode": pikepdf.ObjectStreamMode.generate,
        "compress_streams": True,
        "recompress_flate": True,
        "linearize": linearize,
    }

    try:
        with pikepdf.open(str(input_path)) as pdf:
            pdf.save(str(output_path), **save_kwargs)
    except TypeError:
        # Older pikepdf without recompress_flate; retry with a safe subset.
        save_kwargs.pop("recompress_flate", None)
        try:
            with pikepdf.open(str(input_path)) as pdf:
                pdf.save(str(output_path), **save_kwargs)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"pikepdf structural optimization failed: {exc}")
            return None
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"pikepdf structural optimization failed: {exc}")
        return None

    if not output_path.exists():
        return None

    return {
        "path": str(output_path),
        "size_bytes": output_path.stat().st_size,
        "backend": "pikepdf",
        "warnings": [],
    }


__all__ = ["pikepdf_available", "structural_optimize"]

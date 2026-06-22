"""Optimization profile defaults.

Each profile is a dict of recompression-ladder knobs. ``None`` fields on an
:class:`~pdf_email_optimizer.config.OptimizeConfig` are filled from the active
profile via :meth:`OptimizeConfig.resolved`.
"""

from __future__ import annotations

from typing import Any

PROFILE_DEFAULTS: dict[str, dict[str, Any]] = {
    "quality": {
        "image_quality": 92,
        "min_image_quality": 88,
        "quality_ladder": (92, 90, 88),
        "long_edge_ladder": (None, 3200, 2800, 2400),
        "min_long_edge": 2400,
        "min_image_pixels": 500_000,
        "min_image_bytes": 350_000,
        "ghostscript": "never",
        "pikepdf": "auto",
        "render_qa": True,
        "min_render_psnr": 38.0,
        "max_render_rms": 8.0,
        "qa_scale": 1.5,
        "qa_max_pages": 12,
    },
    "balanced": {
        "image_quality": 88,
        "min_image_quality": 76,
        "quality_ladder": (88, 86, 84, 82, 80, 78, 76),
        "long_edge_ladder": (None, 2400, 2200, 2000, 1800),
        "min_long_edge": 1800,
        "min_image_pixels": 250_000,
        "min_image_bytes": 120_000,
        "ghostscript": "never",
        "pikepdf": "auto",
        "render_qa": False,
        "min_render_psnr": None,
        "max_render_rms": None,
        "qa_scale": 1.0,
        "qa_max_pages": 8,
    },
    "aggressive": {
        "image_quality": 86,
        "min_image_quality": 60,
        "quality_ladder": (86, 82, 78, 74, 70, 66, 62, 60),
        "long_edge_ladder": (None, 2400, 2000, 1800, 1600, 1400, 1200),
        "min_long_edge": 1200,
        "min_image_pixels": 120_000,
        "min_image_bytes": 0,
        "ghostscript": "auto",
        "pikepdf": "auto",
        "render_qa": False,
        "min_render_psnr": None,
        "max_render_rms": None,
        "qa_scale": 1.0,
        "qa_max_pages": 8,
    },
    # Sub-aggressive recompression that still keeps RGB (no bilevel).
    # Prioritises filesize: lower JPEG floor, smaller long-edge caps, no
    # PSNR floor. Use for "force this under N MB" scenarios where visible
    # compression is acceptable but the page must still render as a normal
    # photo / color document.
    "compress": {
        "image_quality": 70,
        "min_image_quality": 30,
        "quality_ladder": (70, 60, 55, 50, 45, 40, 35, 30),
        "long_edge_ladder": (None, 2000, 1600, 1400, 1200, 1000, 900, 800),
        "min_long_edge": 800,
        "min_image_pixels": 50_000,
        "min_image_bytes": 0,
        "ghostscript": "auto",
        "pikepdf": "auto",
        "render_qa": False,
        "min_render_psnr": None,
        "max_render_rms": None,
        "qa_scale": 1.0,
        "qa_max_pages": 8,
    },
}


def profile_default(profile: str, key: str) -> Any:
    """Return the default ``key`` for ``profile``."""

    return PROFILE_DEFAULTS[profile][key]


__all__ = ["PROFILE_DEFAULTS", "profile_default"]

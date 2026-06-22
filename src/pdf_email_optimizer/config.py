#!/usr/bin/env python3
"""Typed configuration for the optimizer's library API.

:class:`OptimizeConfig` is the public, importable way to drive
:func:`pdf_email_optimizer.optimize`. It replaces the old habit of passing an
``argparse.Namespace`` into the core functions: library users build an
``OptimizeConfig`` directly, and the CLI builds one from parsed args via
:meth:`OptimizeConfig.from_cli_args`.

Explicitness is encoded by the ``None`` sentinel: a field left ``None`` means
"use the active profile's default". The pipeline reads the *raw* config (before
:meth:`resolved`) when it needs to know whether the user actually asked for a
value -- this is how a profile-default ``ghostscript="never"`` is told apart
from an explicit ``--ghostscript never``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, TypedDict

from .profiles import PROFILE_DEFAULTS

# Fields filled from the active profile when left as ``None``. Mirrors the old
# ``apply_profile_defaults`` behavior exactly. Note that ``long_edge`` (the
# first long-edge cap to try) is intentionally absent: it stays ``None`` unless
# the caller pins it, and the ladder is sourced from the profile separately.
_PROFILE_FILLED_FIELDS = (
    "image_quality",
    "min_image_quality",
    "min_long_edge",
    "min_image_pixels",
    "min_image_bytes",
    "ghostscript",
    "pikepdf",
    "render_qa",
    "min_render_psnr",
    "max_render_rms",
    "qa_scale",
    "qa_max_pages",
)


@dataclass
class OptimizeConfig:
    """Everything :func:`pdf_email_optimizer.optimize` needs to run.

    Output formatting concerns (``--json`` / ``--report`` / ``--audit``) are
    deliberately *not* here: they are CLI presentation, not optimization input.
    """

    input: str | Path
    output: str | Path | None = None
    force: bool = False
    # Target window
    target_mb: float | None = 7.0
    target: str | None = None
    target_min_mb: float | None = None
    target_range_mb: str | None = None
    preferred_mb: float | None = None
    # Profile + per-knob overrides (None => resolved from PROFILE_DEFAULTS[profile])
    profile: str = "balanced"
    image_quality: int | None = None
    min_image_quality: int | None = None
    long_edge: int | None = None
    min_long_edge: int | None = None
    min_image_pixels: int | None = None
    min_image_bytes: int | None = None
    no_strip_private: bool = False
    no_image_recompress: bool = False
    flatten_alpha: bool = False
    ghostscript: str | None = None  # auto|always|never; None => profile default
    pikepdf: str | None = None  # auto|never; None => profile default
    render_qa: bool | None = None
    min_render_psnr: float | None = None
    max_render_rms: float | None = None
    qa_scale: float | None = None
    qa_max_pages: int | None = None
    bilevel: int | None = None
    bilevel_threshold: int = 200

    def resolved(self) -> OptimizeConfig:
        """Return a copy with ``None`` profile knobs filled from the profile.

        The original (raw) config is left untouched so callers can still see
        which options were explicitly provided.
        """

        if self.profile not in PROFILE_DEFAULTS:
            raise ValueError(
                f"Unknown profile '{self.profile}'. Valid profiles: {', '.join(PROFILE_DEFAULTS)}."
            )
        updates: dict[str, Any] = {}
        for key in _PROFILE_FILLED_FIELDS:
            if getattr(self, key) is None:
                updates[key] = PROFILE_DEFAULTS[self.profile][key]
        return replace(self, **updates)

    def profile_ladders(self) -> tuple[tuple[int, ...], tuple[int | None, ...]]:
        """Return ``(quality_ladder, long_edge_ladder)`` for the active profile."""

        profile = PROFILE_DEFAULTS[self.profile]
        return profile["quality_ladder"], profile["long_edge_ladder"]

    @classmethod
    def from_cli_args(cls, ns: argparse.Namespace) -> OptimizeConfig:
        """Build a config from a parsed CLI namespace.

        Maps ``input_pdf`` -> ``input`` and ``output_pdf`` -> ``output`` and
        ignores the presentation-only flags (``json`` / ``report`` / ``audit``).
        """

        return cls(
            input=ns.input_pdf,
            output=ns.output_pdf,
            force=getattr(ns, "force", False),
            target_mb=getattr(ns, "target_mb", 7.0),
            target=getattr(ns, "target", None),
            target_min_mb=getattr(ns, "target_min_mb", None),
            target_range_mb=getattr(ns, "target_range_mb", None),
            preferred_mb=getattr(ns, "preferred_mb", None),
            profile=getattr(ns, "profile", "balanced"),
            image_quality=getattr(ns, "image_quality", None),
            min_image_quality=getattr(ns, "min_image_quality", None),
            long_edge=getattr(ns, "long_edge", None),
            min_long_edge=getattr(ns, "min_long_edge", None),
            min_image_pixels=getattr(ns, "min_image_pixels", None),
            min_image_bytes=getattr(ns, "min_image_bytes", None),
            no_strip_private=getattr(ns, "no_strip_private", False),
            no_image_recompress=getattr(ns, "no_image_recompress", False),
            flatten_alpha=getattr(ns, "flatten_alpha", False),
            ghostscript=getattr(ns, "ghostscript", None),
            pikepdf=getattr(ns, "pikepdf", None),
            render_qa=getattr(ns, "render_qa", None),
            min_render_psnr=getattr(ns, "min_render_psnr", None),
            max_render_rms=getattr(ns, "max_render_rms", None),
            qa_scale=getattr(ns, "qa_scale", None),
            qa_max_pages=getattr(ns, "qa_max_pages", None),
            bilevel=getattr(ns, "bilevel", None),
            bilevel_threshold=getattr(ns, "bilevel_threshold", 200),
        )


class OptimizeSummary(TypedDict, total=False):
    """Shape of the dict returned by :func:`pdf_email_optimizer.optimize`.

    Kept as a ``TypedDict`` (not a dataclass) so the runtime value stays a
    plain JSON-serialisable dict, while importers still get type checking. The
    ``source_*`` / ``intermediate_pdf_*`` keys are present only when a non-PDF
    input was converted first.
    """

    input: str
    output: str
    profile: str
    input_bytes: int
    output_bytes: int
    input_mb: float
    output_mb: float
    target_mb: float
    target_min_mb: float | None
    target_label: str
    preferred_mb: float | None
    met_target: bool
    within_target_range: bool
    strategy: str
    pages: int | None
    private_removed: dict[str, int]
    image_stats: dict[str, Any] | None
    render_qa: dict[str, Any] | None
    quality_ok: bool
    feature_warnings: dict[str, Any]
    warnings: list[str]
    # Bilevel-only
    bilevel_dpi: int
    bilevel_threshold: int
    # Office-source-only
    source: str
    source_bytes: int
    source_mb: float
    source_format: str
    intermediate_pdf_bytes: int
    intermediate_pdf_mb: float
    converted_via: str
    # CLI-only
    report: str


__all__ = ["OptimizeConfig", "OptimizeSummary"]

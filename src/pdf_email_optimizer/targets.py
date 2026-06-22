#!/usr/bin/env python3
"""Target-size parsing and resolution.

A "target window" describes the acceptable output-size band: an optional lower
bound, a hard upper ceiling, and an optional preferred size used to pick among
several acceptable candidates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def output_path_for(input_path: Path, output_arg: str | None) -> Path:
    if output_arg:
        return Path(output_arg).expanduser().resolve()
    return input_path.with_name(f"{input_path.stem}_email.pdf").resolve()


def parse_mb_range(value: str) -> tuple[float, float]:
    normalized = value.strip().lower().replace("mb", "").replace(" ", "")
    for separator in ("-", ":", ","):
        if separator in normalized:
            left, right = normalized.split(separator, 1)
            low = float(left)
            high = float(right)
            if low <= 0 or high <= 0:
                raise ValueError("Target range values must be positive.")
            if low > high:
                low, high = high, low
            return low, high
    exact = float(normalized)
    if exact <= 0:
        raise ValueError("Target value must be positive.")
    return exact, exact


def resolve_target_window(
    *,
    target_mb: float | None = 7.0,
    target: str | None = None,
    target_min_mb: float | None = None,
    target_range_mb: str | None = None,
    preferred_mb: float | None = None,
) -> dict[str, Any]:
    """Resolve the acceptable output-size window from the target-related knobs.

    Accepts plain keyword parameters (not an argparse Namespace), so it can be
    called directly from library code or from a resolved
    :class:`~pdf_email_optimizer.config.OptimizeConfig`.
    """

    if target_range_mb:
        min_mb, max_mb = parse_mb_range(target_range_mb)
    elif target:
        parsed_min, parsed_max = parse_mb_range(target)
        min_mb = parsed_min if parsed_min != parsed_max else target_min_mb
        max_mb = parsed_max
    else:
        min_mb = target_min_mb
        max_mb = target_mb

    if max_mb is None:
        max_mb = 7.0
    if min_mb is not None and min_mb > max_mb:
        min_mb, max_mb = max_mb, min_mb

    if preferred_mb is None and target_range_mb:
        preferred_mb = max_mb
    if preferred_mb is not None and preferred_mb <= 0:
        raise ValueError("Preferred target must be positive.")

    return {
        "min_mb": min_mb,
        "max_mb": max_mb,
        "preferred_mb": preferred_mb,
        "min_bytes": int(min_mb * 1024 * 1024) if min_mb is not None else None,
        "max_bytes": int(max_mb * 1024 * 1024),
        "preferred_bytes": int(preferred_mb * 1024 * 1024) if preferred_mb is not None else None,
        "label": f"{min_mb:g}-{max_mb:g} MB" if min_mb is not None and min_mb != max_mb else f"{max_mb:g} MB",
    }


__all__ = ["output_path_for", "parse_mb_range", "resolve_target_window"]

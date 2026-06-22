#!/usr/bin/env python3
"""Small, dependency-light helpers shared across the optimizer modules.

Everything here is pure and free of project-internal imports so any module can
depend on it without risking an import cycle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def bytes_to_mb(value: int) -> float:
    return value / (1024 * 1024)


def fmt_mb(value: int) -> str:
    return f"{bytes_to_mb(value):.2f} MB"


def file_size(path: Path) -> int:
    return path.stat().st_size


def unique_warnings(warnings: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        unique.append(warning)
    return unique


def object_value(value: Any) -> Any:
    """Resolve an indirect pypdf object, staying best-effort for feature scans."""

    try:
        return value.get_object()
    except Exception:  # noqa: BLE001 - feature detection should stay best-effort.
        return value


def count_items(value: Any) -> int:
    value = object_value(value)
    if value is None:
        return 0
    try:
        return len(value)
    except TypeError:
        return 1


__all__ = [
    "bytes_to_mb",
    "count_items",
    "file_size",
    "fmt_mb",
    "object_value",
    "unique_warnings",
]

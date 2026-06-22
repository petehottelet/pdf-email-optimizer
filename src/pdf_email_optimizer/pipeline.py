#!/usr/bin/env python3
"""The optimization orchestrator.

:func:`optimize` is the library entry point. It accepts an
:class:`~pdf_email_optimizer.config.OptimizeConfig`, resolves profile defaults,
converts Office inputs to PDF if needed, generates candidate outputs, and picks
the best one that fits the requested size window.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from pypdf.errors import PdfReadError

from . import bilevel as bilevel_strategy
from .candidates import (
    choose_best_result,
    normalize_long_edges,
    normalize_quality_ladder,
    result_in_target_window,
    write_candidate,
)
from .config import OptimizeConfig, OptimizeSummary
from .ghostscript import run_ghostscript
from .input_source import attach_source_metadata, resolve_input_source
from .pdf_inspect import inspect_pdf_features
from .pikepdf_backend import structural_optimize as pikepdf_structural_optimize
from .render_qa import compare_render_quality, mark_render_quality
from .targets import output_path_for, resolve_target_window
from .utils import bytes_to_mb, file_size, unique_warnings


def optimize(config: OptimizeConfig) -> OptimizeSummary:
    """Optimize the document described by ``config`` and return a summary dict."""

    resolved = config.resolved()
    source_path, input_path, source_metadata, source_temp_dir = resolve_input_source(str(config.input))
    try:
        return _optimize_resolved(config, resolved, source_path, input_path, source_metadata)
    finally:
        if source_temp_dir is not None:
            shutil.rmtree(source_temp_dir, ignore_errors=True)


def _target_window(resolved: OptimizeConfig) -> dict[str, Any]:
    return resolve_target_window(
        target_mb=resolved.target_mb,
        target=resolved.target,
        target_min_mb=resolved.target_min_mb,
        target_range_mb=resolved.target_range_mb,
        preferred_mb=resolved.preferred_mb,
    )


def _optimize_resolved(
    config: OptimizeConfig,
    resolved: OptimizeConfig,
    source_path: Path,
    input_path: Path,
    source_metadata: dict[str, Any] | None,
) -> OptimizeSummary:
    output_path = output_path_for(source_path, str(resolved.output) if resolved.output else None)
    if source_path == output_path or input_path == output_path:
        raise ValueError("Output path must be different from input path.")
    if output_path.exists() and not resolved.force:
        raise FileExistsError(f"Output already exists: {output_path}. Use --force to replace it.")

    target = _target_window(resolved)
    min_target_bytes = target["min_bytes"]
    max_target_bytes = target["max_bytes"]
    preferred_target_bytes = target["preferred_bytes"]
    inspection = inspect_pdf_features(input_path)
    if inspection["encrypted"]:
        raise PdfReadError("Encrypted PDFs must be unlocked before optimization.")

    if resolved.bilevel is not None:
        bilevel_summary = _optimize_bilevel_pipeline(
            resolved=resolved,
            input_path=input_path,
            output_path=output_path,
            target=target,
            inspection=inspection,
        )
        attach_source_metadata(bilevel_summary, source_metadata)
        return bilevel_summary

    all_warnings: list[str] = list(inspection.get("warnings", []))
    results: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="pdf-email-opt-") as tmp_name:
        tmp_dir = Path(tmp_name)
        cleanup_path = tmp_dir / "cleanup.pdf"
        cleanup = write_candidate(
            input_path,
            cleanup_path,
            strip_private=not resolved.no_strip_private,
            image_quality=None,
            long_edge=None,
            min_image_pixels=resolved.min_image_pixels,
            min_image_bytes=resolved.min_image_bytes,
            flatten_alpha=resolved.flatten_alpha,
        )
        cleanup["strategy"] = "structural-cleanup"
        cleanup["quality_ok"] = True
        results.append(cleanup)

        if resolved.pikepdf != "never":
            pikepdf_path = tmp_dir / "pikepdf.pdf"
            pikepdf_result = pikepdf_structural_optimize(cleanup_path, pikepdf_path, warnings=all_warnings)
            if pikepdf_result is not None:
                pikepdf_candidate = {
                    "path": pikepdf_result["path"],
                    "size_bytes": pikepdf_result["size_bytes"],
                    "pages": cleanup["pages"],
                    "compressed_pages": cleanup.get("compressed_pages"),
                    "private_removed": cleanup.get("private_removed", {}),
                    "image_stats": None,
                    "strategy": "pikepdf-structural",
                    "quality_ok": True,
                    "warnings": pikepdf_result.get("warnings", []),
                }
                results.append(pikepdf_candidate)

        quality_ladder, long_edge_ladder = resolved.profile_ladders()
        lossless_floor = min(result["size_bytes"] for result in results)
        if lossless_floor > max_target_bytes and not resolved.no_image_recompress:
            quality_values = normalize_quality_ladder(
                resolved.image_quality,
                resolved.min_image_quality,
                quality_ladder,
            )
            long_edges = normalize_long_edges(
                resolved.long_edge,
                resolved.min_long_edge,
                long_edge_ladder,
            )
            for long_edge in long_edges:
                for quality in quality_values:
                    candidate_path = tmp_dir / f"images_q{quality}_edge{long_edge or 'native'}.pdf"
                    candidate = write_candidate(
                        input_path,
                        candidate_path,
                        strip_private=not resolved.no_strip_private,
                        image_quality=quality,
                        long_edge=long_edge,
                        min_image_pixels=resolved.min_image_pixels,
                        min_image_bytes=resolved.min_image_bytes,
                        flatten_alpha=resolved.flatten_alpha,
                    )
                    candidate["strategy"] = "image-recompress"
                    mark_render_quality(
                        candidate,
                        input_path,
                        render_qa=resolved.render_qa,
                        min_render_psnr=resolved.min_render_psnr,
                        max_render_rms=resolved.max_render_rms,
                        qa_scale=resolved.qa_scale,
                        qa_max_pages=resolved.qa_max_pages,
                    )
                    results.append(candidate)
                    if candidate.get("quality_ok", True) and result_in_target_window(
                        candidate,
                        min_target_bytes,
                        max_target_bytes,
                    ):
                        break
                if results[-1].get("quality_ok", True) and result_in_target_window(
                    results[-1],
                    min_target_bytes,
                    max_target_bytes,
                ):
                    break

        best = choose_best_result(
            results,
            min_bytes=min_target_bytes,
            max_bytes=max_target_bytes,
            preferred_bytes=preferred_target_bytes,
        )
        shutil.copy2(best["path"], output_path)
        best = {**best, "path": str(output_path)}

        gs_mode, routed_for_encoding = _ghostscript_mode(config, resolved, inspection)
        if best["size_bytes"] > max_target_bytes and gs_mode != "never":
            gs_input = output_path if gs_mode == "auto" else input_path
            gs_result = run_ghostscript(gs_input, output_path, target_mb=target["max_mb"], warnings=all_warnings)
            if gs_result and gs_result["size_bytes"] < best["size_bytes"]:
                best = {**gs_result, "strategy": "ghostscript-fallback"}
                if routed_for_encoding:
                    all_warnings.append(
                        "Routed to Ghostscript automatically: the built-in recompressor cannot "
                        "reduce JPEG2000/CCITT/JBIG2 image streams, so Ghostscript rewrote the "
                        "images at the page level. Pass --ghostscript never to opt out."
                    )

    for result in results:
        all_warnings.extend(result.get("warnings", []))
    output_bytes = file_size(output_path)
    within_target_range = result_in_target_window({"size_bytes": output_bytes}, min_target_bytes, max_target_bytes)
    if output_bytes > max_target_bytes and resolved.profile == "quality":
        all_warnings.append(
            f"Target not met. The requested {target['label']} target conflicts with the selected quality profile. "
            f"Output is {bytes_to_mb(output_bytes):.2f} MB. To go smaller, rerun with --profile aggressive, "
            "split the PDF, remove pages, or accept lower image fidelity."
        )
    if min_target_bytes is not None and output_bytes < min_target_bytes:
        all_warnings.append(
            "Output is below the requested range. It was not padded upward because adding bytes would not improve email quality."
        )
    if (
        min_target_bytes is None
        and preferred_target_bytes is not None
        and output_bytes < int(preferred_target_bytes * 0.9)
    ):
        all_warnings.append(
            "Output is well below the preferred size. It was not padded upward because adding bytes would not improve email quality."
        )
    all_warnings = unique_warnings(all_warnings)

    summary: OptimizeSummary = {
        "input": str(input_path),
        "output": str(output_path),
        "profile": resolved.profile,
        "input_bytes": file_size(input_path),
        "output_bytes": output_bytes,
        "input_mb": round(bytes_to_mb(file_size(input_path)), 3),
        "output_mb": round(bytes_to_mb(output_bytes), 3),
        "target_mb": target["max_mb"],
        "target_min_mb": target["min_mb"],
        "target_label": target["label"],
        "preferred_mb": target["preferred_mb"],
        "met_target": output_bytes <= max_target_bytes,
        "within_target_range": within_target_range,
        "strategy": best.get("strategy", "unknown"),
        "pages": best.get("pages"),
        "private_removed": best.get("private_removed", {}),
        "image_stats": best.get("image_stats"),
        "render_qa": best.get("render_qa"),
        "quality_ok": best.get("quality_ok", True),
        "feature_warnings": inspection,
        "warnings": all_warnings,
    }
    attach_source_metadata(summary, source_metadata)
    return summary


def _ghostscript_mode(
    config: OptimizeConfig,
    resolved: OptimizeConfig,
    inspection: dict[str, Any],
) -> tuple[str, bool]:
    """Return ``(effective_ghostscript_mode, routed_for_encoding)``.

    The auto-route distinguishes a profile-default ``"never"`` from a user
    explicitly passing ``--ghostscript never`` by reading the *raw* config: a
    raw value of ``None`` means "profile default", anything else means the
    caller asked for it. When pypdf can't recompress the input's image
    encodings, a profile-default ``never`` is upgraded to ``"auto"`` so the only
    viable path isn't silently skipped.
    """

    mode = resolved.ghostscript or "never"
    has_unsupported = int(inspection.get("pypdf_unsupported_images") or 0) > 0
    user_disabled = config.ghostscript == "never"
    if has_unsupported and not resolved.no_image_recompress and not user_disabled and mode == "never":
        return "auto", True
    return mode, False


def _optimize_bilevel_pipeline(
    *,
    resolved: OptimizeConfig,
    input_path: Path,
    output_path: Path,
    target: dict[str, Any],
    inspection: dict[str, Any],
) -> OptimizeSummary:
    """Run the ``--bilevel`` short-circuit and return a summary in the standard shape.

    Skips the entire image-recompress ladder and the Ghostscript fallback: when
    a user explicitly asks for bilevel they've already accepted a fully
    destructive conversion, so the only useful work is the bilevel pass itself
    plus optional render-QA reporting.
    """

    bilevel_result = bilevel_strategy.optimize_bilevel(
        input_path,
        output_path,
        dpi=int(resolved.bilevel),
        threshold=int(resolved.bilevel_threshold),
    )
    all_warnings: list[str] = list(inspection.get("warnings", []))
    all_warnings.extend(bilevel_result.get("warnings", []))

    if resolved.render_qa:
        try:
            qa = compare_render_quality(
                input_path,
                output_path,
                scale=resolved.qa_scale,
                max_pages=resolved.qa_max_pages,
            )
            bilevel_result["render_qa"] = qa
        except Exception as exc:  # noqa: BLE001
            all_warnings.append(f"Render QA unavailable for bilevel output: {exc}")

    output_bytes = file_size(output_path)
    max_target_bytes = target["max_bytes"]
    min_target_bytes = target["min_bytes"]
    within_target_range = result_in_target_window(
        {"size_bytes": output_bytes},
        min_target_bytes,
        max_target_bytes,
    )
    if min_target_bytes is not None and output_bytes < min_target_bytes:
        all_warnings.append(
            "Output is below the requested range. Bilevel conversion is one-shot; "
            "rerun with a higher --bilevel DPI to land back inside the window."
        )

    all_warnings = unique_warnings(all_warnings)
    summary: OptimizeSummary = {
        "input": str(input_path),
        "output": str(output_path),
        "profile": resolved.profile,
        "input_bytes": file_size(input_path),
        "output_bytes": output_bytes,
        "input_mb": round(bytes_to_mb(file_size(input_path)), 3),
        "output_mb": round(bytes_to_mb(output_bytes), 3),
        "target_mb": target["max_mb"],
        "target_min_mb": target["min_mb"],
        "target_label": target["label"],
        "preferred_mb": target["preferred_mb"],
        "met_target": output_bytes <= max_target_bytes,
        "within_target_range": within_target_range,
        "strategy": bilevel_result["strategy"],
        "pages": bilevel_result["pages"],
        "private_removed": {},
        "image_stats": None,
        "render_qa": bilevel_result.get("render_qa"),
        "quality_ok": True,
        "bilevel_dpi": bilevel_result["bilevel_dpi"],
        "bilevel_threshold": bilevel_result["bilevel_threshold"],
        "feature_warnings": inspection,
        "warnings": all_warnings,
    }
    return summary


__all__ = ["optimize"]

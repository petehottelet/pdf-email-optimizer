#!/usr/bin/env python3
"""Migration tombstone for the old monolithic ``optimizer`` module.

Through v2.x everything lived in this single module and the public functions
took an ``argparse.Namespace``. v3.0.0 split the implementation into focused
modules and replaced the Namespace API with a typed
:class:`pdf_email_optimizer.config.OptimizeConfig`.

This module intentionally exposes no functionality. Importing a name from it
raises :class:`ImportError` with a pointer to the new home so upgrades fail
loudly and informatively instead of with a confusing ``AttributeError`` deep in
user code.
"""

from __future__ import annotations

_MOVED = {
    "optimize": "pdf_email_optimizer.optimize (now takes an OptimizeConfig, not argparse args)",
    "audit_pdf": "pdf_email_optimizer.audit",
    "audit": "pdf_email_optimizer.audit",
    "build_parser": "pdf_email_optimizer.cli.build_parser",
    "main": "pdf_email_optimizer.cli.main",
    "OptimizeConfig": "pdf_email_optimizer.OptimizeConfig",
    "PROFILE_DEFAULTS": "pdf_email_optimizer.profiles.PROFILE_DEFAULTS",
    "apply_profile_defaults": "OptimizeConfig.resolved() (pdf_email_optimizer.config)",
    "resolve_target_window": "pdf_email_optimizer.targets.resolve_target_window (now takes keyword args)",
    "parse_mb_range": "pdf_email_optimizer.targets.parse_mb_range",
    "output_path_for": "pdf_email_optimizer.targets.output_path_for",
    "resolve_input_source": "pdf_email_optimizer.input_source.resolve_input_source",
    "recompress_images": "pdf_email_optimizer.images.recompress_images",
    "write_candidate": "pdf_email_optimizer.candidates.write_candidate",
    "choose_best_result": "pdf_email_optimizer.candidates.choose_best_result",
    "result_in_target_window": "pdf_email_optimizer.candidates.result_in_target_window",
    "run_ghostscript": "pdf_email_optimizer.ghostscript.run_ghostscript",
    "compare_render_quality": "pdf_email_optimizer.render_qa.compare_render_quality",
    "mark_render_quality": "pdf_email_optimizer.render_qa.mark_render_quality",
    "inspect_pdf_features": "pdf_email_optimizer.pdf_inspect.inspect_pdf_features",
    "print_summary": "pdf_email_optimizer.reporting.print_summary",
    "print_audit": "pdf_email_optimizer.reporting.print_audit",
    "build_markdown_report": "pdf_email_optimizer.reporting.build_markdown_report",
    "write_report": "pdf_email_optimizer.reporting.write_report",
}


def __getattr__(name: str):
    if name in _MOVED:
        raise ImportError(
            f"`pdf_email_optimizer.optimizer.{name}` was removed in v3.0.0. "
            f"Use `{_MOVED[name]}` instead. The library API now centers on "
            "`from pdf_email_optimizer import optimize, audit, OptimizeConfig`."
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

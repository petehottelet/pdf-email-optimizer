"""Tools for making email-safe PDF copies while preserving visual quality.

Library entry points::

    from pdf_email_optimizer import optimize, audit, OptimizeConfig

    summary = optimize(OptimizeConfig(input="deck.pdf", target_mb=7, profile="balanced"))
"""

from __future__ import annotations

from .config import OptimizeConfig, OptimizeSummary
from .errors import PdfEmailOptimizerError, UnsupportedInputError
from .pdf_inspect import audit
from .pipeline import optimize
from .profiles import PROFILE_DEFAULTS

__version__ = "3.0.0"

__all__ = [
    "OptimizeConfig",
    "OptimizeSummary",
    "PROFILE_DEFAULTS",
    "PdfEmailOptimizerError",
    "UnsupportedInputError",
    "__version__",
    "audit",
    "optimize",
]

"""Project-specific exception types."""

from __future__ import annotations


class PdfEmailOptimizerError(Exception):
    """Base exception for optimizer integration code."""


class UnsupportedInputError(PdfEmailOptimizerError, ValueError):
    """Raised when an input file is neither a PDF nor a supported Office format.

    Also a :class:`ValueError` so existing callers that catch bad-input as a
    ``ValueError`` keep working across the v3 API change.
    """


__all__ = [
    "PdfEmailOptimizerError",
    "UnsupportedInputError",
]

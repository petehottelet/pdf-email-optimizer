# Known Limitations

- Some PDFs cannot reach a requested target without visible degradation.
- `quality` mode may miss the target size.
- Encrypted PDFs must be unlocked first.
- Complex transparency may be skipped or require `--flatten-alpha`.
- Ghostscript fallback may alter metadata, structure, text selectability, or rendering details.
- Render QA is an automated signal, not human proof.
- PDF renderers can disagree.
- Very small screenshots, maps, UI captures, and text-heavy raster images may not tolerate recompression.
- This tool creates email copies. It is not an archival, accessibility, PDF/A, PDF/X, or prepress validator.
- Manually check high-stakes documents.

---
name: pdf-email-optimizer
description: Shrink large PDFs and Office documents to email-safe sizes while preserving visual quality. Use when a PDF, Word doc, PowerPoint deck, or Excel sheet is too large to email, attach, send, or upload and must fit under a target size (for example 5-7 MB or a Gmail/Outlook limit) without visibly degrading photos, scans, screenshots, maps, or design-tool exports (Illustrator, InDesign). Accepts .pdf, .docx, .doc, .pptx, .ppt, .xlsx, .xls, .odt, .odp, .ods, and .rtf inputs (Office formats are converted to PDF via LibreOffice headless mode, then optimized). Supports quality/balanced/aggressive/compress profiles plus opt-in --bilevel for typeset archival scans, audit mode, JSON summaries, Markdown reports, and render QA.
license: MIT
---

# PDF Email Optimizer

## Core Rules

1. Never overwrite the source document. Write an optimized copy to a new path.
2. Accept any supported input format directly — `.pdf`, `.docx`, `.doc`, `.pptx`, `.ppt`, `.xlsx`, `.xls`, `.odt`, `.odp`, `.ods`, `.rtf`. Office files are converted to PDF via LibreOffice automatically; do not ask the user to convert by hand.
3. Use `--quality` when the user mentions photos, images, screenshots, maps, visual fidelity, sharpness, or "do not degrade."
4. Use `--balanced` for ordinary email optimization.
5. Use `--aggressive` only when the user explicitly accepts visible quality loss or asks for the smallest possible file.
6. Use `--compress` when the user must force a much tighter filesize (e.g. "under 1 MB") and accepts visible compression, but still wants normal RGB output (no bilevel). Always pair it with an explicit `--target-mb`.
7. Use `--bilevel <DPI>` only for typeset / line-art archival scans (microfilm-style reports, book scans, government archives). It is destructive (1-bit B&W) and must be a deliberate user choice.
8. Run render QA when available for quality-sensitive work.
9. Report original source size, intermediate PDF size (if converted), final size, target status, profile, strategy, and warnings.
10. If quality mode misses the target, say clearly that the target conflicts with image fidelity.
11. If conversion fails because LibreOffice isn't installed, surface the install hint from the error message (apt / brew / choco / direct download) rather than failing silently.

## Commands

```bash
pdf-email-optimizer input.pdf output_email.pdf --target-mb 7
pdf-email-optimizer deck.pptx deck_email.pdf --target-mb 7 --balanced
pdf-email-optimizer report.docx report_email.pdf --target-mb 5 --quality
pdf-email-optimizer sheet.xlsx sheet_email.pdf --target-mb 5
pdf-email-optimizer input.pdf output_email.pdf --target 7mb --quality
pdf-email-optimizer input.pdf output_email.pdf --range 5-7mb --quality
pdf-email-optimizer input.pdf output_email.pdf --target-mb 5 --preferred-mb 5 --balanced
pdf-email-optimizer input.pdf output_small.pdf --target-mb 5 --aggressive
pdf-email-optimizer input.pdf output_tiny.pdf --target-mb 1 --compress
pdf-email-optimizer scan.pdf scan_email.pdf --bilevel 100
pdf-email-optimizer input.pdf output_email.pdf --target-mb 7 --no-image-recompress
pdf-email-optimizer input.pdf output_email.pdf --target-mb 7 --json
pdf-email-optimizer input.pdf output_email.pdf --target-mb 7 --report report.md
pdf-email-optimizer input.pdf --audit --json
pdf-email-optimizer deck.pptx --audit --json
```

Backward-compatible script form:

```bash
python scripts/optimize_pdf_email.py input.pdf output_email.pdf --target-mb 7
```

## Size Targets

- "Under 7 MB" or "max 7 MB": use `--target-mb 7` or `--target 7mb`.
- "Between 5 and 7 MB": use `--range 5-7mb`.
- "Make it 5 MB": use `--target-mb 5 --preferred-mb 5`.
- If cleanup alone makes the file smaller than a requested range, keep it smaller. Do not pad files.

## Audit First

Use audit mode when the user asks why a PDF is large or when the right strategy is unclear:

```bash
pdf-email-optimizer input.pdf --audit --json
```

Audit reports file size, page count, image count, private payload indicators, forms, annotations, transparency, masks, and recommended profile.

## Visual QA

When available:

```bash
pdf-email-render-compare original.pdf optimized.pdf --output-dir qa-renders
```

Check page count, missing layers, clipped art, changed colors, broken transparency, and softened important images. Automated render QA is a signal, not a human proof.

## Quality Conflict Response

Use this pattern when `quality` cannot hit the requested target:

```text
Target not met. The requested 5 MB target conflicts with the selected quality profile. Output is 8.4 MB.
To go smaller, rerun with --profile aggressive or --profile compress, split the PDF, remove pages, or accept lower image fidelity.
```

## Failure Handling

- Encrypted PDFs must be unlocked first.
- Existing outputs require `--force`.
- Transparent images may be skipped unless `--flatten-alpha` is appropriate.
- Ghostscript is optional; if missing, report the warning and keep the best non-Ghostscript result.
- LibreOffice is required for Office input formats. If `soffice` is missing the tool will raise `OfficeConversionError` with install hints (apt, brew, choco, or libreoffice.org); pass them on to the user verbatim.
- For high-stakes documents, ask the user to spot-check the final PDF locally.

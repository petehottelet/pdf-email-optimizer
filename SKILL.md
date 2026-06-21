---
name: pdf-email-optimizer
description: Shrink large PDFs to email-safe sizes while preserving visual quality. Use when a PDF is too large to email, attach, send, or upload and must fit under a target size (for example 5-7 MB or a Gmail/Outlook limit) without visibly degrading photos, scans, screenshots, maps, or design-tool exports (Illustrator, InDesign). Supports quality/balanced/aggressive profiles, audit mode, JSON summaries, Markdown reports, and render QA.
license: MIT
---

# PDF Email Optimizer

## Core Rules

1. Never overwrite the source PDF. Write an optimized copy to a new path.
2. Use `--quality` when the user mentions photos, images, screenshots, maps, visual fidelity, sharpness, or "do not degrade."
3. Use `--balanced` for ordinary email optimization.
4. Use `--aggressive` only when the user explicitly accepts visible quality loss or asks for the smallest possible file.
5. Run render QA when available for quality-sensitive work.
6. Report original size, final size, target status, profile, strategy, and warnings.
7. If quality mode misses the target, say clearly that the target conflicts with image fidelity.

## Commands

```bash
pdf-email-optimizer input.pdf output_email.pdf --target-mb 7
pdf-email-optimizer input.pdf output_email.pdf --target 7mb --quality
pdf-email-optimizer input.pdf output_email.pdf --range 5-7mb --quality
pdf-email-optimizer input.pdf output_email.pdf --target-mb 5 --preferred-mb 5 --balanced
pdf-email-optimizer input.pdf output_small.pdf --target-mb 5 --aggressive
pdf-email-optimizer input.pdf output_email.pdf --target-mb 7 --no-image-recompress
pdf-email-optimizer input.pdf output_email.pdf --target-mb 7 --json
pdf-email-optimizer input.pdf output_email.pdf --target-mb 7 --report report.md
pdf-email-optimizer input.pdf --audit --json
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
To go smaller, rerun with --profile aggressive, split the PDF, remove pages, or accept lower image fidelity.
```

## Failure Handling

- Encrypted PDFs must be unlocked first.
- Existing outputs require `--force`.
- Transparent images may be skipped unless `--flatten-alpha` is appropriate.
- Ghostscript is optional; if missing, report the warning and keep the best non-Ghostscript result.
- For high-stakes documents, ask the user to spot-check the final PDF locally.

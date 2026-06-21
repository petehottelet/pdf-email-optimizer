# Agent Usage

Use the local `SKILL.md` when an agent runtime supports skills. The core workflow is still plain CLI, so any automation can call the installed command.

## Prompt: Make This Under 7 MB But Keep Images Sharp

Recommended command:

```bash
pdf-email-optimizer input.pdf output_email.pdf --target 7mb --quality --report output_report.md
```

Expected response summary:

```text
Optimized copy written to output_email.pdf.
Original size: 12.4 MB. Final size: 6.8 MB. Target: 7 MB, met.
Profile: quality. Strategy: image-recompress.
Warnings: none.
```

## Prompt: Compress This As Much As Possible

Recommended command:

```bash
pdf-email-optimizer input.pdf output_small.pdf --target-mb 5 --aggressive
```

Expected response summary should clearly say that visible quality loss is possible.

## Prompt: Make It Between 5 And 7 MB

Recommended command:

```bash
pdf-email-optimizer input.pdf output_email.pdf --range 5-7mb --quality
```

If cleanup alone makes the file smaller than 5 MB, keep the smaller file and explain that padding would not improve quality.

## Prompt: Audit This PDF

Recommended command:

```bash
pdf-email-optimizer input.pdf --audit --json
```

Report file size, page count, image count, private payload indicators, warnings, and recommended profile.

## Quality Conflict Template

```text
Target not met. The requested 5 MB target conflicts with the selected quality profile. Output is 8.4 MB.
To go smaller, rerun with --profile aggressive, split the PDF, remove pages, or accept lower image fidelity.
```

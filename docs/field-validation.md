# Field validation

Real-world results contributed by people using `pdf-email-optimizer` on their own PDFs. The bundled benchmark corpus is honest but synthetic; field validation is the part that's hard to fake.

If you want to help, run the steps below on a PDF you'd otherwise need to email, then share the numbers (and, only if it's safe, the PDF itself) via the [fixture submission issue template](../.github/ISSUE_TEMPLATE/fixture-submission.yml).

## Quick test

```bash
pipx install pdf-email-optimizer

pdf-email-optimizer input.pdf output_email.pdf --target-mb 7 --balanced --report report.md
# or, for photographs, screenshots, maps, "do not degrade" requests:
pdf-email-optimizer input.pdf output_email.pdf --target-mb 7 --quality --report report.md
```

Then check, side by side, whether `output_email.pdf` looks acceptable for emailing:

```bash
pdf-email-render-compare input.pdf output_email.pdf --output-dir qa-renders
```

## What to share

- PDF category (marketing deck, scan, screenshot report, etc.)
- Original size and optimized size (MB)
- Command used (full CLI invocation)
- Whether it emailed successfully on Gmail / Outlook / your provider
- Whether the optimized file looked correct
- Any weird PDF behavior

Use the [fixture submission template](../.github/ISSUE_TEMPLATE/fixture-submission.yml) to share results. Do not attach private PDFs to a public issue.

## Anonymized results

The table below is seeded empty. As field reports come in, maintainers add anonymized rows. Please do not edit this table directly in a PR; submit via the issue template above.

| User type | PDF type | Original | Output | Reduction | Emailed | Visual result |
|---|---|---:|---:|---:|---|---|
| _your report here_ | _e.g. Marketing brochure_ | _e.g. 24.8 MB_ | _e.g. 7.6 MB_ | _e.g. 69%_ | _yes/no_ | _looked good / minor issue / broken_ |

## Privacy

`pdf-email-optimizer` runs entirely locally. It does not upload PDFs anywhere and does not collect telemetry. The structural cleanup pass also strips creator-only payloads such as `/PieceInfo` and `/LastModified` from your output. See [`SECURITY.md`](../SECURITY.md) for security reporting.

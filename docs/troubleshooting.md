# Troubleshooting

## Output Already Exists

The optimizer refuses to replace an existing output file by default.

```bash
pdf-email-optimizer input.pdf output.pdf --force
```

## Encrypted PDF

Unlock the PDF first, then rerun the optimizer. The tool does not bypass encryption.

## Render QA Unavailable

Install the package with QA dependencies:

```bash
python -m pip install -e ".[qa]"
```

## Ghostscript Missing

Ghostscript is optional. Install it only if you need the fallback path for aggressive compression.

## Target Not Met

In `quality` mode this usually means the requested file size conflicts with visual fidelity. Choose a larger target, remove pages, split the PDF, replace source images, or rerun with `--aggressive` if visible quality loss is acceptable.

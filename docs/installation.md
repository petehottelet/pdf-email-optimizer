# Installation

## From A Checkout

```bash
python -m pip install -e ".[dev]"
pdf-email-optimizer --help
```

## Package Runner

After package publication:

```bash
pipx install pdf-email-optimizer
pdf-email-optimizer input.pdf output.pdf --target-mb 7
```

```bash
uvx pdf-email-optimizer input.pdf output.pdf --target 7mb
```

## Optional System Dependency

Ghostscript is optional. The optimizer works without it for the normal `quality` and `balanced` workflows.

- macOS: `brew install ghostscript`
- Debian/Ubuntu: `sudo apt-get install ghostscript`
- Windows: install from the official Ghostscript release page

If Ghostscript is missing and a fallback is requested, the optimizer warns and continues safely.

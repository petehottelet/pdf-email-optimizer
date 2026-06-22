# JSON Output

Use:

```bash
pdf-email-optimizer input.pdf output.pdf --target-mb 7 --json
```

The output validates against [../schema/output-summary.schema.json](../schema/output-summary.schema.json).

Example:

```json
{
  "input": "/path/input.pdf",
  "output": "/path/output.pdf",
  "profile": "quality",
  "input_bytes": 10485760,
  "output_bytes": 6291456,
  "input_mb": 10.0,
  "output_mb": 6.0,
  "target_mb": 7.0,
  "target_min_mb": null,
  "target_label": "7 MB",
  "preferred_mb": null,
  "met_target": true,
  "within_target_range": true,
  "strategy": "image-recompress",
  "pages": 8,
  "private_removed": {},
  "image_stats": null,
  "render_qa": null,
  "quality_ok": true,
  "warnings": []
}
```

The `strategy` field is one of `structural-cleanup`, `pikepdf-structural`, `image-recompress`, `ghostscript-fallback`, `bilevel-g4`, or `unknown`.

Treat `warnings` as user-facing. Agents and automation should relay target misses, encrypted PDF failures, transparency concerns, and Ghostscript fallback warnings.

## Library usage

The same summary dict is returned by the Python API. As of v3.0.0 the core
functions take a typed `OptimizeConfig` instead of parsed CLI args:

```python
from pdf_email_optimizer import optimize, audit, OptimizeConfig

summary = optimize(OptimizeConfig(input="deck.pdf", target_mb=7, profile="balanced"))
report = audit("deck.pdf")  # inspection + recommended_profile / recommended_strategy
```

`audit()` additionally reports image-encoding counts (`jpeg2000_images`,
`ccitt_images`, `jbig2_images`, `pypdf_unsupported_images`) and a
`recommended_strategy` (`"ghostscript"`, `"bilevel"`, or `null`) for inputs the
built-in recompressor can't process directly.

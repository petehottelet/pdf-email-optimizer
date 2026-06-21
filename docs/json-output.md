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

The `strategy` field is one of `structural-cleanup`, `pikepdf-structural`, `image-recompress`, `ghostscript-fallback`, or `unknown`.

Treat `warnings` as user-facing. Agents and automation should relay target misses, encrypted PDF failures, transparency concerns, and Ghostscript fallback warnings.

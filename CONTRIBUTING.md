# Contributing

Thanks for improving PDF Email Optimizer.

## Development

```bash
python -m pip install -e ".[dev]"
pytest                     # full suite (includes slow integration tests)
pytest -m "not integration"  # fast unit tests only
pytest --cov
ruff check .
python -m build
```

## Tests

- Unit tests live in `tests/` and use small synthetic PDFs generated at runtime.
- Integration tests (`tests/test_integration.py`, marked `integration`) run the
  optimizer end-to-end against realistic generated fixtures (design-tool
  exports, photos, screenshots, transparency, forms, scans, encrypted files).
  They require `reportlab` (included in the `dev` extra) and are skipped if it
  is unavailable.
- Include tests for behavior changes. For PDF edge cases, prefer small synthetic
  fixtures that can be regenerated.

## Fixtures

Do not commit confidential or copyrighted PDFs. Use generated, public domain,
CC0, or explicitly redistributable fixtures only, and document the origin and
license of each fixture.

The benchmark/test fixtures are synthesized from scratch:

```bash
python benchmarks/make_fixtures.py            # regenerate all fixtures
python benchmarks/make_fixtures.py --only photo_brochure
```

See [`benchmarks/fixtures/README.md`](benchmarks/fixtures/README.md) for the
catalog and what each fixture exercises.

## Benchmarks and gallery

```bash
python benchmarks/run_benchmarks.py   # writes benchmarks/results/latest.{json,md}
python benchmarks/make_gallery.py     # writes docs/gallery/*.png
```

When optimizer behavior changes, regenerate both and commit the updated
`benchmarks/results/latest.md` and gallery images so published numbers stay
honest. Never hand-edit benchmark numbers.

## Optional backends

- `pikepdf`/`qpdf`: lossless structural pass, installed via
  `pip install "pdf-email-optimizer[pikepdf]"`. It bundles qpdf, so no system
  binary is needed.
- Ghostscript: external binary used only for the aggressive last-resort raster
  rewrite.

## Pull requests

Keep changes focused, add tests, run `ruff check .` and `pytest`, and update the
`[Unreleased]` section of [`CHANGELOG.md`](CHANGELOG.md).

## Releases

1. Move the `[Unreleased]` entries under a new version heading with the date.
2. Bump the version in `pyproject.toml` (and the README badge).
3. Tag the release and let CI build and publish.

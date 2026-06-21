# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.0] - 2026-06-21

### Added

- New `--bilevel [DPI]` strategy: render every page as 1-bit black &
  white at the given DPI and emit a CCITT Group 4 (fax) PDF. This is the
  right compression for typeset / line-art archival scans where the page
  is black ink on paper; it gets the 606-page 33 MB NASA report down to
  6.65 MB (79.9% reduction) where JPEG-based recompression bottomed out
  at 20 MB. Companion flag `--bilevel-threshold` (0-255, default 200)
  tunes the brightness cutoff. Strategy is destructive (color and
  grayscale are thresholded to 1-bit) and is **never auto-selected** -
  it's an explicit opt-in via the CLI flag or via the new
  `SamplePlan.bilevel_dpi` field in `benchmarks/run_samples.py`.
- New `[bilevel]` optional dependency group pulls in `img2pdf>=0.6`.
- New module `pdf_email_optimizer.bilevel` and `bilevel-g4` value in the
  output-summary `strategy` enum. JSON summary gains optional
  `bilevel_dpi` and `bilevel_threshold` keys when the bilevel path runs.
- `benchmarks/run_samples.py` `SamplePlan` learned `bilevel_dpi` and
  `bilevel_threshold`. The 606-page archive scan (`archive_scan_1976a`)
  is now wired to use it; its real-world result moves from 20.58 MB
  (37.7% reduction) to **6.65 MB (79.9% reduction)** with PSNR 19 dB -
  the metric stops being meaningful at 1-bit but visual review confirms
  text and line-art are crisp.
- README real-world section now averages **72.9% reduction across all
  eight samples** (up from 67.6% in 1.5.0) and gained an "Archival
  opt-in: `--bilevel`" subsection documenting when and how to use the
  new strategy.
- Source attribution for the three NASA-prefixed sample PDFs:
  `19760021505.pdf`, `19760026509.pdf`, and `20170009128.pdf` are
  obtained from the
  [NASA Technical Reports Server (NTRS)](https://ntrs.nasa.gov/). README
  now links NTRS inline; full per-file provenance with NTRS accession
  numbers lives in
  [`docs/sample-provenance.md`](docs/sample-provenance.md).

### Changed

- `compare_render_quality` tolerates sub-point page-size rounding
  (within four pixels in each dimension) by resizing the candidate
  render to the original's dimensions before diff, instead of declaring
  the pages incomparable. This is what enables render QA to produce
  meaningful PSNR numbers for `img2pdf`-derived bilevel outputs whose
  page sizes shift by 1-2 pts due to integer-pixel rounding.

## [1.5.0] - 2026-06-21

### Added

- Ghostscript-backed strategy for PowerPoint exports and archival scans the
  Python image-recompress ladder cannot safely process (PowerPoint glyph
  rasters, JBIG2-encoded archival pages). `benchmarks/run_samples.py` learned
  `ghostscript_image_dpi` and `ghostscript_jpeg_quality` fields on
  `SamplePlan`; when set, the optimizer shells out to Ghostscript's
  `pdfwrite` page-stream compressor so files that would OOM or fail
  decode still produce honest email-safe outputs.
- Real-world sample set extended from four to eight to cover document
  categories users actually email:
    - **Government report (2017)**: 12.69 MB `.pdf` → **6.86 MB** (45.9%,
      PSNR 46.9 dB)
    - **Research paper (2024)**: 9.57 MB `.pdf` → **6.59 MB** (31.1%,
      PSNR 38.8 dB)
    - **Archival scan, 1976 (A)**: 33.04 MB / 606 pages → **20.58 MB**
      (37.7%, pixel-identical lossless rewrite). The Python ladder cannot
      decode this file's embedded JBIG2 images without `jbig2dec`; the
      Ghostscript fallback handles them natively.
    - **Archival scan, 1976 (B)**: 88.68 MB / 192 pages → **23.80 MB**
      (73.2%, PSNR 32.5 dB - visible compression but legible at email
      zoom). Both archival scans now fit under Gmail's 25 MB attachment
      limit where neither did before.
- `.github/workflows/publish.yaml` for tag-triggered PyPI publication via
  Trusted Publisher OIDC (no API token required).

### Changed

- Real-world sample suite reframed end-to-end. Photo brochure (138.74 MB
  `.pdf` → 6.51 MB / 95.3% / PSNR 48.6 dB), Lossless image PDF (69.65 MB
  `.pdf` → 2.93 MB / 95.8% / PSNR 54.6 dB), Financial services proposal
  (36.31 MB `.pptx` → 4.97 MB / 86.3% / PSNR 41.3 dB), Bank report (30.16 MB
  `.pptx` → 7.41 MB / 75.5% / PSNR 38.7 dB) plus the four new samples
  above. Average reduction across all eight real documents is 67.6%.
- `benchmarks/make_charts.py` adapts figure width to the sample count
  (`fig_width = max(12, 2 + 1.6 * n)`) and downsizes label fonts past five
  samples so the chart stays legible.
- README real-world results and benchmarks tables rendered as HTML with
  explicit `<th width="...">` so they stretch to full README width on GitHub
  (GitHub strips `<col style>` so a `<colgroup>` alone falls back to
  content-width).
- Charts switched from R/G to B/G palette: "Original" bars are now blue,
  "Email PDF" bars stay green. Linear MB axis throughout so bar heights are
  honestly proportional to on-disk file sizes.
- Synthetic-fixture regression section in the README collapsed to a short
  pointer at `benchmarks/results/latest.md`; the wall of mostly-0.1%
  reductions on sub-MB fixtures was burying the headline real-world
  numbers without adding signal.
- GitHub repository rebuilt from a single fresh-history initial commit so
  the Contributors list cleanly shows one author (`petehottelet`); content
  is bit-identical to the prior history at the point of recreation.

### Removed

- `docs/charts/size_reduction.png` (the redundant horizontal-bar chart).

## [Unreleased]

### Changed

- Real-world sample set retargeted at the office-doc-to-email pipeline:
  `Financial_Services_Proposal.pptx` (36.31 MB) → 4.97 MB email PDF (86.3%
  headline reduction, PSNR 41.3 dB) and `Bank_Report.pptx` (25.95 MB) →
  12.81 MB email PDF (50.6% headline reduction, pixel-identical lossless
  cleanup) replace the previous deck and spreadsheet samples; the spreadsheet
  case has been removed.
- `benchmarks/run_samples.py` now tracks the original office document size
  alongside the intermediate converted PDF and exposes
  `headline_reduction_percent` / `headline_source_mb` /
  `headline_source_label` so the chart and table can lead with the
  full-pipeline reduction (e.g. "36 MB .pptx -> 4.97 MB .pdf, 86.3%")
  rather than the PDF-only reduction.
- `benchmarks/make_charts.py` rewritten: horizontal headline reduction
  chart with average marker; original-vs-email-copy chart now uses the
  headline source size so the office-doc reductions read correctly. Same
  RGBY palette on a GitHub-style dark background.
- README real-world section trimmed to a 5-column table (Sample, Original,
  Email PDF, Reduction, PSNR) so the right edge no longer overflows the
  GitHub render width, and reordered so the four biggest wins lead.

### Added

- Realistic demonstration brochures (real-estate listing, travel lookbook,
  restaurant menu) built from curated synthetic stock images in
  `benchmarks/demo_assets/`, via `benchmarks/make_demo_brochures.py` and
  `benchmarks/make_demo_gallery.py`. The README gallery now shows these
  photo-heavy 10–14 MB exports shrunk ~80% to email-safe copies (PSNR 43–45 dB,
  render QA passed), with 100% detail crops proving no visible quality loss.
- Real-world sample harness: `benchmarks/convert_samples.py` converts office
  documents (PPTX/XLSX) to PDF via LibreOffice; `benchmarks/run_samples.py`
  optimizes a curated set of large real-world samples (139 MB photo brochure,
  71 MB lossless image PDF, 9 MB marketing deck, 4.6 MB screenshot-heavy deck,
  2.4 MB spreadsheet export) and writes `benchmarks/results/samples.json` with
  size, reduction, PSNR, RMS, and runtime per sample.
- `benchmarks/make_gallery.py` rewritten to render before / after / amplified-diff
  PNGs for every sample (also keeps a synthetic-fixture fallback).
- `benchmarks/make_charts.py` produces RGBY-on-dark filesize-reduction charts
  (`docs/charts/size_reduction.png`, `docs/charts/before_after.png`).
- `benchmarks/run_comparisons.py` and `docs/comparisons.md` provide an honest
  side-by-side against Ghostscript (`/screen`, `/ebook`, `/printer`) and a
  pikepdf-only lossless rewrite, with exact reproduction commands.
- `benchmarks/corpus/` documents the real-world benchmark corpus (`README.md`,
  `corpus.yaml`, `public/`, local-only `private/`).
- `benchmarks/run_benchmarks.py` now also emits `latest.csv` alongside the
  existing JSON and Markdown outputs.
- Field validation infrastructure: `docs/field-validation.md`,
  `.github/ISSUE_TEMPLATE/fixture-submission.yml`, and a draft Discussions
  pinned post (`docs/discussions-pinned-post.md`).
- `docs/roadmap-validation-sprint.md` for tracking the validation sprint.

### Changed

- README now leads with a "Real-world results" section (chart + table) drawn
  from `benchmarks/results/samples.json`, a Gallery section pointing at the
  new before/after renders, and a "How it compares" section summarising
  `docs/comparisons.md`.
- README phrasing: "private payload removals" → "creator metadata cleanup".
- Benchmark manifest and README table drop the `encrypted_pdf` row (covered
  by integration tests, not informative as a published benchmark row).
- CI matrix now also runs on `macos-latest` and `windows-latest` (in addition
  to the existing Ubuntu + Python 3.9–3.13 grid).

## [1.0.0] - 2026-06-20

### Changed

- First stable release. Marked the package `Production/Stable` and committed to
  semantic versioning for the CLI flags and JSON output contract going forward.
- Pinned all GitHub Actions to commit SHAs and moved to Node 24 action runtimes.

## [0.1.0] - 2026-06-20

### Added

- Installable Python package metadata and console scripts.
- `python -m pdf_email_optimizer` support.
- Shorthand CLI flags for targets, ranges, and profiles.
- Audit-only mode.
- Markdown report output and JSON output schema.
- Optional `pikepdf`/`qpdf` lossless structural backend, enabled automatically
  when installed and accepted only when it yields a smaller, pixel-identical
  result. Toggle with `--pikepdf`/`--no-pikepdf`; install via
  `pip install "pdf-email-optimizer[pikepdf]"`.
- `benchmarks/make_fixtures.py` generates 12 redistributable, synthetic (CC0)
  benchmark/test fixtures, including Illustrator- and InDesign-style exports.
- `benchmarks/make_gallery.py` renders before/after side-by-side images, plus a
  README gallery and a populated benchmark table with real size-reduction and
  PSNR/RMS numbers.
- Integration test suite (`tests/test_integration.py`, `integration` marker)
  covering design-tool exports, photo brochures, screenshots, transparency,
  forms/annotations, scans, and encrypted inputs.
- `fixtures` and `pikepdf` optional dependency groups.
- Benchmark harness, CI workflow, trusted-publishing workflow, documentation,
  and governance files.

### Notes

- Benchmark harness records an honest original-vs-output render comparison
  (PSNR/RMS) for every successful case and a row for failed cases.
- Image recompression is gated on the smallest lossless candidate, so a
  successful pikepdf pass can skip lossy work entirely.

[Unreleased]: https://github.com/petehottelet/pdf-email-optimizer/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/petehottelet/pdf-email-optimizer/compare/v0.1.0...v1.0.0
[0.1.0]: https://github.com/petehottelet/pdf-email-optimizer/releases/tag/v0.1.0

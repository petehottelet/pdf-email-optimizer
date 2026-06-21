# 9.5 validation sprint roadmap

Tracking issue body. Drop into a single GitHub issue titled "9.5: validation sprint - real-world corpus, gallery, comparisons".

## Goal

Get from "claim" to "demonstrated" on each of: real-world result coverage, side-by-side competitor comparisons, community validation, multi-OS CI.

## Workstreams

- [x] Convert provided sample documents (PPTX/XLSX) to PDF via LibreOffice (`benchmarks/convert_samples.py`).
- [x] Optimize all real-world samples and capture size, reduction, PSNR, RMS, runtime (`benchmarks/run_samples.py` + `benchmarks/results/samples.json`).
- [x] Build a regenerable corpus structure under `benchmarks/corpus/` (`README.md`, `corpus.yaml`, `public/`, `private/`).
- [x] Rework `benchmarks/make_gallery.py` to render before / after / diff PNGs for each sample into `docs/gallery/`.
- [x] Add `benchmarks/make_charts.py` and produce RGBY-on-dark size-reduction charts under `docs/charts/`.
- [x] Add `benchmarks/run_comparisons.py` and write `docs/comparisons.md` with real Ghostscript and pikepdf numbers + exact commands.
- [x] Extend `benchmarks/run_benchmarks.py` to emit `latest.csv` alongside the existing JSON / Markdown.
- [x] Update `README.md` with Real-world results, Gallery, and How it compares sections; rephrase wording; drop the `encrypted_pdf` row.
- [x] Expand the CI matrix to include `macos-latest` and `windows-latest` (substantiates the multi-OS claim).
- [x] Add a `fixture-submission` issue template and `docs/field-validation.md` for external user reports.
- [x] Draft `docs/discussions-pinned-post.md` for the Discussions setup.
- [ ] Enable GitHub Discussions on the repo and pin the welcome post.
- [ ] Open / close this issue once everything above is committed.

## Follow-ups for after the sprint

- [ ] Collect at least 5 community-submitted real PDFs via the fixture template, anonymize, and add to `docs/field-validation.md`.
- [ ] Run `benchmarks/run_comparisons.py` on a screenshot-heavy deck and a design-export so the comparisons doc has multiple anchors.
- [ ] Wire a nightly CI job that re-renders the gallery + charts from the in-repo fixtures so the synthetic side never drifts.

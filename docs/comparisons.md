# How it compares

`pdf-email-optimizer` is one of several tools you can point at an oversized PDF. This page is the honest side-by-side: same input, four profiles of the optimizer (`--quality` / `--balanced` / `--aggressive` at the shared 7 MB target, plus `--compress` at a tighter 1 MB target to show the "force this small" path), the opt-in `--bilevel` strategy (included to show what happens when it's applied to the wrong content), three Ghostscript presets, and a pikepdf-only lossless rewrite. All numbers are produced by [`benchmarks/run_comparisons.py`](../benchmarks/run_comparisons.py); the exact commands are listed below so anyone can reproduce them.

Methodology:

- All tools are pointed at the same source PDF.
- Output size and percent reduction are file-system measurements.
- "Worst PSNR" and "worst RMS" come from page-by-page rendering of original vs. output via [`pdf-email-render-compare`](../scripts/compare_pdf_render.py). Higher PSNR / lower RMS = closer to the original. `inf` PSNR + `0.0` RMS means pixel-identical rendering.
- "Met target" applies only to the optimizer; Ghostscript's `/PDFSETTINGS` are not size targets.

## Sample: large lossless PDF (70 MB), target 7 MB

Source: a 69.65 MB PDF saved with lossless image encoding (huge image headroom, vector text). Target: 7 MB email-safe size.

Results from [`benchmarks/results/comparisons.json`](../benchmarks/results/comparisons.json):

| Tool | Output | Reduction | Worst PSNR | Worst RMS | Notes |
|---|---:|---:|---:|---:|---|
| pdf-email-optimizer (`--quality`) | 3.48 MB | 95.0% | 55.8 dB | 0.42 | Visually lossless, hits target |
| pdf-email-optimizer (`--balanced`) | 2.93 MB | 95.8% | 54.6 dB | 0.47 | Visually lossless, hits target |
| pdf-email-optimizer (`--aggressive`) | 2.71 MB | 96.1% | 54.0 dB | 0.51 | Visually lossless, hits target |
| pdf-email-optimizer (`--compress --target-mb 1`) | 0.81 MB | 98.8% | 44.6 dB | 1.55 | Lossy; prioritizes filesize over fidelity. Stays RGB. |
| pdf-email-optimizer (`--bilevel 100`) | 0.02 MB | 100.0% | 11.0 dB | 71.6 | Lossy; prioritizes filesize over fidelity. For typeset / line-art scans. |
| Ghostscript `/printer` | 1.29 MB | 98.2% | 34.5 dB | 4.82 | Visible degradation, no quality floor |
| Ghostscript `/ebook` | 0.29 MB | 99.6% | 31.6 dB | 6.69 | Severely degraded |
| Ghostscript `/screen` | 0.12 MB | 99.8% | 27.2 dB | 11.2 | Severely degraded |
| pikepdf-only (lossless) | 53.90 MB | 22.6% | ∞ | 0.0 | Pixel-identical, but doesn't hit target |

Reproduce with:

```bash
python benchmarks/run_comparisons.py \
  --source "00_project_files/Converted PDFs/sample_lossless_huge.pdf" \
  --target-mb 7 \
  --output benchmarks/results/comparisons.json
```

### What this shows

`pdf-email-optimizer` and Ghostscript are not the same shape of tool.

- All three "visually lossless" optimizer profiles **hit the email target** while staying above PSNR 54 dB - visually lossless rendering at scale. The widely-cited "visually indistinguishable" threshold is about 38-40 dB.
- `--compress` is the "force a filesize" profile. At `--target-mb 1` it lands at **0.81 MB / PSNR 44.6 dB** — visibly more compressed than the lossless profiles but still RGB, still recognisably the same page. Compare it to the Ghostscript rows just below: Ghostscript `/printer` is 1.29 MB at PSNR 34.5 dB (bigger file, worse fidelity); Ghostscript `/ebook` is 0.29 MB at PSNR 31.6 dB (smaller but a measurable step down in quality). `--compress` honours the target you set and gives back PSNR proportional to it.
- Every Ghostscript preset goes **smaller than asked**, but trades real visual fidelity. `/screen` ends up at PSNR 27 dB, which is well into "people will notice."
- `--bilevel 100` produces a **21 KB** file — the smallest output in the table — at PSNR 11 dB. The photo content has been quantized to 1-bit black/white squares; the file is technically valid but the photos are gone. Bilevel is the right answer for typeset / line-art archival scans (it took the 88.68 MB 1976 NASA scan in [Real-world results](../README.md#real-world-results) down to 5.27 MB while keeping text legible) and the wrong answer for everything else.
- The pikepdf-only run is the strictly safe ceiling (no pixel changes) but doesn't hit any kind of email target on a PDF this big.

In other words: if you want the smallest possible file that still looks visually identical to the original, the optimizer's `--quality` / `--balanced` / `--aggressive` profiles win. If you need to force a much tighter size on photo content and accept visible compression, `--compress` is the option to reach for — it beats the equivalent Ghostscript preset at the same approximate output size. If your source is a typeset / line-art scan, the opt-in `--bilevel` strategy outperforms every other tool here.

## Exact Ghostscript commands

Each Ghostscript row above corresponds to:

```bash
# /screen (most aggressive, ~72 dpi images)
gs -sDEVICE=pdfwrite \
   -dPDFSETTINGS=/screen \
   -dCompatibilityLevel=1.6 \
   -dNOPAUSE -dBATCH -dQUIET -dSAFER \
   -sOutputFile=output.pdf \
   input.pdf

# /ebook (~150 dpi images)
gs -sDEVICE=pdfwrite \
   -dPDFSETTINGS=/ebook \
   -dCompatibilityLevel=1.6 \
   -dNOPAUSE -dBATCH -dQUIET -dSAFER \
   -sOutputFile=output.pdf \
   input.pdf

# /printer (~300 dpi images)
gs -sDEVICE=pdfwrite \
   -dPDFSETTINGS=/printer \
   -dCompatibilityLevel=1.6 \
   -dNOPAUSE -dBATCH -dQUIET -dSAFER \
   -sOutputFile=output.pdf \
   input.pdf
```

The `--bilevel` row corresponds to:

```bash
pip install "pdf-email-optimizer[bilevel]"
pdf-email-optimizer input.pdf output.pdf --bilevel 100
```

(See [README — Archival opt-in: `--bilevel`](../README.md#archival-opt-in---bilevel) for the threshold/DPI flags.)

The pikepdf row corresponds to the lossless structural rewrite `pdf-email-optimizer` calls internally:

```python
import pikepdf

with pikepdf.open("input.pdf") as pdf:
    pdf.save(
        "output.pdf",
        object_stream_mode=pikepdf.ObjectStreamMode.generate,
        compress_streams=True,
        recompress_flate=True,
    )
```

## How to read this

- **Hard targets vs. preset compression.** `pdf-email-optimizer` ships an email-shaped target (`--target-mb`, `--range`, `--preferred-mb`) and a quality floor. Ghostscript's `/PDFSETTINGS` are recompression presets; they will sometimes go smaller, sometimes larger, and there is no "fail" if quality drops.
- **Quality-floor behavior.** `--quality` runs a render QA pass and rejects candidates that fall below the PSNR/RMS floor for the profile. The other tools in this table do not.
- **Lossless cleanup is free.** pikepdf-only is the strictly safe option: it never touches pixels. It rarely hits an aggressive size target on its own, but it is always accepted by `pdf-email-optimizer` when it is smaller than the cleanup baseline.
- **Aggressive is meant to be aggressive.** If you need raw smallness, `--aggressive` (and the optional Ghostscript fallback it can call) is the closest analog to Ghostscript `/screen`. Use it only when visible quality loss is acceptable.

If you have a sample where another tool wins cleanly, please file it via the [fixture submission template](../.github/ISSUE_TEMPLATE/fixture-submission.yml) so the comparison stays current.

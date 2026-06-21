# Sample document provenance

These input PDFs are real-world documents used to benchmark `pdf-email-optimizer`. Each one is included only as a third-party input for compression testing; this project does not republish them. Renders that appear in `docs/gallery/` are derived works limited to small thumbnails for size-reduction comparison, and the optimized derivatives in `00_project_files/Optimized PDFs/` are reproductions for benchmarking only.

## NASA Technical Reports Server (NTRS) documents

All three NASA-prefixed PDFs were obtained from the [NASA Technical Reports Server (NTRS)](https://ntrs.nasa.gov/), the public NASA STI repository. NASA-authored Scientific and Technical Information is a U.S. government work and is not protected by copyright in the United States; NASA requests attribution back to NTRS when its content is reused. See [NASA's Disclaimers, Copyright Notice, and Terms of Use](https://www.nasa.gov/nasa-web-privacy-policy-and-important-notices/) for full terms.

| File | NTRS accession # | Document URL |
| --- | --- | --- |
| `19760021505.pdf` | 19760021505 | https://ntrs.nasa.gov/citations/19760021505 |
| `19760026509.pdf` | 19760026509 | https://ntrs.nasa.gov/citations/19760026509 |
| `20170009128.pdf` | 20170009128 | https://ntrs.nasa.gov/citations/20170009128 |

If you are the NASA NTRS team and would prefer a different attribution string or want the renders removed, please open an issue and the project will adjust promptly.

## Other documents

| File | Source | Notes |
| --- | --- | --- |
| `TUM_2024.pdf` | Technische Universität München (publicly distributed PDF) | Used as a representative recent academic paper. If the rights holder would prefer the file or its renders not appear in this benchmark suite, please open an issue. |

## How these are used

- The original PDFs in this directory are inputs to `benchmarks/run_samples.py` and are never modified.
- Optimized derivatives in `00_project_files/Optimized PDFs/` are produced solely to measure compression and visual fidelity.
- Thumbnails in `docs/gallery/` are low-resolution renders sized for README comparison and are not substitutes for the originals.

If you want to re-run the benchmark on your own copies, see [`benchmarking.md`](benchmarking.md).

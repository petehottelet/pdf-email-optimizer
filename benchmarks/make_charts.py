#!/usr/bin/env python3
"""Render the RGBY-on-dark real-world results chart for the README.

Reads ``benchmarks/results/samples.json`` (produced by
``benchmarks/run_samples.py``) and writes a single vertical bar chart at
``docs/charts/before_after.png`` showing **Original** (red) vs **Email PDF**
(green) for every successful sample, on a LINEAR megabyte scale so the bars
honestly represent the on-disk file sizes.

Colour palette is RGBY on a GitHub-style dark background:

- R `#ef4444`
- G `#22c55e`
- B `#3b82f6`
- Y `#eab308`
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = PROJECT_ROOT / "benchmarks" / "results" / "samples.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "charts"

# RGBY palette + supporting greys for dark UI.
PALETTE = {
    "red": "#ef4444",
    "green": "#22c55e",
    "blue": "#3b82f6",
    "yellow": "#eab308",
}
BG = "#0d1117"
FG = "#e6edf3"
FG_MUTED = "#8b949e"
GRID = "#30363d"

# Canonical README ordering: descending by original size for visual impact.
DEFAULT_ORDER = (
    "travel_contact_sheet",
    "lossless_huge",
    "financial_proposal",
    "bank_report",
)

SHORT_LABELS = {
    "travel_contact_sheet": "Photo brochure",
    "lossless_huge": "Lossless image PDF",
    "financial_proposal": "Financial proposal",
    "bank_report": "Bank report",
}


def _apply_dark_theme(fig: plt.Figure, ax: plt.Axes) -> None:
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.tick_params(colors=FG)
    ax.yaxis.label.set_color(FG)
    ax.xaxis.label.set_color(FG)
    ax.title.set_color(FG)
    ax.grid(True, axis="y", color=GRID, linestyle="-", linewidth=0.5, alpha=0.7)
    ax.set_axisbelow(True)


def _headline_source(sample: dict[str, Any]) -> tuple[float, str]:
    """Return ``(MB, format label)`` for the headline original column.

    If the sample carries an office source (.pptx/.xlsx/.docx), the office
    file's size and extension are used so the chart says ".pptx 36 MB" rather
    than the intermediate converted-PDF size.
    """

    if sample.get("source_office_mb") is not None:
        suffix = (sample.get("headline_source_label") or "").lstrip(".") or "office"
        return float(sample["source_office_mb"]), suffix
    return float(sample.get("input_mb", 0.0)), "pdf"


def _headline_reduction(sample: dict[str, Any]) -> float:
    if "headline_reduction_percent" in sample:
        return float(sample["headline_reduction_percent"])
    return float(sample.get("reduction_percent", 0.0))


def _label_with_size(sample: dict[str, Any]) -> str:
    size_mb, suffix = _headline_source(sample)
    base = SHORT_LABELS.get(sample["sample_id"], sample["sample_id"])
    return f"{base}\n({size_mb:.0f} MB .{suffix})"


def _ordered_ok_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {sample.get("sample_id"): sample for sample in samples if sample.get("status") == "ok"}
    ordered = [by_id[sid] for sid in DEFAULT_ORDER if sid in by_id]
    extras = [sample for sid, sample in by_id.items() if sid not in DEFAULT_ORDER]
    return ordered + extras


def chart_before_after(samples: list[dict[str, Any]], output_path: Path) -> None:
    """Single vertical bar chart on a LINEAR scale.

    Each sample produces a pair of bars: Original (red) and Email PDF (green).
    Linear MB axis so a 6 MB output bar honestly looks tiny next to a 139 MB
    input - that visual asymmetry is the point.
    """

    ok = _ordered_ok_samples(samples)
    if not ok:
        print("No successful samples; skipping chart.")
        return

    labels = [_label_with_size(sample) for sample in ok]
    originals = [_headline_source(sample)[0] for sample in ok]
    outputs = [float(sample["output_mb"]) for sample in ok]
    reductions = [_headline_reduction(sample) for sample in ok]

    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=160)
    _apply_dark_theme(fig, ax)

    x = np.arange(len(labels))
    width = 0.4
    gap = 0.04
    bars_in = ax.bar(
        x - (width / 2 + gap / 2),
        originals,
        width,
        label="Original",
        color=PALETTE["blue"],
        edgecolor=BG,
        linewidth=1.5,
        zorder=3,
    )
    bars_out = ax.bar(
        x + (width / 2 + gap / 2),
        outputs,
        width,
        label="Email PDF",
        color=PALETTE["green"],
        edgecolor=BG,
        linewidth=1.5,
        zorder=3,
    )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, color=FG, fontsize=11)
    ax.set_ylabel("Size (MB)", color=FG, fontsize=11)
    ax.set_title(
        "Real-world filesize reduction: original document vs email-safe PDF",
        color=FG,
        pad=18,
        fontsize=14,
        fontweight="bold",
    )

    headroom = max(originals) * 1.18
    ax.set_ylim(0, headroom)

    # Value labels on top of each bar.
    for bar, value in zip(bars_in, originals):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + headroom * 0.012,
            f"{value:.1f} MB",
            ha="center",
            va="bottom",
            color=PALETTE["blue"],
            fontsize=11,
            fontweight="bold",
        )
    for bar, value, reduction in zip(bars_out, outputs, reductions):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + headroom * 0.012,
            f"{value:.2f} MB",
            ha="center",
            va="bottom",
            color=PALETTE["green"],
            fontsize=11,
            fontweight="bold",
        )
        # The headline win line just below: -95.3% (etc.). Offset further
        # so it doesn't collide with the MB label above when the bar is
        # microscopic next to a towering original.
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + headroom * 0.07,
            f"\u2212{reduction:.1f}%",
            ha="center",
            va="bottom",
            color=PALETTE["green"],
            fontsize=12,
            fontweight="bold",
        )

    legend = ax.legend(
        loc="upper right",
        facecolor=BG,
        edgecolor=GRID,
        labelcolor=FG,
        framealpha=0.95,
        fontsize=11,
    )
    for text in legend.get_texts():
        text.set_color(FG)

    # Subtitle / context line below the bars.
    avg = sum(reductions) / len(reductions) if reductions else 0.0
    ax.text(
        0.5,
        -0.16,
        f"Average reduction across these four real documents: {avg:.1f}%   \u2022   PSNR\u202F\u2265\u202F40\u202FdB \"visually indistinguishable\" except where noted",
        transform=ax.transAxes,
        ha="center",
        va="top",
        color=FG_MUTED,
        fontsize=10,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", default=str(DEFAULT_RESULTS))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    samples_path = Path(args.samples).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if not samples_path.exists():
        print(f"Samples results not found at {samples_path}; run benchmarks/run_samples.py first.")
        return 1

    samples = json.loads(samples_path.read_text(encoding="utf-8"))
    chart_before_after(samples, output_dir / "before_after.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

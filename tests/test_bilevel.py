"""Tests for the --bilevel / CCITT G4 strategy."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import write_image_pdf

from pdf_email_optimizer import bilevel
from pdf_email_optimizer.optimizer import build_parser, optimize


def parse_args(*args: str):
    return build_parser().parse_args(list(args))


def test_bilevel_default_value_uses_module_default(tmp_path: Path) -> None:
    args = parse_args(str(tmp_path / "in.pdf"), str(tmp_path / "out.pdf"), "--bilevel")
    assert args.bilevel == bilevel.DEFAULT_DPI
    assert args.bilevel_threshold == bilevel.DEFAULT_THRESHOLD


def test_bilevel_off_by_default(tmp_path: Path) -> None:
    args = parse_args(str(tmp_path / "in.pdf"), str(tmp_path / "out.pdf"))
    assert args.bilevel is None


def test_validate_rejects_out_of_range_dpi() -> None:
    with pytest.raises(ValueError):
        bilevel._validate(dpi=10, threshold=200)
    with pytest.raises(ValueError):
        bilevel._validate(dpi=400, threshold=200)


def test_validate_rejects_out_of_range_threshold() -> None:
    with pytest.raises(ValueError):
        bilevel._validate(dpi=100, threshold=0)
    with pytest.raises(ValueError):
        bilevel._validate(dpi=100, threshold=300)


@pytest.mark.skipif(
    bilevel.img2pdf is None or bilevel.pdfium is None,
    reason="bilevel deps not installed",
)
def test_optimize_bilevel_end_to_end(tmp_path: Path) -> None:
    src = write_image_pdf(tmp_path / "src.pdf")
    dst = tmp_path / "out.pdf"
    result = bilevel.optimize_bilevel(src, dst, dpi=100, threshold=200)

    assert dst.exists()
    assert dst.stat().st_size > 0
    assert result["strategy"] == "bilevel-g4"
    assert result["pages"] == 1
    assert result["bilevel_dpi"] == 100
    assert result["bilevel_threshold"] == 200
    assert any("Bilevel strategy" in w for w in result["warnings"])


@pytest.mark.skipif(
    bilevel.img2pdf is None or bilevel.pdfium is None,
    reason="bilevel deps not installed",
)
def test_cli_bilevel_short_circuits_optimize(tmp_path: Path) -> None:
    src = write_image_pdf(tmp_path / "src.pdf")
    out = tmp_path / "out.pdf"
    args = parse_args(str(src), str(out), "--bilevel", "100", "--target-mb", "5")
    summary = optimize(args)

    assert summary["strategy"] == "bilevel-g4"
    assert summary["bilevel_dpi"] == 100
    assert summary["bilevel_threshold"] == bilevel.DEFAULT_THRESHOLD
    assert summary["pages"] == 1
    assert summary["output_bytes"] > 0
    # image-recompress path was skipped, so no image_stats from that pipeline
    assert summary["image_stats"] is None
    # Render QA defaults off under the balanced profile, even when --bilevel is used
    assert summary["render_qa"] is None
    assert any("Bilevel strategy" in w for w in summary["warnings"])


def test_missing_dependencies_raises_friendly_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bilevel, "img2pdf", None)
    monkeypatch.setattr(bilevel, "pdfium", None)
    with pytest.raises(RuntimeError) as excinfo:
        bilevel.optimize_bilevel(tmp_path / "any.pdf", tmp_path / "out.pdf")
    msg = str(excinfo.value)
    assert "img2pdf" in msg
    assert "pypdfium2" in msg
    assert "pdf-email-optimizer[bilevel]" in msg

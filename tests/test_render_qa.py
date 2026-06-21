from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from conftest import write_blank_pdf
from PIL import Image
from pypdf import PdfWriter

from pdf_email_optimizer import render_qa
from pdf_email_optimizer.render_qa import compare_pdfs


def test_render_compare_identical_pdf(tmp_path: Path) -> None:
    pytest.importorskip("pypdfium2")
    source = write_blank_pdf(tmp_path / "input.pdf")
    output_dir = tmp_path / "renders"
    summary = compare_pdfs(source, source, scale=0.5, max_pages=1, output_dir=output_dir)
    assert summary["identical_render"] is True
    assert summary["pages"][0]["rms_diff"] == 0
    assert (output_dir / "original_page_001.png").exists()
    assert (output_dir / "optimized_page_001.png").exists()
    assert (output_dir / "diff_page_001.png").exists()


def test_render_compare_changed_pdf(tmp_path: Path) -> None:
    pytest.importorskip("pypdfium2")
    original = write_blank_pdf(tmp_path / "original.pdf")
    changed = write_blank_pdf(tmp_path / "changed.pdf", pages=2)
    summary = compare_pdfs(original, changed, scale=0.5, max_pages=2, output_dir=None)
    assert summary["identical_render"] is False


def test_render_compare_size_changed_pdf(tmp_path: Path) -> None:
    pytest.importorskip("pypdfium2")
    original = write_blank_pdf(tmp_path / "original.pdf")
    changed = tmp_path / "changed.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=400, height=400)
    with changed.open("wb") as handle:
        writer.write(handle)
    summary = compare_pdfs(original, changed, scale=0.5, max_pages=1, output_dir=None)
    assert summary["pages"][0]["same_size"] is False


def test_changed_percent_handles_empty_images() -> None:
    image = Image.new("RGB", (0, 0))
    assert render_qa.changed_percent(image) == 0.0


def test_render_qa_print_summary_modes(capsys: pytest.CaptureFixture[str]) -> None:
    summary = {
        "original_pages": 1,
        "optimized_pages": 1,
        "compared_pages": 1,
        "identical_render": True,
        "pages": [{"page": 1, "same_size": True, "rms_diff": 0.0, "changed_percent": 0.0, "diff_bbox": None}],
    }
    render_qa.print_summary(summary, json_output=False)
    assert "Identical render: yes" in capsys.readouterr().out

    render_qa.print_summary(summary, json_output=True)
    assert json.loads(capsys.readouterr().out)["identical_render"] is True


def test_render_qa_print_summary_size_changed(capsys: pytest.CaptureFixture[str]) -> None:
    summary = {
        "original_pages": 1,
        "optimized_pages": 1,
        "compared_pages": 1,
        "identical_render": False,
        "pages": [
            {
                "page": 1,
                "same_size": False,
                "original_size": (100, 100),
                "optimized_size": (200, 200),
            }
        ],
    }
    render_qa.print_summary(summary, json_output=False)
    assert "size changed" in capsys.readouterr().out


def test_render_qa_main_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pytest.importorskip("pypdfium2")
    source = write_blank_pdf(tmp_path / "input.pdf")
    monkeypatch.setattr(
        sys,
        "argv",
        ["pdf-email-render-compare", str(source), str(source), "--scale", "0.5", "--max-pages", "1"],
    )
    assert render_qa.main() == 0
    assert "Identical render: yes" in capsys.readouterr().out


def test_render_qa_main_failure(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["pdf-email-render-compare", "missing.pdf", "missing.pdf"])
    assert render_qa.main() == 1
    assert "Error:" in capsys.readouterr().err


def test_render_page_requires_pdfium(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = write_blank_pdf(tmp_path / "input.pdf")
    monkeypatch.setattr(render_qa, "pdfium", None)
    with pytest.raises(RuntimeError, match="pypdfium2 is required"):
        render_qa.render_page(source, 0, 1.0)

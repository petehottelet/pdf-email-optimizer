"""Tests for the Office-document -> PDF conversion layer.

The conversion itself depends on LibreOffice being installed on the host,
so the end-to-end test is skipped when ``soffice`` is unavailable. The
non-end-to-end tests (suffix detection, missing-soffice error path,
input-resolution branching) run everywhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import write_blank_pdf

from pdf_email_optimizer import office_convert
from pdf_email_optimizer.optimizer import build_parser, optimize, resolve_input_source


def test_office_suffix_detection(tmp_path: Path) -> None:
    docx = tmp_path / "deck.docx"
    docx.write_bytes(b"not a real docx, suffix check only")
    pdf = tmp_path / "deck.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    assert office_convert.is_office_document(docx)
    assert not office_convert.is_office_document(pdf)


@pytest.mark.parametrize("suffix", [".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".odt", ".odp", ".ods", ".rtf"])
def test_all_advertised_suffixes_route_through_convert(suffix: str, tmp_path: Path) -> None:
    candidate = tmp_path / f"sample{suffix}"
    candidate.write_bytes(b"placeholder")
    assert office_convert.is_office_document(candidate)


def test_convert_raises_when_soffice_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(office_convert, "find_soffice", lambda: None)
    src = tmp_path / "deck.docx"
    src.write_bytes(b"placeholder")

    with pytest.raises(office_convert.OfficeConversionError) as excinfo:
        office_convert.convert_to_pdf(src)

    msg = str(excinfo.value)
    assert "LibreOffice" in msg
    assert "libreoffice.org" in msg


def test_convert_rejects_unsupported_suffix(tmp_path: Path) -> None:
    src = tmp_path / "image.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(office_convert.OfficeConversionError):
        office_convert.convert_to_pdf(src)


def test_resolve_input_source_passes_through_pdf(tmp_path: Path) -> None:
    pdf = write_blank_pdf(tmp_path / "in.pdf")
    source, working, metadata, temp_dir = resolve_input_source(str(pdf))

    assert source == pdf.resolve()
    assert working == pdf.resolve()
    assert metadata is None
    assert temp_dir is None


def test_resolve_input_source_rejects_unknown_format(tmp_path: Path) -> None:
    img = tmp_path / "diagram.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ValueError) as excinfo:
        resolve_input_source(str(img))
    assert ".png" in str(excinfo.value) or "Unsupported" in str(excinfo.value)


def test_resolve_input_source_surfaces_missing_soffice_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(office_convert, "find_soffice", lambda: None)
    src = tmp_path / "deck.docx"
    src.write_bytes(b"placeholder")
    with pytest.raises(RuntimeError) as excinfo:
        resolve_input_source(str(src))
    assert "LibreOffice" in str(excinfo.value)


@pytest.mark.skipif(office_convert.find_soffice() is None, reason="LibreOffice not installed on host")
def test_end_to_end_office_input(tmp_path: Path) -> None:
    """Round-trip a real Office file through the optimizer.

    Uses an ``.rtf`` because Python's stdlib can write one without any
    additional dependencies, and LibreOffice converts RTF -> PDF just like
    DOCX -> PDF.
    """

    rtf = tmp_path / "report.rtf"
    rtf.write_text(
        "{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Times New Roman;}}\\f0\\fs28 "
        "PDF Email Optimizer end-to-end smoke test.\\par "
        "Second line of body copy to give the page some content.}",
        encoding="ascii",
    )
    output = tmp_path / "report_email.pdf"
    args = build_parser().parse_args([str(rtf), str(output), "--target-mb", "5", "--skip-render-qa"])
    summary = optimize(args)

    assert output.exists()
    assert summary["output"] == str(output)
    assert summary["source"] == str(rtf.resolve())
    assert summary["source_format"] == ".rtf"
    assert summary["converted_via"] == "libreoffice"
    assert summary["source_bytes"] > 0
    assert summary["intermediate_pdf_bytes"] > 0
    assert summary["output_bytes"] > 0

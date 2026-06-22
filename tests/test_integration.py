"""End-to-end integration tests against realistic, generated PDF fixtures.

These cover the design-tool exports and tricky PDF shapes the optimizer is
meant to handle: Illustrator/InDesign exports, photo brochures, screenshot
reports, transparent graphics, form/annotation PDFs, and scanned pages. Every
fixture is synthesized at runtime (CC0) so the suite stays hermetic and never
depends on committed binaries.

Run only these with ``pytest -m integration``; skip them with
``pytest -m 'not integration'``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

reportlab = pytest.importorskip("reportlab", reason="reportlab is required to generate integration fixtures")

import make_fixtures  # noqa: E402  (added to pythonpath via pyproject)
from pypdf.errors import PdfReadError  # noqa: E402

from pdf_email_optimizer import audit, optimize  # noqa: E402
from pdf_email_optimizer.cli import build_parser  # noqa: E402
from pdf_email_optimizer.config import OptimizeConfig  # noqa: E402

pytestmark = pytest.mark.integration


def _args(*argv: str) -> OptimizeConfig:
    return OptimizeConfig.from_cli_args(build_parser().parse_args(list(argv)))


@pytest.fixture(scope="session")
def fixtures(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    out = tmp_path_factory.mktemp("integration-fixtures")
    paths: dict[str, Path] = {}
    for name, builder in make_fixtures.FIXTURES.items():
        paths[name] = builder(out / f"{name}.pdf")
    return paths


def _optimize(source: Path, out_dir: Path, *flags: str):
    output = out_dir / f"{source.stem}_email.pdf"
    summary = optimize(_args(str(source), str(output), "--force", "--skip-render-qa", *flags))
    return summary, output


def test_illustrator_export_preserves_vectors(fixtures: dict[str, Path], tmp_path: Path) -> None:
    summary, output = _optimize(fixtures["illustrator_export"], tmp_path, "--profile", "balanced")
    assert output.exists()
    # Pure vector art has no recompressible images.
    assert summary["image_stats"] is None or summary["image_stats"]["changed"] == 0
    assert summary["pages"] == 1
    assert summary["output_bytes"] <= summary["input_bytes"]


def test_indesign_export_hits_target(fixtures: dict[str, Path], tmp_path: Path) -> None:
    summary, output = _optimize(fixtures["indesign_export"], tmp_path, "--profile", "balanced", "--target-mb", "1.0")
    assert output.exists()
    assert summary["met_target"] is True
    assert summary["strategy"] == "image-recompress"
    assert summary["output_bytes"] < summary["input_bytes"]


def test_photo_brochure_quality_does_not_silently_degrade(fixtures: dict[str, Path], tmp_path: Path) -> None:
    summary, _ = _optimize(fixtures["photo_brochure"], tmp_path, "--quality", "--target-mb", "0.6")
    # Quality profile must either hit the target or warn, never ship blurry output silently.
    if not summary["met_target"]:
        assert any("Target not met" in warning for warning in summary["warnings"])


def test_screenshot_report_runs_and_preserves_pages(fixtures: dict[str, Path], tmp_path: Path) -> None:
    summary, output = _optimize(fixtures["screenshot_report"], tmp_path, "--quality", "--target-mb", "0.2")
    assert output.exists()
    assert summary["pages"] == 3


def test_transparency_skipped_without_flatten(fixtures: dict[str, Path], tmp_path: Path) -> None:
    summary, _ = _optimize(fixtures["mixed_transparency"], tmp_path, "--quality", "--target-mb", "1.0")
    assert any("transparen" in warning.lower() for warning in summary["warnings"])


def test_transparency_flattened_when_requested(fixtures: dict[str, Path], tmp_path: Path) -> None:
    summary, output = _optimize(
        fixtures["mixed_transparency"], tmp_path, "--balanced", "--target-mb", "0.8", "--flatten-alpha"
    )
    assert output.exists()
    assert summary["image_stats"] is not None
    assert summary["image_stats"]["changed"] >= 1


def test_forms_and_annotations_warn(fixtures: dict[str, Path], tmp_path: Path) -> None:
    audit_summary = audit(fixtures["forms_annotations"])
    assert audit_summary["forms"] is True
    assert audit_summary["annotations"] >= 1

    summary, output = _optimize(fixtures["forms_annotations"], tmp_path, "--quality")
    assert output.exists()
    assert any("Form fields" in warning for warning in summary["warnings"])
    assert any("Annotations" in warning for warning in summary["warnings"])


def test_scanned_pdf_recompresses(fixtures: dict[str, Path], tmp_path: Path) -> None:
    summary, output = _optimize(fixtures["scanned_pdf"], tmp_path, "--balanced", "--target-mb", "0.4")
    assert output.exists()
    assert summary["output_bytes"] < summary["input_bytes"]


def test_repeated_images_dedupe_shrinks_file(fixtures: dict[str, Path], tmp_path: Path) -> None:
    summary, _ = _optimize(fixtures["repeated_images"], tmp_path, "--balanced", "--target-mb", "0.5")
    assert summary["output_bytes"] < summary["input_bytes"]


def test_creator_metadata_is_stripped(fixtures: dict[str, Path], tmp_path: Path) -> None:
    summary, _ = _optimize(fixtures["creator_metadata"], tmp_path, "--quality")
    assert summary["private_removed"]


def test_encrypted_pdf_raises_clear_error(fixtures: dict[str, Path], tmp_path: Path) -> None:
    with pytest.raises(PdfReadError, match="Encrypted PDFs must be unlocked"):
        _optimize(fixtures["encrypted_pdf"], tmp_path)


def test_encrypted_audit_reports_unlock_guidance(fixtures: dict[str, Path]) -> None:
    audit_summary = audit(fixtures["encrypted_pdf"])
    assert audit_summary["encrypted"] is True
    assert any("Unlock" in warning for warning in audit_summary["warnings"])

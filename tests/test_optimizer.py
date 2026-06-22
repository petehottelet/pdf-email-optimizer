from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import PROJECT_ROOT, write_blank_pdf, write_image_pdf
from PIL import Image
from pypdf import PdfWriter
from pypdf.errors import PdfReadError

from pdf_email_optimizer import audit, ghostscript, images, optimize, pipeline, render_qa, reporting
from pdf_email_optimizer.cli import build_parser
from pdf_email_optimizer.config import OptimizeConfig

REQUIRED_JSON_FIELDS = {
    "input",
    "output",
    "profile",
    "input_bytes",
    "output_bytes",
    "input_mb",
    "output_mb",
    "target_mb",
    "target_min_mb",
    "target_label",
    "preferred_mb",
    "met_target",
    "within_target_range",
    "strategy",
    "pages",
    "private_removed",
    "image_stats",
    "render_qa",
    "quality_ok",
    "warnings",
}


def parse_args(*args: str):
    return build_parser().parse_args(list(args))


def cfg(*args: str) -> OptimizeConfig:
    """Build an OptimizeConfig the way the CLI does, from parsed args."""

    return OptimizeConfig.from_cli_args(parse_args(*args))


def test_quality_profile_defaults(tmp_path: Path) -> None:
    resolved = cfg(str(tmp_path / "in.pdf"), str(tmp_path / "out.pdf"), "--quality").resolved()
    assert resolved.profile == "quality"
    assert resolved.image_quality == 92
    assert resolved.render_qa is True
    assert resolved.ghostscript == "never"


def test_balanced_profile_defaults(tmp_path: Path) -> None:
    resolved = cfg(str(tmp_path / "in.pdf"), str(tmp_path / "out.pdf"), "--balanced").resolved()
    assert resolved.profile == "balanced"
    assert resolved.image_quality == 88
    assert resolved.render_qa is False


def test_aggressive_profile_defaults(tmp_path: Path) -> None:
    resolved = cfg(str(tmp_path / "in.pdf"), str(tmp_path / "out.pdf"), "--aggressive").resolved()
    assert resolved.profile == "aggressive"
    assert resolved.min_image_quality == 60
    assert resolved.ghostscript == "auto"


def test_compress_profile_defaults(tmp_path: Path) -> None:
    resolved = cfg(str(tmp_path / "in.pdf"), str(tmp_path / "out.pdf"), "--compress").resolved()
    assert resolved.profile == "compress"
    # Lower JPEG floor than aggressive (60), keeps RGB (no bilevel handoff).
    assert resolved.min_image_quality == 30
    assert resolved.min_long_edge == 800
    assert resolved.render_qa is False
    assert resolved.min_render_psnr is None


def test_resolved_does_not_mutate_raw_config(tmp_path: Path) -> None:
    raw = cfg(str(tmp_path / "in.pdf"), str(tmp_path / "out.pdf"), "--quality")
    assert raw.image_quality is None  # not yet resolved
    resolved = raw.resolved()
    assert resolved.image_quality == 92
    assert raw.image_quality is None  # raw stays untouched for explicitness checks


def test_profile_flags_are_mutually_exclusive(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        parse_args(str(tmp_path / "in.pdf"), str(tmp_path / "out.pdf"), "--quality", "--aggressive")


def test_compress_flag_is_mutually_exclusive_with_other_profiles(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        parse_args(str(tmp_path / "in.pdf"), str(tmp_path / "out.pdf"), "--compress", "--aggressive")


def test_json_output_has_required_fields(tmp_path: Path) -> None:
    source = write_blank_pdf(tmp_path / "input.pdf")
    output = tmp_path / "output.pdf"
    summary = optimize(cfg(str(source), str(output)))
    assert set(summary) >= REQUIRED_JSON_FIELDS
    assert summary["output"] == str(output.resolve())
    assert output.exists()


def test_json_summary_validates_schema(tmp_path: Path) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    source = write_blank_pdf(tmp_path / "input.pdf")
    summary = optimize(cfg(str(source), str(tmp_path / "output.pdf")))
    schema = json.loads((PROJECT_ROOT / "schema" / "output-summary.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(summary, schema)


def test_encrypted_pdf_returns_clear_error(tmp_path: Path) -> None:
    source = write_blank_pdf(tmp_path / "encrypted.pdf", encrypted=True)
    with pytest.raises(PdfReadError, match="Encrypted PDFs must be unlocked"):
        optimize(cfg(str(source), str(tmp_path / "out.pdf")))


def test_no_image_recompress_does_not_recompress_images(tmp_path: Path) -> None:
    source = write_image_pdf(tmp_path / "image.pdf")
    summary = optimize(cfg(str(source), str(tmp_path / "out.pdf"), "--target-mb", "0.001", "--no-image-recompress"))
    assert summary["strategy"] in {"structural-cleanup", "pikepdf-structural"}
    assert summary["image_stats"] is None


def test_recompress_images_tracks_changed_and_skipped_images() -> None:
    class FakeImageFile:
        def __init__(
            self,
            name: str,
            image: Image.Image | None,
            data: bytes,
            ref_id: int | None,
            *,
            fail: bool = False,
        ) -> None:
            self.name = name
            self.image = image
            self.data = data
            self.indirect_reference = None if ref_id is None else SimpleNamespace(idnum=ref_id, generation=0)
            self.fail = fail

        def replace(self, replacement: Image.Image, *, quality: int, optimize: bool) -> None:
            if self.fail:
                raise RuntimeError("replace failed")
            self.image = replacement
            self.data = b"compressed"

    normal = Image.new("RGB", (500, 500), "red")
    small = Image.new("RGB", (10, 10), "blue")
    bilevel = Image.new("1", (500, 500))
    alpha = Image.new("RGBA", (500, 500), (255, 0, 0, 128))
    writer = SimpleNamespace(
        pages=[
            SimpleNamespace(
                images=[
                    FakeImageFile("no-ref", normal, b"x" * 2000, None),
                    FakeImageFile("none", None, b"x" * 2000, 99),
                    FakeImageFile("small", small, b"x" * 2000, 2),
                    FakeImageFile("low-bytes", normal, b"x", 3),
                    FakeImageFile("bilevel", bilevel, b"x" * 2000, 4),
                    FakeImageFile("alpha", alpha, b"x" * 2000, 5),
                    FakeImageFile("normal", normal, b"x" * 2000, 1),
                    FakeImageFile("duplicate", normal, b"x" * 2000, 1),
                    FakeImageFile("fails", normal, b"x" * 2000, 6, fail=True),
                ]
            )
        ]
    )
    warnings: list[str] = []
    stats = images.recompress_images(
        writer,
        quality=80,
        long_edge=100,
        min_image_pixels=1000,
        min_image_bytes=100,
        flatten_alpha=False,
        warnings=warnings,
    )
    assert stats["attempted"] == 1
    assert stats["changed"] == 1
    assert stats["skipped"] == 7
    assert stats["skipped_small"] == 1
    assert stats["skipped_low_value"] == 1
    assert any("transparent image" in warning for warning in warnings)
    assert any("Could not recompress image" in warning for warning in warnings)


def test_recompress_images_can_flatten_alpha() -> None:
    class FakeImageFile:
        name = "alpha"
        image = Image.new("RGBA", (500, 500), (255, 0, 0, 128))
        data = b"x" * 2000
        indirect_reference = SimpleNamespace(idnum=1, generation=0)

        def replace(self, replacement: Image.Image, *, quality: int, optimize: bool) -> None:
            self.image = replacement
            self.data = b"compressed"

    image_file = FakeImageFile()
    writer = SimpleNamespace(pages=[SimpleNamespace(images=[image_file])])
    stats = images.recompress_images(
        writer,
        quality=80,
        long_edge=None,
        min_image_pixels=1000,
        min_image_bytes=100,
        flatten_alpha=True,
        warnings=[],
    )
    assert stats["attempted"] == 1
    assert image_file.image.mode == "RGB"


def test_cleanup_only_preserves_page_count(tmp_path: Path) -> None:
    source = write_blank_pdf(tmp_path / "input.pdf", pages=3)
    summary = optimize(cfg(str(source), str(tmp_path / "out.pdf"), "--no-image-recompress"))
    assert summary["pages"] == 3


def test_metadata_private_payload_stripping(tmp_path: Path) -> None:
    source = write_blank_pdf(tmp_path / "input.pdf", private_payload=True)
    summary = optimize(cfg(str(source), str(tmp_path / "out.pdf"), "--no-image-recompress"))
    assert summary["private_removed"]["/PieceInfo"] == 1
    assert summary["private_removed"]["/LastModified"] == 1


def test_quality_target_miss_warning(tmp_path: Path) -> None:
    source = write_blank_pdf(tmp_path / "input.pdf")
    summary = optimize(
        cfg(str(source), str(tmp_path / "out.pdf"), "--quality", "--target-mb", "0.000001", "--no-image-recompress")
    )
    assert summary["met_target"] is False
    assert any("Target not met" in warning for warning in summary["warnings"])


def test_missing_ghostscript_warns_not_crashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_blank_pdf(tmp_path / "input.pdf")
    output = tmp_path / "out.pdf"
    warnings: list[str] = []
    monkeypatch.setenv("PATH", "")
    result = ghostscript.run_ghostscript(source, output, target_mb=1, warnings=warnings)
    assert result is None
    assert warnings


def test_ghostscript_success_copies_best_candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_blank_pdf(tmp_path / "input.pdf")
    output = tmp_path / "out.pdf"

    def fake_run(command, capture_output, text, check):
        output_arg = next(part for part in command if str(part).startswith("-sOutputFile="))
        Path(output_arg.split("=", 1)[1]).write_bytes(b"small")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(ghostscript.shutil, "which", lambda _name: "gs")
    monkeypatch.setattr(ghostscript.subprocess, "run", fake_run)
    result = ghostscript.run_ghostscript(source, output, target_mb=1, warnings=[])
    assert result is not None
    assert result["ghostscript"]["dpi"] == 180
    assert output.read_bytes() == b"small"


def test_cli_help(env_with_src: dict[str, str]) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "pdf_email_optimizer", "--help"],
        check=False,
        capture_output=True,
        text=True,
        env=env_with_src,
    )
    assert completed.returncode == 0
    assert "--target" in completed.stdout
    assert "--audit" in completed.stdout


def test_cli_rejects_existing_output_without_force(tmp_path: Path, env_with_src: dict[str, str]) -> None:
    source = write_blank_pdf(tmp_path / "input.pdf")
    output = write_blank_pdf(tmp_path / "output.pdf")
    completed = subprocess.run(
        [sys.executable, "-m", "pdf_email_optimizer", str(source), str(output)],
        check=False,
        capture_output=True,
        text=True,
        env=env_with_src,
    )
    assert completed.returncode == 1
    assert "Output already exists" in completed.stderr


def test_report_output_writes_markdown(tmp_path: Path) -> None:
    source = write_blank_pdf(tmp_path / "input.pdf")
    report = tmp_path / "report.md"
    summary = optimize(cfg(str(source), str(tmp_path / "out.pdf")))
    reporting.write_report(summary, report)
    assert "PDF Email Optimizer Report" in report.read_text(encoding="utf-8")


def test_print_summary_and_audit_human_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = write_blank_pdf(tmp_path / "input.pdf", private_payload=True)
    summary = optimize(cfg(str(source), str(tmp_path / "out.pdf"), "--no-image-recompress"))
    summary["report"] = str(tmp_path / "report.md")
    reporting.print_summary(summary, json_output=False)
    output = capsys.readouterr()
    assert "Target:" in output.out
    assert "Report:" in output.out

    audit_summary = audit(source)
    reporting.print_audit(audit_summary, json_output=False)
    output = capsys.readouterr()
    assert "Recommended profile:" in output.out


def test_print_summary_and_audit_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = write_blank_pdf(tmp_path / "input.pdf")
    summary = optimize(cfg(str(source), str(tmp_path / "out.pdf")))
    reporting.print_summary(summary, json_output=True)
    assert json.loads(capsys.readouterr().out)["input"] == str(source.resolve())

    reporting.print_audit(audit(source), json_output=True)
    assert json.loads(capsys.readouterr().out)["input"] == str(source)


def test_audit_mode_reports_features(tmp_path: Path) -> None:
    source = write_blank_pdf(tmp_path / "input.pdf", private_payload=True)
    summary = audit(source)
    assert summary["pages"] == 1
    assert summary["structural_cleanup_likely"] is True
    assert summary["recommended_profile"] in {"balanced", "quality"}


def test_audit_encrypted_pdf_reports_unlock_guidance(tmp_path: Path) -> None:
    source = write_blank_pdf(tmp_path / "encrypted.pdf", encrypted=True)
    summary = audit(source)
    assert summary["encrypted"] is True
    assert summary["recommended_profile"] is None
    assert any("Unlock" in warning for warning in summary["warnings"])


def test_optimizer_render_compare_identical_pdf(tmp_path: Path) -> None:
    pytest.importorskip("pypdfium2")
    source = write_blank_pdf(tmp_path / "input.pdf")
    qa = render_qa.compare_render_quality(source, source, scale=0.5, max_pages=1)
    assert qa["worst_rms"] == 0.0
    assert qa["worst_psnr"] == "inf"


def test_optimizer_render_compare_size_mismatch(tmp_path: Path) -> None:
    pytest.importorskip("pypdfium2")
    source = write_blank_pdf(tmp_path / "input.pdf")
    changed = tmp_path / "changed.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=400, height=400)
    with changed.open("wb") as handle:
        writer.write(handle)
    qa = render_qa.compare_render_quality(source, changed, scale=0.5, max_pages=1)
    assert qa["worst_rms"] == "inf"
    assert qa["worst_psnr"] == 0.0


def test_render_qa_failure_marks_candidate_unacceptable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_blank_pdf(tmp_path / "input.pdf")
    result = {"path": str(source), "warnings": []}

    def fake_compare(*_args, **_kwargs):
        return {"worst_psnr": 30.0, "worst_rms": 13.0, "compared_pages": 1, "pages": []}

    monkeypatch.setattr(render_qa, "compare_render_quality", fake_compare)
    marked = render_qa.mark_render_quality(
        result,
        source,
        render_qa=True,
        min_render_psnr=38.0,
        max_render_rms=8.0,
        qa_scale=1.0,
        qa_max_pages=1,
    )
    assert marked["quality_ok"] is False
    assert len(marked["warnings"]) == 2


def test_main_audit_and_report_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from pdf_email_optimizer import cli

    source = write_blank_pdf(tmp_path / "input.pdf")
    report = tmp_path / "report.md"
    monkeypatch.setattr(
        sys,
        "argv",
        ["pdf-email-optimizer", str(source), str(tmp_path / "out.pdf"), "--report", str(report)],
    )
    assert cli.main() == 0
    assert report.exists()
    assert "Report:" in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["pdf-email-optimizer", str(source), "--audit"])
    assert cli.main() == 0
    assert "Recommended profile:" in capsys.readouterr().out


def test_optimizer_tombstone_points_to_new_home() -> None:
    import pdf_email_optimizer.optimizer as legacy

    with pytest.raises(ImportError, match="removed in v3.0.0"):
        _ = legacy.optimize


def test_new_module_layout_is_importable() -> None:
    import pdf_email_optimizer.candidates
    import pdf_email_optimizer.cli
    import pdf_email_optimizer.config
    import pdf_email_optimizer.errors
    import pdf_email_optimizer.ghostscript
    import pdf_email_optimizer.images
    import pdf_email_optimizer.input_source
    import pdf_email_optimizer.pdf_inspect
    import pdf_email_optimizer.pikepdf_backend
    import pdf_email_optimizer.pipeline
    import pdf_email_optimizer.profiles
    import pdf_email_optimizer.render_qa
    import pdf_email_optimizer.reporting
    import pdf_email_optimizer.targets

    assert callable(pdf_email_optimizer.cli.main)
    assert callable(pdf_email_optimizer.ghostscript.run_ghostscript)
    assert callable(pdf_email_optimizer.pikepdf_backend.structural_optimize)
    assert "balanced" in pdf_email_optimizer.profiles.PROFILE_DEFAULTS


def test_pikepdf_backend_reduces_or_matches(tmp_path: Path) -> None:
    pytest.importorskip("pikepdf")
    from pdf_email_optimizer import pikepdf_backend

    source = write_image_pdf(tmp_path / "image.pdf")
    output = tmp_path / "pike.pdf"
    warnings: list[str] = []
    result = pikepdf_backend.structural_optimize(source, output, warnings=warnings)
    assert result is not None
    assert output.exists()
    assert result["backend"] == "pikepdf"
    assert result["size_bytes"] == output.stat().st_size


def test_pikepdf_backend_missing_dependency_warns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    from pdf_email_optimizer import pikepdf_backend

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "pikepdf":
            raise ImportError("no pikepdf")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    warnings: list[str] = []
    result = pikepdf_backend.structural_optimize(tmp_path / "missing.pdf", tmp_path / "out.pdf", warnings=warnings)
    assert result is None
    assert any("pikepdf was not found" in warning for warning in warnings)


def test_pikepdf_disabled_skips_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = write_image_pdf(tmp_path / "image.pdf")
    called = False

    def fake_backend(*_args, **_kwargs):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(pipeline, "pikepdf_structural_optimize", fake_backend)
    optimize(cfg(str(source), str(tmp_path / "out.pdf"), "--no-pikepdf"))
    assert called is False

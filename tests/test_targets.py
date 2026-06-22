from __future__ import annotations

import pytest

from pdf_email_optimizer.targets import output_path_for, parse_mb_range, resolve_target_window


def test_parse_target_range() -> None:
    assert parse_mb_range("5-7mb") == (5.0, 7.0)
    assert parse_mb_range("7:5") == (5.0, 7.0)
    assert parse_mb_range("6") == (6.0, 6.0)


def test_parse_target_range_rejects_non_positive_values() -> None:
    with pytest.raises(ValueError):
        parse_mb_range("0-7")


def test_target_alias_accepts_units() -> None:
    target = resolve_target_window(target_range_mb=None, target="7mb", target_min_mb=None, target_mb=99, preferred_mb=None)
    assert target["max_mb"] == 7.0
    assert target["min_mb"] is None


def test_default_target_is_7mb() -> None:
    target = resolve_target_window(target_range_mb=None, target=None, target_min_mb=None, target_mb=7.0, preferred_mb=None)
    assert target["label"] == "7 MB"


def test_output_path_never_equals_input(tmp_path) -> None:
    input_path = (tmp_path / "input.pdf").resolve()
    with pytest.raises(ValueError):
        if input_path == output_path_for(input_path, str(input_path)):
            raise ValueError("Output path must be different from input path.")

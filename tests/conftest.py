from __future__ import annotations

import os
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"


@pytest.fixture
def env_with_src() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC_DIR) if not existing else f"{SRC_DIR}{os.pathsep}{existing}"
    return env


def write_blank_pdf(path: Path, *, pages: int = 1, private_payload: bool = False, encrypted: bool = False) -> Path:
    writer = PdfWriter()
    for index in range(pages):
        page = writer.add_blank_page(width=240 + index, height=320 + index)
        if private_payload:
            page[NameObject("/PieceInfo")] = DictionaryObject({NameObject("/Private"): TextStringObject("payload")})
            page[NameObject("/LastModified")] = TextStringObject("D:20260101000000")
    if private_payload:
        writer.add_metadata({"/Creator": "fixture", "/Subject": "private payload fixture"})
    if encrypted:
        writer.encrypt("secret")
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def write_image_pdf(path: Path) -> Path:
    from PIL import Image

    image = Image.new("RGB", (900, 900), "white")
    for x in range(0, 900, 30):
        for y in range(0, 900, 30):
            color = ((x * 3) % 255, (y * 5) % 255, ((x + y) * 7) % 255)
            for dx in range(15):
                for dy in range(15):
                    image.putpixel((x + dx, y + dy), color)
    image.save(path, "PDF", resolution=72)
    return path

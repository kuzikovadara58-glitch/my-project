from __future__ import annotations

import io

from PIL import Image

from journal_automation.photos.exif_reader import read_capture_datetime


def _write_jpeg(path, exif_datetime: str | None) -> None:
    image = Image.new("RGB", (2, 2), color=(10, 20, 30))
    if exif_datetime is not None:
        exif = Image.Exif()
        exif[36867] = exif_datetime  # DateTimeOriginal
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", exif=exif.tobytes())
    else:
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
    path.write_bytes(buffer.getvalue())


def test_reads_datetime_original(tmp_path):
    path = tmp_path / "photo.jpg"
    _write_jpeg(path, "2026:09:28 18:07:00")

    captured_at, source = read_capture_datetime(path)

    assert source == "exif"
    assert captured_at.isoformat() == "2026-09-28T18:07:00"


def test_missing_exif_returns_none(tmp_path):
    path = tmp_path / "photo.jpg"
    _write_jpeg(path, None)

    captured_at, source = read_capture_datetime(path)

    assert captured_at is None
    assert source == "none"


def test_corrupted_file_does_not_raise(tmp_path):
    path = tmp_path / "not-a-photo.jpg"
    path.write_bytes(b"this is not a jpeg file at all")

    captured_at, source = read_capture_datetime(path)

    assert captured_at is None
    assert source == "none"


def test_unreadable_datetime_format_ignored(tmp_path):
    path = tmp_path / "photo.jpg"
    image = Image.new("RGB", (2, 2))
    exif = Image.Exif()
    exif[36867] = "not-a-valid-date"
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif.tobytes())
    path.write_bytes(buffer.getvalue())

    captured_at, source = read_capture_datetime(path)

    assert captured_at is None
    assert source == "none"

from __future__ import annotations

import pytest

from journal_automation.photos.filename_parser import parse_filename


@pytest.mark.parametrize(
    "filename,expected_iso,expected_group",
    [
        ("2026-09-28_18-07.jpg", "2026-09-28T18:07:00", None),
        ("2026-09-28_18-07.JPG", "2026-09-28T18:07:00", None),
        ("kids_1_2026-09-28_18-07.jpg", "2026-09-28T18:07:00", "kids_1"),
        ("kids_2_2026-09-28_20-04.jpeg", "2026-09-28T20:04:00", "kids_2"),
    ],
)
def test_recognized_formats(filename, expected_iso, expected_group):
    captured_at, group = parse_filename(filename)

    assert captured_at is not None
    assert captured_at.isoformat() == expected_iso
    assert group == expected_group


@pytest.mark.parametrize(
    "filename",
    [
        "random_photo.jpg",
        "IMG_20260928_180700.jpg",
        "2026-13-40_25-99.jpg",  # синтаксически похоже, но невалидная дата/время
        "",
    ],
)
def test_unrecognized_formats_return_none(filename):
    captured_at, group = parse_filename(filename)

    assert captured_at is None
    assert group is None

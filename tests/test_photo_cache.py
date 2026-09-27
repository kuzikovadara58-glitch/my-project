from __future__ import annotations

import os
import time

from journal_automation.photos.cache import PhotoCache
from journal_automation.photos.models import TrainingPhoto


def _photo(file_id="file-1", name="2026-09-28_18-07.jpg") -> TrainingPhoto:
    return TrainingPhoto(source="google_drive", remote_file_id=file_id, remote_name=name, mime_type="image/jpeg")


def test_path_for_is_deterministic_and_sanitized(tmp_path):
    cache = PhotoCache(tmp_path)
    photo = _photo(file_id="weird:id/with*chars")

    path1 = cache.path_for(photo)
    path2 = cache.path_for(photo)

    assert path1 == path2
    assert ":" not in path1.name
    assert "/" not in path1.name
    assert "*" not in path1.name


def test_has_reflects_actual_file_presence(tmp_path):
    cache = PhotoCache(tmp_path)
    photo = _photo()

    assert cache.has(photo) is False

    cache.path_for(photo).write_bytes(b"fake-jpeg-bytes")

    assert cache.has(photo) is True


def test_cleanup_removes_old_files_but_keeps_recent(tmp_path):
    cache = PhotoCache(tmp_path)
    old_file = tmp_path / "old.jpg"
    new_file = tmp_path / "new.jpg"
    old_file.write_bytes(b"old")
    new_file.write_bytes(b"new")

    old_time = time.time() - 10 * 86400  # 10 дней назад
    os.utime(old_file, (old_time, old_time))

    removed = cache.cleanup(retention_days=7)

    assert removed == 1
    assert not old_file.exists()
    assert new_file.exists()


def test_cleanup_does_not_remove_protected_files(tmp_path):
    cache = PhotoCache(tmp_path)
    old_file = tmp_path / "old.jpg"
    old_file.write_bytes(b"old")
    old_time = time.time() - 10 * 86400
    os.utime(old_file, (old_time, old_time))

    removed = cache.cleanup(retention_days=7, protect=frozenset({old_file}))

    assert removed == 0
    assert old_file.exists()


def test_cleanup_on_missing_directory_returns_zero(tmp_path):
    cache = PhotoCache(tmp_path / "does-not-exist")

    assert cache.cleanup(retention_days=7) == 0

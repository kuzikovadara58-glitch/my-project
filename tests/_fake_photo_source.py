"""Дублёр PhotoSource для тестов PhotoService (не тестовый файл сам по себе)."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from PIL import Image

from journal_automation.photos.models import TrainingPhoto


def jpeg_bytes(exif_datetime: datetime | None = None) -> bytes:
    image = Image.new("RGB", (2, 2), color=(1, 2, 3))
    buffer = io.BytesIO()
    if exif_datetime is not None:
        exif = Image.Exif()
        exif[36867] = exif_datetime.strftime("%Y:%m:%d %H:%M:%S")
        image.save(buffer, format="JPEG", exif=exif.tobytes())
    else:
        image.save(buffer, format="JPEG")
    return buffer.getvalue()


class FakePhotoSource:
    def __init__(self, candidates: list[TrainingPhoto], cache_dir: Path) -> None:
        self._candidates = candidates
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        # file_id -> bytes | Exception
        self.file_contents: dict[str, bytes | Exception] = {}
        self.download_calls: list[str] = []
        self.list_error: Exception | None = None

    def list_candidates(self, session) -> list[TrainingPhoto]:
        if self.list_error is not None:
            raise self.list_error
        return list(self._candidates)

    def download_photo(self, photo: TrainingPhoto) -> Path:
        self.download_calls.append(photo.remote_file_id)
        content = self.file_contents.get(photo.remote_file_id, jpeg_bytes())
        if isinstance(content, Exception):
            raise content
        path = self._cache_dir / f"{photo.remote_file_id}.jpg"
        path.write_bytes(content)
        return path

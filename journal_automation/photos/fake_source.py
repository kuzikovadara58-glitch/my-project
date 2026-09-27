"""Демонстрационный источник фото — не обращается к реальному Google Drive.

docs/SPEC.md, этап 4, раздел 30: `python main.py --demo` должен воспроизводимо
проходить весь конвейер (список кандидатов → скачивание → EXIF → выбор), но
на полностью синтетических данных. Поэтому "скачивание" здесь на самом деле
создаёт настоящий JPEG с настоящим EXIF через Pillow — дальше по конвейеру
работает тот же код чтения EXIF/валидации, что и с реальным Drive, только
файл не пришёл из интернета.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Literal

from PIL import Image

from journal_automation.domain.session import TrainingSession
from journal_automation.photos.cache import PhotoCache
from journal_automation.photos.models import TrainingPhoto
from journal_automation.photos.source import PhotoSourceUnavailableError

DemoPhotoMode = Literal["success", "missing", "error", "ambiguous"]


class FakeGoogleDrivePhotoSource:
    def __init__(self, mode: DemoPhotoMode, cache: PhotoCache) -> None:
        self._mode = mode
        self._cache = cache

    def list_candidates(self, session: TrainingSession) -> list[TrainingPhoto]:
        if self._mode == "error":
            raise PhotoSourceUnavailableError(
                "демо: смоделированная недоступность Google Drive (--simulate-drive-error)"
            )
        if self._mode == "missing":
            return []

        base_name = f"{session.group_id}_{session.date:%Y-%m-%d}_{session.start_time:%H-%M}"

        first = TrainingPhoto(
            source="demo",
            remote_file_id=f"demo-{session.session_id}-1",
            remote_name=f"{base_name}.jpg",
            mime_type="image/jpeg",
        )
        if self._mode == "success":
            return [first]

        # ambiguous — второй кандидат с ТЕМ ЖЕ именем (в Google Drive два файла
        # в одной папке могут называться одинаково) -> та же дата/время съёмки,
        # тот же источник времени -> детерминированный tie-break не может
        # выбрать между ними, как и должно быть при настоящей неоднозначности.
        second = TrainingPhoto(
            source="demo",
            remote_file_id=f"demo-{session.session_id}-2",
            remote_name=f"{base_name}.jpg",
            mime_type="image/jpeg",
        )
        return [first, second]

    def download_photo(self, photo: TrainingPhoto) -> Path:
        cached_path = self._cache.path_for(photo)
        if cached_path.is_file():
            return cached_path

        capture_time = _capture_time_for(photo)
        self._cache.cache_dir.mkdir(parents=True, exist_ok=True)
        _write_fake_jpeg_with_exif(cached_path, capture_time)
        return cached_path


def _capture_time_for(photo: TrainingPhoto):
    # Имя файла уже несёт дату/время в рекомендованном формате — переиспользуем
    # тот же парсер, что и для реальных файлов, вместо отдельной demo-логики.
    from journal_automation.photos.filename_parser import parse_filename

    captured_at, _group = parse_filename(photo.remote_name)
    return captured_at


def _write_fake_jpeg_with_exif(path: Path, capture_time) -> None:
    image = Image.new("RGB", (4, 4), color=(120, 160, 200))
    exif = Image.Exif()
    if capture_time is not None:
        formatted = capture_time.strftime("%Y:%m:%d %H:%M:%S")
        exif[36867] = formatted  # DateTimeOriginal
        exif[36868] = formatted  # DateTimeDigitized

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif.tobytes())
    path.write_bytes(buffer.getvalue())

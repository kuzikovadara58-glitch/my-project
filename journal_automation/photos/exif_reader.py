"""Чтение времени съёмки из EXIF (docs/SPEC.md, этап 4, разделы 6, 13, 15).

Главный источник времени съёмки — EXIF DateTimeOriginal, затем
DateTimeDigitized. Один повреждённый/неподдерживаемый файл не должен ломать
весь поиск фото — любая проблема здесь просто означает "EXIF недоступен",
а не исключение наружу.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)

# Теги EXIF (см. PIL.ExifTags): 36867 = DateTimeOriginal, 36868 = DateTimeDigitized.
_DATETIME_ORIGINAL = 36867
_DATETIME_DIGITIZED = 36868
_EXIF_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"


def read_capture_datetime(path: Path) -> tuple[datetime | None, str]:
    """Возвращает (время_съёмки, источник). Источник — всегда "exif" или "none".

    Никогда не выбрасывает исключение наружу — повреждённый/неподдерживаемый
    файл просто не даёт даты (docs/SPEC.md, этап 4, раздел 15).
    """

    try:
        with Image.open(path) as image:
            exif = image.getexif()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        logger.info("EXIF недоступен для %s: %s", path.name, exc)
        return None, "none"

    for tag_id in (_DATETIME_ORIGINAL, _DATETIME_DIGITIZED):
        raw_value = exif.get(tag_id)
        if not raw_value:
            continue
        try:
            return datetime.strptime(str(raw_value).strip(), _EXIF_DATETIME_FORMAT), "exif"
        except ValueError:
            logger.info("Некорректный формат даты EXIF в %s: %r", path.name, raw_value)
            continue

    return None, "none"

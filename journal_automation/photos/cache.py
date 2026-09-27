"""Локальный кэш скачанных фотографий (docs/SPEC.md, этап 4, разделы 9, 11).

Отдельный каталог от постоянных пользовательских данных, не путать с
`photos/` как постоянным локальным хранилищем (раздел 9). Скачанный файл —
временный: он существует, только чтобы дальше передать его локальный путь
дальше по конвейеру (в будущем — Playwright, раздел 10).
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from journal_automation.photos.models import TrainingPhoto

logger = logging.getLogger(__name__)

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class PhotoCache:
    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def path_for(self, photo: TrainingPhoto) -> Path:
        """Детерминированный путь для файла — одинаковый при повторном обращении

        к тому же remote_file_id, это и даёт повторное использование кэша
        без повторного скачивания.
        """

        # Санитизируем оба компонента: реальные Drive file id всегда
        # буквенно-цифровые, но демонстрационный/будущий локальный источник
        # может подставить что угодно (например, session_id с двоеточиями,
        # недопустимыми в путях Windows).
        safe_id = _UNSAFE_CHARS.sub("_", photo.remote_file_id) or "file"
        safe_name = _UNSAFE_CHARS.sub("_", photo.remote_name) or "photo"
        return self._cache_dir / f"{safe_id}_{safe_name}"

    def has(self, photo: TrainingPhoto) -> bool:
        return self.path_for(photo).is_file()

    def cleanup(self, retention_days: int, protect: frozenset[Path] = frozenset()) -> int:
        """Удаляет файлы кэша старше `retention_days`, кроме путей из `protect`

        (сейчас используемых занятием, которое обрабатывается — раздел 11:
        "не удалять файл, если он сейчас используется"). Никогда не трогает
        сам Google Drive — только локальные файлы кэша.
        """

        if not self._cache_dir.is_dir():
            return 0

        cutoff = time.time() - retention_days * 86400
        removed = 0
        for path in self._cache_dir.iterdir():
            if not path.is_file() or path in protect:
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
                    logger.info("Удалён устаревший файл кэша фото: %s", path.name)
            except OSError as exc:
                logger.warning("Не удалось удалить файл кэша %s: %s", path.name, exc)
        return removed

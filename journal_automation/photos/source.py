"""Абстракция источника фотографий (docs/SPEC.md, этап 4, раздел 5).

`PhotoService` работает только с этим интерфейсом и не знает деталей
Google Drive API — так же, как `SchedulerLoop` не знает деталей сайта
журнала за `JournalAutomationPort` (этап 3). В будущем `LocalPhotoSource`
подключается без изменения `PhotoService`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from journal_automation.domain.session import TrainingSession
from journal_automation.photos.models import TrainingPhoto


class PhotoSourceError(Exception):
    """Базовый класс ошибок источника фото."""


class PhotoSourceUnavailableError(PhotoSourceError):
    """Источник целиком недоступен: нет сети, истёк токен, нет доступа к

    папке, неверный folder_id, API временно недоступен после исчерпания
    повторных попыток (docs/SPEC.md, этап 4, раздел 22).
    """


class CandidateUnavailableError(PhotoSourceError):
    """Один конкретный файл недоступен (пропал между list и download,

    повреждён и т.п.) — не должно ронять весь поиск (раздел 15/34: "файл
    исчез между list/download").
    """


class PhotoSource(Protocol):
    def list_candidates(self, session: TrainingSession) -> list[TrainingPhoto]:
        """Возвращает кандидатов (только метаданные, без скачивания).

        Поднимает `PhotoSourceUnavailableError`, если источник недоступен
        целиком. Пустой список — это не ошибка, а "фото пока нет".
        """
        ...

    def download_photo(self, photo: TrainingPhoto) -> Path:
        """Скачивает (или берёт из кэша) файл и возвращает локальный путь.

        Поднимает `CandidateUnavailableError`, если именно этот файл исчез/
        повреждён, или `PhotoSourceUnavailableError`, если недоступен весь
        источник.
        """
        ...

"""Фотография занятия: проверки перед загрузкой (docs/SPEC.md, раздел 3).

Реальное чтение EXIF (время съёмки) — открытый вопрос из
docs/ARCHITECTURE.md §8: выбор библиотеки не сделан, чтобы не добавлять
незапрошенную на этапе 2 зависимость. Здесь `detected_datetime` — это вход,
который на этом этапе поставляет вызывающий код (в будущем — модуль чтения
EXIF), а не то, что этот модуль извлекает из файла сам. Время
создания/копирования файла НЕ является допустимым источником этого значения
(docs/SPEC.md: "Не считать время создания или копирования файла достоверным
временем съёмки") — этот модуль вообще не смотрит на файловые метки времени
файловой системы, только на переданное значение.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from enum import Enum
from pathlib import Path

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MIN_FILE_SIZE_BYTES = 1024  # 1 КБ — отсекает пустые/битые файлы
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 МБ


class PhotoValidationState(str, Enum):
    NOT_PROVIDED = "not_provided"
    NEEDS_CONFIRMATION = "needs_confirmation"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


def compute_file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class PhotoCandidate:
    path: Path
    session_id: str
    group_id: str
    file_hash: str
    detected_datetime: datetime | None = None
    source_of_datetime: str = "unknown"  # "exif" | "user_confirmed" | "unknown"

    @classmethod
    def from_file(
        cls,
        path: Path,
        session_id: str,
        group_id: str,
        detected_datetime: datetime | None = None,
        source_of_datetime: str = "unknown",
    ) -> "PhotoCandidate":
        return cls(
            path=path,
            session_id=session_id,
            group_id=group_id,
            file_hash=compute_file_hash(path),
            detected_datetime=detected_datetime,
            source_of_datetime=source_of_datetime,
        )


def validate_photo_candidate(
    candidate: PhotoCandidate,
    session_start: datetime,
    session_end: datetime,
    tolerance_before_minutes: int,
    tolerance_after_minutes: int,
    known_hashes_for_session: frozenset[str],
) -> PhotoValidationState:
    """Проверяет кандидата в фото занятия. Не трогает файловую систему, кроме

    уже вычисленного `file_hash` — сама проверка чистая и легко тестируется.
    """

    if candidate.file_hash in known_hashes_for_session:
        return PhotoValidationState.REJECTED  # уже загружено для этого занятия

    if candidate.path.suffix.lower() not in ALLOWED_EXTENSIONS:
        return PhotoValidationState.REJECTED

    try:
        size = candidate.path.stat().st_size
    except OSError:
        return PhotoValidationState.REJECTED
    if not (MIN_FILE_SIZE_BYTES <= size <= MAX_FILE_SIZE_BYTES):
        return PhotoValidationState.REJECTED

    if candidate.detected_datetime is None:
        return PhotoValidationState.NEEDS_CONFIRMATION

    window_start = session_start.astimezone(_tz(session_start)) - timedelta(
        minutes=tolerance_before_minutes
    )
    window_end = session_end.astimezone(_tz(session_end)) + timedelta(
        minutes=tolerance_after_minutes
    )
    detected = candidate.detected_datetime
    if detected.tzinfo is None:
        # Naive-время съёмки неоднозначно (неизвестен часовой пояс съёмки) —
        # не считаем его достоверным само по себе.
        return PhotoValidationState.NEEDS_CONFIRMATION

    if window_start <= detected <= window_end:
        return PhotoValidationState.CONFIRMED
    return PhotoValidationState.NEEDS_CONFIRMATION


def _tz(value: datetime) -> tzinfo:
    assert value.tzinfo is not None
    return value.tzinfo



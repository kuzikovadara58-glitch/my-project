"""Проверка соответствия фото занятию (docs/SPEC.md, этап 4, разделы 16-18).

Только проверяет уже существующие данные — никогда не изменяет EXIF, имя
файла или метаданные ради совпадения (раздел 18).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from journal_automation.config.models import PhotosSettings
from journal_automation.domain.session import TrainingSession
from journal_automation.photos.models import TrainingPhoto, TrainingPhotoValidationStatus


def is_photo_time_valid(
    captured_at: datetime,
    session_start: datetime,
    session_end: datetime,
    tolerance_before_minutes: int,
    tolerance_after_minutes: int,
) -> bool:
    """Чистая функция: попадает ли момент съёмки в допустимое окно занятия."""

    window_start = session_start - timedelta(minutes=tolerance_before_minutes)
    window_end = session_end + timedelta(minutes=tolerance_after_minutes)
    return window_start <= captured_at <= window_end


def validate_training_photo(
    photo: TrainingPhoto,
    session: TrainingSession,
    tz: ZoneInfo,
    settings: PhotosSettings,
) -> TrainingPhoto:
    """Возвращает копию `photo` с заполненными validation_status/validation_errors."""

    if photo.captured_at is None:
        return replace(
            photo,
            validation_status=TrainingPhotoValidationStatus.INVALID,
            validation_errors=("не удалось определить дату/время съёмки",),
        )

    captured_at = photo.captured_at
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=tz)
    else:
        captured_at = captured_at.astimezone(tz)

    errors: list[str] = []

    if captured_at.date() != session.date:
        errors.append(
            f"дата фото {captured_at.date():%Y-%m-%d} не совпадает с датой занятия "
            f"{session.date:%Y-%m-%d}"
        )

    if not is_photo_time_valid(
        captured_at,
        session.start_datetime(tz),
        session.end_datetime(tz),
        settings.time_tolerance_before_minutes,
        settings.time_tolerance_after_minutes,
    ):
        errors.append("время съёмки вне допустимого окна занятия")

    status = TrainingPhotoValidationStatus.INVALID if errors else TrainingPhotoValidationStatus.VALID
    return replace(photo, validation_status=status, validation_errors=tuple(errors))

"""PhotoService — оркестратор выбора фото для занятия (docs/SPEC.md, этап 4).

Реализует конвейер из раздела 8: получить метаданные → дёшево отфильтровать
по имени файла БЕЗ скачивания → скачать только узкий набор кандидатов →
проверить EXIF → выбрать итоговое фото. Не знает про Google Drive напрямую —
работает только через `PhotoSource`.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta

from journal_automation.config.models import PhotosSettings
from journal_automation.domain.session import TrainingSession
from journal_automation.photos.exif_reader import read_capture_datetime
from journal_automation.photos.filename_parser import parse_filename
from journal_automation.photos.models import (
    PhotoSelectionResult,
    PhotoSelectionStatus,
    TrainingPhoto,
    TrainingPhotoValidationStatus,
)
from journal_automation.photos.source import (
    CandidateUnavailableError,
    PhotoSource,
    PhotoSourceUnavailableError,
)
from journal_automation.photos.validation import validate_training_photo
from journal_automation.services.time_service import TimeService

logger = logging.getLogger(__name__)

# Верхняя граница, сколько файлов вообще скачивать за одну проверку —
# защита от "скачать всю папку" даже если дешёвый отбор по имени файла
# оставил слишком много кандидатов (docs/SPEC.md, этап 4, раздел 8).
_MAX_CANDIDATES_TO_DOWNLOAD = 5

_DATETIME_SOURCE_PRIORITY = {
    "exif": 0,
    "filename": 1,
    "drive_created_time": 2,
    "drive_modified_time": 2,
}


class PhotoService:
    def __init__(
        self,
        source: PhotoSource,
        settings: PhotosSettings,
        time_service: TimeService,
        max_candidates_to_download: int = _MAX_CANDIDATES_TO_DOWNLOAD,
    ) -> None:
        self._source = source
        self._settings = settings
        self._time_service = time_service
        self._max_candidates_to_download = max_candidates_to_download

    def get_photo_for_session(self, session: TrainingSession) -> PhotoSelectionResult:
        tz = self._time_service.timezone

        try:
            raw_candidates = self._source.list_candidates(session)
        except PhotoSourceUnavailableError as exc:
            logger.warning("Источник фото недоступен для %s: %s", session.session_id, exc)
            return PhotoSelectionResult(PhotoSelectionStatus.SOURCE_UNAVAILABLE, message=str(exc))

        narrowed = self._narrow_by_filename_hint(raw_candidates, session)[
            : self._max_candidates_to_download
        ]

        downloaded: list[TrainingPhoto] = []
        for candidate in narrowed:
            try:
                local_path = self._source.download_photo(candidate)
            except CandidateUnavailableError as exc:
                logger.info("Кандидат недоступен, пропускаем: %s (%s)", candidate.remote_name, exc)
                continue
            downloaded.append(self._resolve_capture_datetime(candidate, local_path))

        validated = [
            validate_training_photo(photo, session, tz, self._settings) for photo in downloaded
        ]
        valid = [p for p in validated if p.validation_status is TrainingPhotoValidationStatus.VALID]

        if not valid:
            if self._within_wait_window(session, tz):
                return PhotoSelectionResult(
                    PhotoSelectionStatus.WAITING_FOR_PHOTO,
                    candidates=tuple(validated),
                    message="подходящее фото пока не найдено, ожидание Google Drive",
                )
            return PhotoSelectionResult(
                PhotoSelectionStatus.NOT_FOUND,
                candidates=tuple(validated),
                message="подходящая фотография не найдена",
            )

        best = self._select_best(valid, session, tz)
        if best is None:
            names = ", ".join(p.remote_name for p in valid)
            return PhotoSelectionResult(
                PhotoSelectionStatus.AMBIGUOUS,
                candidates=tuple(valid),
                message=f"найдено несколько подходящих фотографий: {names}",
            )

        return PhotoSelectionResult(PhotoSelectionStatus.FOUND, photo=best, candidates=tuple(valid))

    def _narrow_by_filename_hint(
        self, candidates: list[TrainingPhoto], session: TrainingSession
    ) -> list[TrainingPhoto]:
        """Отсеивает то, что имя файла УВЕРЕННО относит к другой дате — без

        скачивания. Неразбираемое имя не отбрасывается: имя файла — лишь
        подсказка, авторитетный источник — EXIF (раздел 13).
        """

        kept: list[tuple[float, TrainingPhoto]] = []
        for candidate in candidates:
            hinted_at, _group = parse_filename(candidate.remote_name)
            if hinted_at is not None and hinted_at.date() != session.date:
                continue
            distance = (
                abs((hinted_at - _naive(session.start_time, session.date)).total_seconds())
                if hinted_at is not None
                else float("inf")
            )
            kept.append((distance, candidate))
        kept.sort(key=lambda pair: pair[0])
        return [candidate for _distance, candidate in kept]

    def _resolve_capture_datetime(self, candidate: TrainingPhoto, local_path) -> TrainingPhoto:
        captured_at, source_label = read_capture_datetime(local_path)
        if captured_at is None:
            captured_at, _group = parse_filename(candidate.remote_name)
            source_label = "filename" if captured_at is not None else "unknown"
        if captured_at is None and self._settings.allow_drive_timestamp_fallback:
            if candidate.remote_created_at is not None:
                captured_at, source_label = candidate.remote_created_at, "drive_created_time"
            elif candidate.remote_modified_at is not None:
                captured_at, source_label = candidate.remote_modified_at, "drive_modified_time"

        return replace(
            candidate, local_path=local_path, captured_at=captured_at, datetime_source=source_label
        )

    def _within_wait_window(self, session: TrainingSession, tz) -> bool:
        deadline = session.end_datetime(tz) + timedelta(
            minutes=self._settings.wait_for_photo_until_minutes_after_end
        )
        return self._time_service.now() <= deadline

    def _select_best(
        self, valid: list[TrainingPhoto], session: TrainingSession, tz
    ) -> TrainingPhoto | None:
        start_dt = session.start_datetime(tz)

        def sort_key(photo: TrainingPhoto) -> tuple[int, float]:
            captured = photo.captured_at
            if captured.tzinfo is None:
                captured = captured.replace(tzinfo=tz)
            distance = abs((captured - start_dt).total_seconds())
            return (_DATETIME_SOURCE_PRIORITY.get(photo.datetime_source, 9), distance)

        ranked = sorted(valid, key=sort_key)
        if len(ranked) == 1:
            return ranked[0]
        if sort_key(ranked[0]) == sort_key(ranked[1]):
            return None  # неоднозначно — не выбираем случайно (раздел 20)
        return ranked[0]


def _naive(time_, date_) -> datetime:
    return datetime.combine(date_, time_)

"""Реализация PhotoSource поверх Google Drive API (docs/SPEC.md, этап 4).

Не парсит HTML Google Drive и не использует Playwright (раздел 2) — только
официальный Drive API v3. Не скачивает всю папку: `list_candidates` только
запрашивает метаданные, `download_photo` вызывается лишь для уже отобранных
кандидатов (раздел 8).

`drive_service` внедряется извне (см. `create_drive_service` в этом модуле
для реальной сборки) — это и есть граница модульного тестирования: юнит-тесты
подают дублёр вместо реального `googleapiclient`-объекта, не обращаясь к
интернету (docs/SPEC.md, этап 4, раздел 34).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from googleapiclient.errors import HttpError

from journal_automation.domain.session import TrainingSession
from journal_automation.photos.cache import PhotoCache
from journal_automation.photos.models import TrainingPhoto
from journal_automation.photos.source import CandidateUnavailableError, PhotoSourceUnavailableError

logger = logging.getLogger(__name__)

_IMAGE_MIME_PREFIX = "image/"
_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
_TRANSIENT_STATUSES = {408, 429, 500, 502, 503, 504}
_LIST_FIELDS = "files(id,name,mimeType,createdTime,modifiedTime,size,parents)"


class GoogleDrivePhotoSource:
    def __init__(
        self,
        drive_service: Any,
        folder_id: str,
        cache: PhotoCache,
        max_retries: int = 3,
        base_backoff_seconds: float = 0.5,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._service = drive_service
        self._folder_id = folder_id
        self._cache = cache
        self._max_retries = max_retries
        self._base_backoff_seconds = base_backoff_seconds
        self._sleep_fn = sleep_fn

    def list_candidates(self, session: TrainingSession) -> list[TrainingPhoto]:
        target_folder_id = self._resolve_group_folder_id(session.group_id) or self._folder_id
        query = (
            f"'{target_folder_id}' in parents and trashed = false "
            f"and mimeType contains 'image/'"
        )
        try:
            response = self._call_with_retry(
                lambda: self._service.files()
                .list(q=query, fields=_LIST_FIELDS, pageSize=200)
                .execute()
            )
        except HttpError as exc:
            raise PhotoSourceUnavailableError(
                f"Не удалось получить список файлов Google Drive: {exc}"
            ) from exc

        return [self._to_training_photo(item, target_folder_id) for item in response.get("files", [])]

    def download_photo(self, photo: TrainingPhoto) -> Path:
        cached_path = self._cache.path_for(photo)
        if cached_path.is_file():
            return cached_path

        try:
            data = self._call_with_retry(
                lambda: self._service.files().get_media(fileId=photo.remote_file_id).execute()
            )
        except HttpError as exc:
            status = getattr(exc.resp, "status", None)
            if status == 404:
                raise CandidateUnavailableError(
                    f"Файл исчез из Google Drive: {photo.remote_name}"
                ) from exc
            raise PhotoSourceUnavailableError(
                f"Не удалось скачать {photo.remote_name}: {exc}"
            ) from exc

        self._cache.cache_dir.mkdir(parents=True, exist_ok=True)
        cached_path.write_bytes(data)
        return cached_path

    def _resolve_group_folder_id(self, group_id: str) -> str | None:
        """Ищет подпапку с именем == group_id внутри корневой папки

        (структура из docs/SPEC.md, этап 4, раздел 7). Если такой подпапки
        нет — считаем структуру плоской и используем корневую папку целиком
        (фильтрация по группе тогда идёт по имени файла — см. PhotoService).
        """

        query = (
            f"'{self._folder_id}' in parents and name = '{group_id}' "
            f"and mimeType = '{_FOLDER_MIME_TYPE}' and trashed = false"
        )
        try:
            response = self._call_with_retry(
                lambda: self._service.files().list(q=query, fields="files(id,name)").execute()
            )
        except HttpError:
            return None
        files = response.get("files", [])
        return files[0]["id"] if files else None

    def _to_training_photo(self, item: dict, parent_id: str) -> TrainingPhoto:
        return TrainingPhoto(
            source="google_drive",
            remote_file_id=item["id"],
            remote_name=item.get("name", item["id"]),
            mime_type=item.get("mimeType", ""),
            remote_created_at=_parse_drive_timestamp(item.get("createdTime")),
            remote_modified_at=_parse_drive_timestamp(item.get("modifiedTime")),
            remote_parent_id=parent_id,
            size_bytes=int(item["size"]) if item.get("size") else None,
        )

    def _call_with_retry(self, call: Callable[[], Any]) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return call()
            except HttpError as exc:
                status = getattr(exc.resp, "status", None)
                if status not in _TRANSIENT_STATUSES:
                    raise
                last_exc = exc
            except (ConnectionError, TimeoutError) as exc:
                last_exc = exc

            if attempt < self._max_retries:
                logger.info(
                    "Google Drive: временная ошибка (попытка %s/%s): %s",
                    attempt, self._max_retries, last_exc,
                )
                self._sleep_fn(self._base_backoff_seconds * attempt)

        raise PhotoSourceUnavailableError(
            f"Google Drive недоступен после {self._max_retries} попыток: {last_exc}"
        ) from last_exc


def _parse_drive_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None

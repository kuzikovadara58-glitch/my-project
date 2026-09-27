"""Сборка PhotoService для обычного (не demo) режима (docs/SPEC.md, этап 4).

Если папка Google Drive ещё не настроена (пустой `folder_url`/`folder_id`,
placeholder-состояние по умолчанию, раздел 39) — возвращает `None`, и
планировщик работает ровно как на этапе 3, без проверки фото. OAuth-вход
запускается только тогда, когда реальная папка действительно указана —
не при обычном запуске приложения с пустой конфигурацией.
"""

from __future__ import annotations

import logging

from journal_automation.config.manager import LoadedConfig
from journal_automation.paths import AppPaths
from journal_automation.photos.cache import PhotoCache
from journal_automation.photos.google_drive_auth import GoogleDriveSetupError, create_drive_service
from journal_automation.photos.google_drive_source import GoogleDrivePhotoSource
from journal_automation.photos.google_drive_url import extract_folder_id
from journal_automation.photos.service import PhotoService
from journal_automation.services.time_service import TimeService

logger = logging.getLogger(__name__)


def build_photo_service(
    config: LoadedConfig, paths: AppPaths, time_service: TimeService
) -> PhotoService | None:
    photos = config.app.photos
    if photos.source != "google_drive":
        return None

    reference = photos.google_drive.folder_url or photos.google_drive.folder_id
    if not reference:
        logger.info("Google Drive не настроен (пустая ссылка на папку) — источник фото отключён")
        return None

    folder_id = extract_folder_id(reference)  # уже провалидировано ConfigManager при загрузке

    cache_dir = paths.resolve_configured_path(config.app.paths.data) / "cache" / "photos"
    cache = PhotoCache(cache_dir)

    credentials_path = paths.user_data_root / "google_drive_credentials.json"
    token_path = paths.user_data_root / "google_drive_token.json"

    try:
        drive_service = create_drive_service(credentials_path, token_path)
    except GoogleDriveSetupError as exc:
        logger.warning("Google Drive настроен, но авторизация не завершена: %s", exc)
        return None

    source = GoogleDrivePhotoSource(drive_service, folder_id, cache)
    return PhotoService(source, photos, time_service)

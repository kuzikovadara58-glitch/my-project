"""Извлечение folder_id из ссылки Google Drive (docs/SPEC.md, этап 4, раздел 4).

Не зависит ни от googleapiclient, ни от остального проекта — чистая функция
над строкой, чтобы её можно было использовать и в ConfigManager (валидация
при загрузке настроек), и в GoogleDrivePhotoSource.
"""

from __future__ import annotations

import re

# Поддерживаемые варианты ссылок на папку Google Drive:
#   https://drive.google.com/drive/folders/<id>
#   https://drive.google.com/drive/folders/<id>?usp=sharing
#   https://drive.google.com/drive/u/0/folders/<id>
#   https://drive.google.com/open?id=<id>
#   голый <id> без ссылки вообще
_FOLDER_PATTERNS = (
    re.compile(r"drive\.google\.com/drive/(?:u/\d+/)?folders/([a-zA-Z0-9_-]+)"),
    re.compile(r"drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)"),
    re.compile(r"[?&]id=([a-zA-Z0-9_-]+)"),
)
_BARE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{10,}$")


class InvalidGoogleDriveFolderReference(ValueError):
    """Ссылка/идентификатор папки Google Drive не удалось разобрать."""


def extract_folder_id(folder_url_or_id: str) -> str:
    value = folder_url_or_id.strip()
    if not value:
        raise InvalidGoogleDriveFolderReference("ссылка или идентификатор папки не указаны")

    for pattern in _FOLDER_PATTERNS:
        match = pattern.search(value)
        if match:
            return match.group(1)

    if _BARE_ID_PATTERN.fullmatch(value):
        return value

    raise InvalidGoogleDriveFolderReference(
        f"не удалось извлечь folder_id из значения: {folder_url_or_id!r}"
    )

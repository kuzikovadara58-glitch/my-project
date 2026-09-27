"""Доменные модели для источника фотографий Google Drive (этап 4).

Отдельно от `journal_automation/domain/photo.py` (этап 2): та сущность
(`PhotoCandidate`/`PhotoValidationState`) — про финальную проверку ПЕРЕД
загрузкой уже выбранного фото на сайт (пригодится на этапе 6). Этот модуль —
про то, откуда фото вообще берётся и как выбирается среди нескольких
кандидатов в Google Drive. Слои дополняют друг друга, а не дублируются.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class TrainingPhotoValidationStatus(str, Enum):
    PENDING = "pending"  # ещё не проверено (метаданные есть, файл не скачан)
    VALID = "valid"
    INVALID = "invalid"


class PhotoSelectionStatus(str, Enum):
    FOUND = "found"
    WAITING_FOR_PHOTO = "waiting_for_photo"
    NOT_FOUND = "not_found"
    SOURCE_UNAVAILABLE = "source_unavailable"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class TrainingPhoto:
    source: str  # "google_drive" | "local" | "demo"
    remote_file_id: str
    remote_name: str
    mime_type: str
    remote_created_at: datetime | None = None
    remote_modified_at: datetime | None = None
    remote_parent_id: str | None = None
    size_bytes: int | None = None

    local_path: Path | None = None

    captured_at: datetime | None = None
    # "exif" | "filename" | "drive_created_time" | "drive_modified_time" | "unknown"
    datetime_source: str = "unknown"

    validation_status: TrainingPhotoValidationStatus = TrainingPhotoValidationStatus.PENDING
    validation_errors: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PhotoSelectionResult:
    status: PhotoSelectionStatus
    photo: TrainingPhoto | None = None
    candidates: tuple[TrainingPhoto, ...] = field(default_factory=tuple)
    message: str = ""

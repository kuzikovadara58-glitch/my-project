"""Типизированные модели конфигурации (settings/groups/absences/reasons).

Это только данные и лёгкая валидация типов внутри одной записи. Проверки,
которым нужно видеть несколько файлов сразу (например: существует ли
athlete_id в составе группы) — в ConfigManager, а не здесь (docs/SPEC.md,
раздел 6: "не размазывать чтение YAML по всему проекту").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_
from datetime import time as time_

WEEKDAYS: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

GenderLiteral = str  # "m" | "f" | None — намеренно не Enum, см. Athlete.gender


@dataclass(frozen=True)
class Athlete:
    id: str
    full_name: str
    gender: GenderLiteral | None = None  # используется только для согласования
    # рода в шаблонах причин ("отпросился"/"отпросилась"); отсутствие пола не
    # блокирует работу — используется базовая (мужская) форма шаблона.


@dataclass(frozen=True)
class TrainingSchedule:
    weekday: int  # 0=понедельник .. 6=воскресенье (см. WEEKDAYS)
    start: time_
    end: time_

    def __post_init__(self) -> None:
        if not (0 <= self.weekday <= 6):
            raise ValueError(f"Некорректный день недели: {self.weekday}")
        if self.start >= self.end:
            raise ValueError(
                f"Время начала должно быть раньше окончания: {self.start} >= {self.end}"
            )


@dataclass(frozen=True)
class Group:
    id: str
    name: str
    journal_group_id: str
    schedule: tuple[TrainingSchedule, ...]
    athletes: tuple[Athlete, ...]

    def athlete_by_id(self, athlete_id: str) -> Athlete | None:
        for athlete in self.athletes:
            if athlete.id == athlete_id:
                return athlete
        return None


@dataclass(frozen=True)
class PathsSettings:
    photos: str = "photos"
    data: str = "data"
    logs: str = "logs"


@dataclass(frozen=True)
class AutomationSettings:
    # Ровно один из режимов действует одновременно: если задан
    # fill_after_start_minutes — используется он; иначе fill_after_end_minutes.
    fill_after_start_minutes: int | None = None
    fill_after_end_minutes: int = 10
    photo_time_tolerance_before_minutes: int = 30
    photo_time_tolerance_after_minutes: int = 120

    def __post_init__(self) -> None:
        for name in (
            "fill_after_start_minutes",
            "fill_after_end_minutes",
            "photo_time_tolerance_before_minutes",
            "photo_time_tolerance_after_minutes",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} не может быть отрицательным: {value}")


@dataclass(frozen=True)
class GoogleDriveSettings:
    """Ссылка на постоянную папку с фото (docs/SPEC.md, этап 4, раздел 4).

    Ровно одно из полей заполняется пользователем — `folder_url` (обычная
    ссылка Google Drive) предпочтительнее `folder_id`. До того как ссылка
    предоставлена, оба поля — пустые строки, это ожидаемое, а не ошибочное
    состояние (этап 4, раздел 39).
    """

    folder_url: str = ""
    folder_id: str = ""


@dataclass(frozen=True)
class PhotosSettings:
    """Настройки источника фотографий (docs/SPEC.md, этап 4)."""

    source: str = "google_drive"  # "google_drive" | "local" (LocalPhotoSource — задел на будущее)
    google_drive: GoogleDriveSettings = field(default_factory=GoogleDriveSettings)
    allow_drive_timestamp_fallback: bool = False
    time_tolerance_before_minutes: int = 15
    time_tolerance_after_minutes: int = 120
    wait_for_photo_until_minutes_after_end: int = 30
    recheck_interval_seconds: int = 60
    cache_retention_days: int = 7

    def __post_init__(self) -> None:
        if self.source not in ("google_drive", "local"):
            raise ValueError(f"photos.source: неизвестный источник '{self.source}'")
        for name in (
            "time_tolerance_before_minutes",
            "time_tolerance_after_minutes",
            "wait_for_photo_until_minutes_after_end",
            "recheck_interval_seconds",
            "cache_retention_days",
        ):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"photos.{name} не может быть отрицательным: {value}")


@dataclass(frozen=True)
class AppConfig:
    timezone: str
    automation: AutomationSettings
    paths: PathsSettings
    photos: PhotosSettings = field(default_factory=PhotosSettings)


@dataclass(frozen=True)
class AbsenceReason:
    key: str
    text_masculine: str


@dataclass(frozen=True)
class AttendanceRecordConfig:
    """Одна запись об отсутствии конкретного спортсмена на занятии."""

    athlete_id: str
    reason_key: str | None = None
    custom_comment: str | None = None

    def __post_init__(self) -> None:
        has_reason = self.reason_key is not None
        has_comment = self.custom_comment is not None
        if has_reason and has_comment:
            raise ValueError(
                f"У отсутствия спортсмена {self.athlete_id!r} указаны и reason, "
                "и comment одновременно — допустим только один вариант"
            )
        if not has_reason and not has_comment:
            raise ValueError(
                f"У отсутствия спортсмена {self.athlete_id!r} не указана ни "
                "причина (reason), ни свой комментарий (comment)"
            )


@dataclass(frozen=True)
class AttendanceSourceEntry:
    """Подтверждённое (или нет) состояние посещаемости занятия на дату."""

    date: date_
    group_id: str
    confirmed_complete: bool
    absent_athletes: tuple[AttendanceRecordConfig, ...] = field(default_factory=tuple)

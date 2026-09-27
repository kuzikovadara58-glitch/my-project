"""Загрузка, валидация и типизация конфигурации приложения.

Единственное место в проекте, которое читает settings.yaml / groups.yaml /
absence_reasons.yaml / absences.yaml напрямую. Остальной код работает с
объектами `LoadedConfig`, а не с YAML (docs/SPEC.md, раздел 6).

Ничего не работает "тихо" на повреждённой конфигурации: любая проблема —
это `ConfigError` с понятным текстом, а не пропущенное поле или None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_
from datetime import datetime, time as time_
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from journal_automation.config.models import (
    WEEKDAYS,
    AbsenceReason,
    AppConfig,
    Athlete,
    AttendanceRecordConfig,
    AttendanceSourceEntry,
    AutomationSettings,
    Group,
    GoogleDriveSettings,
    PathsSettings,
    PhotosSettings,
    TrainingSchedule,
)
from journal_automation.photos.google_drive_url import (
    InvalidGoogleDriveFolderReference,
    extract_folder_id,
)


class ConfigError(Exception):
    """Конфигурация повреждена, неполна или внутренне противоречива."""


@dataclass(frozen=True)
class LoadedConfig:
    app: AppConfig
    groups: dict[str, Group]
    absence_reasons: dict[str, AbsenceReason]
    attendance: tuple[AttendanceSourceEntry, ...]

    def group(self, group_id: str) -> Group | None:
        return self.groups.get(group_id)

    def attendance_for(self, date: date_, group_id: str) -> AttendanceSourceEntry | None:
        for entry in self.attendance:
            if entry.date == date and entry.group_id == group_id:
                return entry
        return None


class ConfigManager:
    def __init__(self, config_dir: Path) -> None:
        self._config_dir = config_dir

    def load(self) -> LoadedConfig:
        app = self._load_settings()
        absence_reasons = self._load_absence_reasons()
        groups = self._load_groups()
        attendance = self._load_attendance(groups, absence_reasons)
        return LoadedConfig(
            app=app, groups=groups, absence_reasons=absence_reasons, attendance=attendance
        )

    # -- вспомогательное чтение файлов -----------------------------------

    def _read_yaml(self, filename: str) -> Any:
        path = self._config_dir / filename
        if not path.is_file():
            raise ConfigError(f"Не найден файл конфигурации: {path}")
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Файл {path} повреждён и не читается как YAML: {exc}") from exc
        if data is None:
            raise ConfigError(f"Файл {path} пуст")
        return data

    @staticmethod
    def _require(mapping: dict, key: str, context: str) -> Any:
        if not isinstance(mapping, dict) or key not in mapping or mapping[key] in (None, ""):
            raise ConfigError(f"{context}: отсутствует обязательное поле '{key}'")
        return mapping[key]

    @staticmethod
    def _parse_time(value: str, context: str) -> time_:
        try:
            hours, minutes = value.split(":")
            return time_(hour=int(hours), minute=int(minutes))
        except (ValueError, AttributeError) as exc:
            raise ConfigError(
                f"{context}: некорректное время '{value}', ожидается формат ЧЧ:ММ"
            ) from exc

    # -- settings.yaml -----------------------------------------------------

    def _load_settings(self) -> AppConfig:
        data = self._read_yaml("settings.yaml")
        timezone_name = self._require(data, "timezone", "settings.yaml")
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(f"settings.yaml: неизвестный часовой пояс '{timezone_name}'") from exc

        automation_raw = data.get("automation") or {}
        try:
            automation = AutomationSettings(
                fill_after_start_minutes=automation_raw.get("fill_after_start_minutes"),
                fill_after_end_minutes=automation_raw.get("fill_after_end_minutes", 10),
                photo_time_tolerance_before_minutes=automation_raw.get(
                    "photo_time_tolerance_before_minutes", 30
                ),
                photo_time_tolerance_after_minutes=automation_raw.get(
                    "photo_time_tolerance_after_minutes", 120
                ),
            )
        except ValueError as exc:
            raise ConfigError(f"settings.yaml: некорректный раздел automation: {exc}") from exc

        paths_raw = data.get("paths") or {}
        paths = PathsSettings(
            photos=paths_raw.get("photos", "photos"),
            data=paths_raw.get("data", "data"),
            logs=paths_raw.get("logs", "logs"),
        )

        photos = self._load_photos_settings(data.get("photos") or {})

        return AppConfig(timezone=timezone_name, automation=automation, paths=paths, photos=photos)

    def _load_photos_settings(self, photos_raw: dict) -> PhotosSettings:
        drive_raw = photos_raw.get("google_drive") or {}
        folder_url = str(drive_raw.get("folder_url", "") or "")
        folder_id_raw = str(drive_raw.get("folder_id", "") or "")

        # Пустая ссылка/id — ожидаемое состояние, пока пользователь не
        # предоставил постоянную папку (docs/SPEC.md, этап 4, раздел 39).
        # Но если что-то указано — оно должно быть разбираемым уже сейчас,
        # а не падать позже посреди работы планировщика.
        for label, value in (("folder_url", folder_url), ("folder_id", folder_id_raw)):
            if value:
                try:
                    extract_folder_id(value)
                except InvalidGoogleDriveFolderReference as exc:
                    raise ConfigError(
                        f"settings.yaml: photos.google_drive.{label} некорректен: {exc}"
                    ) from exc

        google_drive = GoogleDriveSettings(folder_url=folder_url, folder_id=folder_id_raw)

        try:
            return PhotosSettings(
                source=photos_raw.get("source", "google_drive"),
                google_drive=google_drive,
                allow_drive_timestamp_fallback=bool(
                    photos_raw.get("allow_drive_timestamp_fallback", False)
                ),
                time_tolerance_before_minutes=photos_raw.get("time_tolerance_before_minutes", 15),
                time_tolerance_after_minutes=photos_raw.get("time_tolerance_after_minutes", 120),
                wait_for_photo_until_minutes_after_end=photos_raw.get(
                    "wait_for_photo_until_minutes_after_end", 30
                ),
                recheck_interval_seconds=photos_raw.get("recheck_interval_seconds", 60),
                cache_retention_days=photos_raw.get("cache_retention_days", 7),
            )
        except ValueError as exc:
            raise ConfigError(f"settings.yaml: некорректный раздел photos: {exc}") from exc

    # -- absence_reasons.yaml ----------------------------------------------

    def _load_absence_reasons(self) -> dict[str, AbsenceReason]:
        data = self._read_yaml("absence_reasons.yaml")
        if not isinstance(data, dict) or not data:
            raise ConfigError("absence_reasons.yaml: ожидается непустой словарь ключ->текст")
        reasons: dict[str, AbsenceReason] = {}
        for key, text in data.items():
            if not isinstance(text, str) or not text.strip():
                raise ConfigError(f"absence_reasons.yaml: пустой текст для причины '{key}'")
            reasons[key] = AbsenceReason(key=key, text_masculine=text)
        return reasons

    # -- groups.yaml ---------------------------------------------------------

    def _load_groups(self) -> dict[str, Group]:
        data = self._read_yaml("groups.yaml")
        raw_groups = data.get("groups") if isinstance(data, dict) else None
        if not raw_groups:
            raise ConfigError("groups.yaml: отсутствует непустой список 'groups'")

        groups: dict[str, Group] = {}
        for raw_group in raw_groups:
            group_id = self._require(raw_group, "id", "groups.yaml: группа")
            if group_id in groups:
                raise ConfigError(f"groups.yaml: дублирующийся id группы '{group_id}'")
            context = f"groups.yaml: группа '{group_id}'"
            name = self._require(raw_group, "name", context)
            journal_group_id = raw_group.get("journal_group_id", "") or ""

            schedule = self._load_schedule(raw_group.get("schedule") or [], context)
            athletes = self._load_athletes(raw_group.get("athletes") or [], context)

            groups[group_id] = Group(
                id=group_id,
                name=name,
                journal_group_id=journal_group_id,
                schedule=tuple(schedule),
                athletes=tuple(athletes),
            )

        if not groups:
            raise ConfigError("groups.yaml: список групп не может быть пустым")
        return groups

    def _load_schedule(self, raw_schedule: list, context: str) -> list[TrainingSchedule]:
        schedule: list[TrainingSchedule] = []
        for raw_rule in raw_schedule:
            weekday_name = self._require(raw_rule, "weekday", f"{context}, расписание")
            weekday_key = str(weekday_name).strip().lower()
            if weekday_key not in WEEKDAYS:
                raise ConfigError(
                    f"{context}, расписание: неизвестный день недели '{weekday_name}', "
                    f"допустимо: {', '.join(WEEKDAYS)}"
                )
            start_raw = self._require(raw_rule, "start", f"{context}, расписание")
            end_raw = self._require(raw_rule, "end", f"{context}, расписание")
            start = self._parse_time(start_raw, f"{context}, расписание")
            end = self._parse_time(end_raw, f"{context}, расписание")
            try:
                schedule.append(TrainingSchedule(weekday=WEEKDAYS[weekday_key], start=start, end=end))
            except ValueError as exc:
                raise ConfigError(f"{context}, расписание: {exc}") from exc
        if not schedule:
            raise ConfigError(f"{context}: расписание не может быть пустым")
        return schedule

    def _load_athletes(self, raw_athletes: list, context: str) -> list[Athlete]:
        athletes: list[Athlete] = []
        seen_ids: set[str] = set()
        for raw_athlete in raw_athletes:
            athlete_id = self._require(raw_athlete, "id", f"{context}, спортсмен")
            if athlete_id in seen_ids:
                raise ConfigError(f"{context}: дублирующийся id спортсмена '{athlete_id}'")
            seen_ids.add(athlete_id)
            full_name = self._require(raw_athlete, "full_name", f"{context}, спортсмен '{athlete_id}'")
            gender = raw_athlete.get("gender")
            if gender is not None and gender not in ("m", "f"):
                raise ConfigError(
                    f"{context}, спортсмен '{athlete_id}': gender должен быть 'm', 'f' или отсутствовать"
                )
            athletes.append(Athlete(id=athlete_id, full_name=full_name, gender=gender))
        if not athletes:
            raise ConfigError(f"{context}: список спортсменов не может быть пустым")
        return athletes

    # -- absences.yaml ---------------------------------------------------------

    def _load_attendance(
        self, groups: dict[str, Group], absence_reasons: dict[str, AbsenceReason]
    ) -> tuple[AttendanceSourceEntry, ...]:
        path = self._config_dir / "absences.yaml"
        if not path.is_file():
            return ()
        data = self._read_yaml("absences.yaml")
        raw_entries = data.get("attendance") or [] if isinstance(data, dict) else []

        entries: list[AttendanceSourceEntry] = []
        seen_keys: set[tuple[date_, str]] = set()
        for raw_entry in raw_entries:
            date_raw = self._require(raw_entry, "date", "absences.yaml: запись")
            group_id = self._require(raw_entry, "group_id", "absences.yaml: запись")
            context = f"absences.yaml: {date_raw} / {group_id}"

            try:
                entry_date = datetime.strptime(str(date_raw), "%Y-%m-%d").date()
            except ValueError as exc:
                raise ConfigError(f"{context}: некорректная дата, ожидается ГГГГ-ММ-ДД") from exc

            if (entry_date, group_id) in seen_keys:
                raise ConfigError(f"{context}: дублирующаяся запись посещаемости")
            seen_keys.add((entry_date, group_id))

            group = groups.get(group_id)
            if group is None:
                raise ConfigError(f"{context}: неизвестная группа '{group_id}'")

            confirmed_complete = bool(raw_entry.get("confirmed_complete", False))
            raw_athletes = raw_entry.get("athletes") or []

            absent: list[AttendanceRecordConfig] = []
            seen_athlete_ids: set[str] = set()
            for raw_absent in raw_athletes:
                athlete_id = self._require(raw_absent, "athlete_id", f"{context}: отсутствующий")
                if athlete_id in seen_athlete_ids:
                    raise ConfigError(f"{context}: спортсмен '{athlete_id}' указан дважды")
                seen_athlete_ids.add(athlete_id)

                if group.athlete_by_id(athlete_id) is None:
                    raise ConfigError(
                        f"{context}: спортсмен '{athlete_id}' не найден в составе группы '{group_id}'"
                    )

                reason_key = raw_absent.get("reason")
                custom_comment = raw_absent.get("comment")
                if reason_key is not None and reason_key not in absence_reasons:
                    raise ConfigError(
                        f"{context}: неизвестный ключ причины '{reason_key}' у спортсмена '{athlete_id}'"
                    )
                try:
                    absent.append(
                        AttendanceRecordConfig(
                            athlete_id=athlete_id,
                            reason_key=reason_key,
                            custom_comment=custom_comment,
                        )
                    )
                except ValueError as exc:
                    raise ConfigError(f"{context}: {exc}") from exc

            entries.append(
                AttendanceSourceEntry(
                    date=entry_date,
                    group_id=group_id,
                    confirmed_complete=confirmed_complete,
                    absent_athletes=tuple(absent),
                )
            )

        return tuple(entries)

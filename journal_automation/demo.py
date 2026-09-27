"""Изолированный контекст для `python main.py --demo` (этап 3, раздел 13;

этап 4 добавил `photo_mode` — раздел 30-33). Не читает config/ и не пишет в
реальную пользовательскую историю или реальный Google Drive — всё
синтетическое и живёт во временном каталоге, который не переживает
завершение процесса.
"""

from __future__ import annotations

import tempfile
from datetime import timedelta
from pathlib import Path

from journal_automation.app import AppContext
from journal_automation.config.manager import LoadedConfig
from journal_automation.config.models import (
    AppConfig,
    Athlete,
    AutomationSettings,
    GoogleDriveSettings,
    Group,
    PathsSettings,
    PhotosSettings,
    TrainingSchedule,
)
from journal_automation.paths import AppPaths
from journal_automation.photos.cache import PhotoCache
from journal_automation.photos.fake_source import DemoPhotoMode, FakeGoogleDrivePhotoSource
from journal_automation.photos.service import PhotoService
from journal_automation.services.history_manager import HistoryManager
from journal_automation.services.time_service import TimeService
from journal_automation.services.training_service import TrainingService

DEMO_TIMEZONE = "Europe/Moscow"

# Через сколько секунд от запуска наступает демо-занятие и сколько условно
# "длится" оно (docs/PLAN.md, критерий готовности этапов 3-4).
_SESSION_OFFSET_SECONDS = 5.0
_SESSION_DURATION_SECONDS = 2.0


def build_demo_app_context(photo_mode: DemoPhotoMode = "success") -> AppContext:
    tmp_root = Path(tempfile.mkdtemp(prefix="journal-automation-demo-"))
    paths = AppPaths(user_data_root=tmp_root, config_dir=tmp_root / "config")

    time_service = TimeService(DEMO_TIMEZONE)  # реальные часы, не подменяются
    now = time_service.now()
    today = now.date()

    start_dt = now + timedelta(seconds=_SESSION_OFFSET_SECONDS)
    end_dt = start_dt + timedelta(seconds=_SESSION_DURATION_SECONDS)
    schedule_rule = TrainingSchedule(weekday=today.weekday(), start=start_dt.time(), end=end_dt.time())

    demo_group = Group(
        id="demo_group",
        name="Демо-группа",
        journal_group_id="",
        schedule=(schedule_rule,),
        athletes=(Athlete(id="demo_athlete", full_name="Демо Спортсмен", gender="m"),),
    )

    # fill_after_start_minutes=0 даёт секундную точность запуска обработки —
    # занятие считается "готовым" сразу в момент своего начала.
    automation = AutomationSettings(fill_after_start_minutes=0, fill_after_end_minutes=10)

    # wait_for_photo_until_minutes_after_end=0 и короткий recheck — иначе
    # демонстрация перехода WAITING_FOR_PHOTO -> NEEDS_ATTENTION заняла бы
    # реальные десятки минут (photos.wait_for_photo_until_minutes_after_end
    # измеряется в минутах, docs/SPEC.md, этап 4, раздел 28).
    photos_settings = PhotosSettings(
        source="google_drive",
        google_drive=GoogleDriveSettings(folder_url="", folder_id=""),
        time_tolerance_before_minutes=15,
        time_tolerance_after_minutes=120,
        wait_for_photo_until_minutes_after_end=0,
        recheck_interval_seconds=2,
    )

    app_config = AppConfig(
        timezone=DEMO_TIMEZONE, automation=automation, paths=PathsSettings(), photos=photos_settings
    )
    config = LoadedConfig(
        app=app_config,
        groups={"demo_group": demo_group},
        absence_reasons={},
        attendance=(),
    )

    history = HistoryManager(tmp_root / "history.json")
    training_service = TrainingService(config, time_service, history)

    cache = PhotoCache(tmp_root / "cache" / "photos")
    photo_source = FakeGoogleDrivePhotoSource(mode=photo_mode, cache=cache)
    photo_service = PhotoService(photo_source, photos_settings, time_service)

    return AppContext(
        paths=paths,
        config=config,
        time_service=time_service,
        history=history,
        training_service=training_service,
        photo_service=photo_service,
    )

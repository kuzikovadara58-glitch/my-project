"""Сборка готовых слоёв в единый объект — для CLI-демо, GUI и планировщика.

Не содержит собственной логики — только соединяет ConfigManager, AppPaths,
TimeService, HistoryManager, TrainingService и (если настроено) PhotoService
так, как описано в docs/ARCHITECTURE.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from journal_automation.config.manager import ConfigManager, LoadedConfig
from journal_automation.paths import AppPaths
from journal_automation.photos.bootstrap import build_photo_service
from journal_automation.photos.service import PhotoService
from journal_automation.services.history_manager import HistoryManager
from journal_automation.services.time_service import TimeService
from journal_automation.services.training_service import TrainingService


@dataclass
class AppContext:
    """Всё, что нужно GUI/CLI для работы с одним и тем же набором данных."""

    paths: AppPaths
    config: LoadedConfig
    time_service: TimeService
    history: HistoryManager
    training_service: TrainingService
    # None, пока папка Google Drive не настроена (docs/SPEC.md, этап 4,
    # раздел 39) — планировщик тогда работает без проверки фото, как на этапе 3.
    photo_service: PhotoService | None = None


def load_app_config(paths: AppPaths | None = None) -> LoadedConfig:
    paths = paths or AppPaths.resolve()
    return ConfigManager(paths.config_dir).load()


def build_app_context(paths: AppPaths | None = None) -> AppContext:
    paths = paths or AppPaths.resolve()
    config = ConfigManager(paths.config_dir).load()
    time_service = TimeService(config.app.timezone)
    history_path = paths.resolve_configured_path(config.app.paths.data) / "history.json"
    history = HistoryManager(history_path)
    training_service = TrainingService(config, time_service, history)
    photo_service = build_photo_service(config, paths, time_service)
    return AppContext(
        paths=paths,
        config=config,
        time_service=time_service,
        history=history,
        training_service=training_service,
        photo_service=photo_service,
    )

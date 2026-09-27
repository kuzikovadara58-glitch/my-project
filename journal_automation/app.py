"""Сборка готовых слоёв в единый объект — для CLI-демо и будущего GUI/планировщика.

Не содержит собственной логики — только соединяет ConfigManager, AppPaths,
TimeService, HistoryManager и TrainingService так, как описано в
docs/ARCHITECTURE.md.
"""

from __future__ import annotations

from journal_automation.config.manager import ConfigManager, LoadedConfig
from journal_automation.paths import AppPaths
from journal_automation.services.history_manager import HistoryManager
from journal_automation.services.time_service import TimeService
from journal_automation.services.training_service import TrainingService


def load_app_config(paths: AppPaths | None = None) -> LoadedConfig:
    paths = paths or AppPaths.resolve()
    return ConfigManager(paths.config_dir).load()


def build_training_service(
    paths: AppPaths | None = None,
) -> tuple[LoadedConfig, TrainingService, HistoryManager]:
    paths = paths or AppPaths.resolve()
    config = ConfigManager(paths.config_dir).load()
    time_service = TimeService(config.app.timezone)
    history_path = paths.resolve_configured_path(config.app.paths.data) / "history.json"
    history = HistoryManager(history_path)
    return config, TrainingService(config, time_service, history), history

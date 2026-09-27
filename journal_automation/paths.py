"""Единая точка разрешения путей приложения.

Требование (docs/SPEC.md, раздел 11; CLAUDE.md, правило 13): пользовательские
данные (БД, история, логи, фото) хранятся отдельно от каталога установленной
программы и не зависят от того, где именно на диске лежит `C:\\Users\\...` —
поэтому конкретный путь берётся у ОС через `platformdirs`, а не собирается
вручную через `Path(__file__)` в разных местах проекта.

Всё завязанное на файловую систему в остальном коде должно получать пути
только отсюда, а не составлять их самостоятельно.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import platformdirs

APP_NAME = "JournalAutomation"
APP_AUTHOR = "JournalAutomation"

_ENV_APP_DATA_DIR = "JOURNAL_APP_DATA_DIR"
_ENV_CONFIG_DIR = "JOURNAL_CONFIG_DIR"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _source_repo_root() -> Path:
    # journal_automation/paths.py -> journal_automation/ -> <repo root>
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class AppPaths:
    """Разрешает пути приложения независимо от способа запуска.

    - `user_data_root` — приватные данные пользователя (история, БД, логи,
      фото по умолчанию). По умолчанию — системный каталог данных
      пользователя (`platformdirs`), переопределяется `JOURNAL_APP_DATA_DIR`
      (используется в тестах и для явного выбора каталога разработчиком).
    - `config_dir` — каталог с settings.yaml/groups.yaml/absences.yaml/
      absence_reasons.yaml. По умолчанию — `config/` рядом с исходниками
      (при запуске из исходников) или рядом с исполняемым файлом (после
      сборки PyInstaller), переопределяется `JOURNAL_CONFIG_DIR` — так
      реальный, приватный конфиг конкретного тренера может физически лежать
      вне репозитория.
    """

    user_data_root: Path
    config_dir: Path

    @classmethod
    def resolve(cls) -> "AppPaths":
        data_override = os.environ.get(_ENV_APP_DATA_DIR)
        user_data_root = (
            Path(data_override)
            if data_override
            else Path(platformdirs.user_data_dir(APP_NAME, APP_AUTHOR))
        )

        config_override = os.environ.get(_ENV_CONFIG_DIR)
        if config_override:
            config_dir = Path(config_override)
        elif _is_frozen():
            config_dir = Path(sys.executable).resolve().parent / "config"
        else:
            config_dir = _source_repo_root() / "config"

        return cls(user_data_root=user_data_root, config_dir=config_dir)

    def resolve_configured_path(self, configured_value: str) -> Path:
        """Резолвит значение из settings.yaml (`paths.*`).

        Абсолютный путь используется как есть (осознанный выбор
        пользователя, например сетевой диск для фото). Относительный путь
        трактуется как подпапка пользовательского каталога данных, а не
        текущей рабочей директории процесса.
        """

        candidate = Path(configured_value)
        if candidate.is_absolute():
            return candidate
        return self.user_data_root / candidate

    def ensure_directories(self, *extra: Path) -> None:
        self.user_data_root.mkdir(parents=True, exist_ok=True)
        for path in extra:
            path.mkdir(parents=True, exist_ok=True)

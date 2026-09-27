from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import keyring
import pytest
import yaml
from keyring.backend import KeyringBackend
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Единственный на процесс экземпляр QApplication для Qt-тестов.

    Не показывает никаких окон — нужен только для того, чтобы сигналы/слоты
    и QThread работали (docs/PLAN.md, этап 3, раздел 26: тестируем
    Controller/сигнальную интеграцию отдельно от визуального рендеринга).
    """

    app = QApplication.instance() or QApplication([])
    return app


def pump_events(app: QApplication, predicate, timeout: float = 5.0) -> bool:
    """Крутит цикл событий Qt, пока `predicate()` не станет True или не выйдет

    время — так фоновый QThread успевает доставить сигналы в тестовый процесс
    без реального `app.exec()`.
    """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()

DEFAULT_SETTINGS: dict[str, Any] = {
    "timezone": "Europe/Moscow",
    "automation": {
        "fill_after_start_minutes": None,
        "fill_after_end_minutes": 10,
        "photo_time_tolerance_before_minutes": 30,
        "photo_time_tolerance_after_minutes": 120,
    },
    "paths": {"photos": "photos", "data": "data", "logs": "logs"},
}

DEFAULT_GROUPS: dict[str, Any] = {
    "groups": [
        {
            "id": "g1",
            "name": "Тестовая группа",
            "journal_group_id": "",
            "schedule": [{"weekday": "monday", "start": "18:00", "end": "19:30"}],
            "athletes": [
                {"id": "a1", "full_name": "Спортсмен Один", "gender": "m"},
                {"id": "a2", "full_name": "Спортсменка Два", "gender": "f"},
            ],
        }
    ]
}

DEFAULT_REASONS: dict[str, str] = {
    "family": "отпросился с тренировки по семейным обстоятельствам",
    "health": "отпросился с тренировки в связи с плохим самочувствием",
}


class InMemoryKeyring(KeyringBackend):
    """Тестовый backend для keyring — не трогает реальное хранилище ОС."""

    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self._store.pop((service, username), None)


@pytest.fixture(autouse=True)
def fake_keyring() -> InMemoryKeyring:
    backend = InMemoryKeyring()
    keyring.set_keyring(backend)
    return backend


def write_yaml(path: Path, data: Any) -> None:
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


@pytest.fixture
def config_dir_factory(tmp_path: Path):
    def _make(
        settings: dict | None = None,
        groups: dict | None = None,
        absence_reasons: dict | None = None,
        absences: dict | None = None,
    ) -> Path:
        config_dir = tmp_path / f"config_{len(list(tmp_path.iterdir()))}"
        config_dir.mkdir()
        write_yaml(config_dir / "settings.yaml", settings if settings is not None else DEFAULT_SETTINGS)
        write_yaml(config_dir / "groups.yaml", groups if groups is not None else DEFAULT_GROUPS)
        write_yaml(
            config_dir / "absence_reasons.yaml",
            absence_reasons if absence_reasons is not None else DEFAULT_REASONS,
        )
        if absences is not None:
            write_yaml(config_dir / "absences.yaml", absences)
        return config_dir

    return _make

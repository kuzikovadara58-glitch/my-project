"""Опциональный интеграционный тест с РЕАЛЬНЫМ Google Drive API.

docs/SPEC.md, этап 4, раздел 35: не входит в обычный `pytest` (см.
`pytest.ini`: `addopts = -m "not google_drive"`). Запускается только вручную,
когда настроены реальные Google-credentials и тестовая папка:

    pytest -m google_drive \
        --gdrive-credentials path/to/credentials.json \
        --gdrive-token path/to/token.json \
        --gdrive-folder <folder_id_или_ссылка>

Пока эти данные не предоставлены — тест пропускается с понятным сообщением,
а не падает и не блокирует обычный прогон тестов.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.google_drive


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def test_real_drive_folder_listing_smoke():
    credentials_path = _env_path("JOURNAL_TEST_GDRIVE_CREDENTIALS")
    token_path = _env_path("JOURNAL_TEST_GDRIVE_TOKEN")
    folder_reference = os.environ.get("JOURNAL_TEST_GDRIVE_FOLDER")

    if not (credentials_path and token_path and folder_reference):
        pytest.skip(
            "Реальные Google Drive credentials/папка не настроены — задайте "
            "JOURNAL_TEST_GDRIVE_CREDENTIALS, JOURNAL_TEST_GDRIVE_TOKEN, "
            "JOURNAL_TEST_GDRIVE_FOLDER, чтобы запустить этот тест вручную."
        )

    from journal_automation.photos.google_drive_auth import create_drive_service
    from journal_automation.photos.google_drive_source import GoogleDrivePhotoSource
    from journal_automation.photos.google_drive_url import extract_folder_id
    from journal_automation.photos.cache import PhotoCache

    tmp_cache = Path.cwd() / ".gdrive_integration_cache"
    service = create_drive_service(credentials_path, token_path)
    source = GoogleDrivePhotoSource(service, extract_folder_id(folder_reference), PhotoCache(tmp_cache))

    # Реальная папка может быть пустой — тест только проверяет, что запрос
    # к API не падает и возвращает список без исключений.
    from journal_automation.domain.session import TrainingSession
    from journal_automation.domain.states import AutomationState, TrainingDomainState
    from journal_automation.config.models import Group
    from datetime import date, time

    dummy_session = TrainingSession(
        session_id="integration-test",
        date=date.today(),
        group=Group(id="integration", name="integration", journal_group_id="", schedule=(), athletes=()),
        start_time=time(0, 0),
        end_time=time(23, 59),
        domain_state=TrainingDomainState.PLANNED,
        automation_state=AutomationState.PENDING,
    )

    candidates = source.list_candidates(dummy_session)
    assert isinstance(candidates, list)

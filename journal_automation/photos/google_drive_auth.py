"""OAuth-авторизация в Google Drive для desktop-приложения одного пользователя.

docs/SPEC.md, этап 4, разделы 2-3: пароль от Google-аккаунта приложение
никогда не получает — только OAuth 2.0 через официальный "installed app"
flow с локальным loopback-сервером (`InstalledAppFlow.run_local_server`),
это рекомендованный Google механизм именно для десктопных приложений одного
пользователя (в отличие от service account, который создан для доступа
без участия человека, или web-flow с публичным redirect URI, ненужного
здесь).

Файлы:
  - `credentials.json` — OAuth client secret, скачивается пользователем из
    Google Cloud Console (тип "Desktop app"). НЕ создаётся этим кодом и не
    коммитится (docs/SPEC.md, раздел 36).
  - `token.json` — access/refresh token, создаётся автоматически после
    первого успешного входа, хранится локально, не коммитится.

Это НЕ вызывается автоматически при обычном запуске приложения без
настроенной папки — только когда `GoogleDrivePhotoSource` реально
понадобится (см. journal_automation/app.py), чтобы не открывать окно входа
в браузере без необходимости.
"""

from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from journal_automation.photos.source import PhotoSourceUnavailableError

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


class GoogleDriveSetupError(PhotoSourceUnavailableError):
    """credentials.json отсутствует или OAuth-вход не пройден — нужна ручная

    настройка пользователем (см. README.md, раздел "Google Drive — фото").
    """


def load_credentials(credentials_path: Path, token_path: Path, scopes: list[str] = SCOPES) -> Credentials:
    creds: Credentials | None = None
    if token_path.is_file():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:  # noqa: BLE001 — любая причина отказа = нужен новый вход
            raise GoogleDriveSetupError(
                f"Не удалось обновить доступ к Google Drive автоматически ({exc}). "
                "Нужно войти заново."
            ) from exc
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    if not credentials_path.is_file():
        raise GoogleDriveSetupError(
            f"Не найден файл {credentials_path.name} — скачайте OAuth client "
            "secret (тип 'Desktop app') в Google Cloud Console и укажите путь "
            "к нему (см. README.md, раздел 'Google Drive — фото')."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), scopes)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def create_drive_service(credentials_path: Path, token_path: Path):
    creds = load_credentials(credentials_path, token_path)
    return build("drive", "v3", credentials=creds, cache_discovery=False)

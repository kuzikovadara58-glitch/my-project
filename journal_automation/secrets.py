"""Хранение секретов конечного пользователя (логин/пароль от журнала).

По умолчанию — системное хранилище учётных данных ОС через `keyring`
(на Windows — Credential Manager). `.env` — только для локальной разработки
и только если явно включён переменной `JOURNAL_ALLOW_DOTENV_SECRETS=1`
(docs/SPEC.md, раздел 1; CLAUDE.md, правило 12).

Секреты никогда не логируются и не печатаются этим модулем.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import keyring

_SERVICE_NAME = "journal-automation"
_LOGIN_USERNAME_KEY = "journal-login"  # ключ, под которым хранится логин
_PASSWORD_USERNAME_KEY = "journal-password"

_ENV_ALLOW_DOTENV = "JOURNAL_ALLOW_DOTENV_SECRETS"


class CredentialsError(Exception):
    """Секреты не найдены ни в системном хранилище, ни (если разрешено) в .env."""


@dataclass(frozen=True)
class JournalCredentials:
    url: str
    login: str
    password: str


def save_journal_credentials(login: str, password: str) -> None:
    keyring.set_password(_SERVICE_NAME, _LOGIN_USERNAME_KEY, login)
    keyring.set_password(_SERVICE_NAME, _PASSWORD_USERNAME_KEY, password)


def _load_from_keyring() -> tuple[str, str] | None:
    login = keyring.get_password(_SERVICE_NAME, _LOGIN_USERNAME_KEY)
    password = keyring.get_password(_SERVICE_NAME, _PASSWORD_USERNAME_KEY)
    if login and password:
        return login, password
    return None


def _load_from_dotenv() -> tuple[str, str] | None:
    login = os.environ.get("JOURNAL_LOGIN")
    password = os.environ.get("JOURNAL_PASSWORD")
    if login and password:
        return login, password
    return None


def load_journal_credentials(journal_url: str) -> JournalCredentials:
    """Читает логин/пароль. Не принимает и не выводит пароль в открытом виде.

    `journal_url` передаётся отдельно (не секрет), обычно из конфигурации —
    см. docs/ARCHITECTURE.md.
    """

    from_keyring = _load_from_keyring()
    if from_keyring is not None:
        login, password = from_keyring
        return JournalCredentials(url=journal_url, login=login, password=password)

    if os.environ.get(_ENV_ALLOW_DOTENV) == "1":
        from_dotenv = _load_from_dotenv()
        if from_dotenv is not None:
            login, password = from_dotenv
            return JournalCredentials(url=journal_url, login=login, password=password)

    raise CredentialsError(
        "Не найдены учётные данные журнала. Сохраните их через "
        "journal_automation.secrets.save_journal_credentials(login, password) "
        "(системное хранилище ОС), либо для разработки заполните .env "
        "(см. .env.example) и установите JOURNAL_ALLOW_DOTENV_SECRETS=1."
    )

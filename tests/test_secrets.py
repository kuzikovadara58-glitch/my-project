from __future__ import annotations

import pytest

from journal_automation.secrets import (
    CredentialsError,
    load_journal_credentials,
    save_journal_credentials,
)


def test_raises_when_nothing_configured(monkeypatch):
    monkeypatch.delenv("JOURNAL_ALLOW_DOTENV_SECRETS", raising=False)
    monkeypatch.delenv("JOURNAL_LOGIN", raising=False)
    monkeypatch.delenv("JOURNAL_PASSWORD", raising=False)

    with pytest.raises(CredentialsError):
        load_journal_credentials("https://example.invalid")


def test_loads_from_keyring(fake_keyring):
    save_journal_credentials("trainer", "s3cret")

    creds = load_journal_credentials("https://example.invalid")

    assert creds.login == "trainer"
    assert creds.password == "s3cret"
    assert creds.url == "https://example.invalid"


def test_dotenv_fallback_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("JOURNAL_LOGIN", "trainer")
    monkeypatch.setenv("JOURNAL_PASSWORD", "s3cret")
    monkeypatch.delenv("JOURNAL_ALLOW_DOTENV_SECRETS", raising=False)

    with pytest.raises(CredentialsError):
        load_journal_credentials("https://example.invalid")

    monkeypatch.setenv("JOURNAL_ALLOW_DOTENV_SECRETS", "1")
    creds = load_journal_credentials("https://example.invalid")
    assert creds.login == "trainer"


def test_keyring_takes_priority_over_dotenv(monkeypatch, fake_keyring):
    save_journal_credentials("from-keyring", "keyring-pass")
    monkeypatch.setenv("JOURNAL_ALLOW_DOTENV_SECRETS", "1")
    monkeypatch.setenv("JOURNAL_LOGIN", "from-dotenv")
    monkeypatch.setenv("JOURNAL_PASSWORD", "dotenv-pass")

    creds = load_journal_credentials("https://example.invalid")

    assert creds.login == "from-keyring"

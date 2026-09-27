from __future__ import annotations

from datetime import date

import pytest

from journal_automation.config.manager import ConfigError, ConfigManager


def test_valid_config_loads(config_dir_factory):
    config_dir = config_dir_factory()
    loaded = ConfigManager(config_dir).load()

    assert loaded.app.timezone == "Europe/Moscow"
    assert set(loaded.groups) == {"g1"}
    group = loaded.group("g1")
    assert group is not None
    assert {a.id for a in group.athletes} == {"a1", "a2"}
    assert "family" in loaded.absence_reasons


def test_missing_config_dir_raises(tmp_path):
    with pytest.raises(ConfigError, match="Не найден файл конфигурации"):
        ConfigManager(tmp_path / "does-not-exist").load()


def test_broken_yaml_raises(config_dir_factory):
    config_dir = config_dir_factory()
    (config_dir / "settings.yaml").write_text("timezone: [unclosed", encoding="utf-8")

    with pytest.raises(ConfigError, match="повреждён"):
        ConfigManager(config_dir).load()


def test_missing_required_field_raises(config_dir_factory):
    groups = {
        "groups": [
            {
                "id": "g1",
                # "name" отсутствует намеренно
                "schedule": [{"weekday": "monday", "start": "18:00", "end": "19:00"}],
                "athletes": [{"id": "a1", "full_name": "Спортсмен"}],
            }
        ]
    }
    config_dir = config_dir_factory(groups=groups)

    with pytest.raises(ConfigError, match="name"):
        ConfigManager(config_dir).load()


def test_invalid_time_format_raises(config_dir_factory):
    groups = {
        "groups": [
            {
                "id": "g1",
                "name": "Группа",
                "schedule": [{"weekday": "monday", "start": "не время", "end": "19:00"}],
                "athletes": [{"id": "a1", "full_name": "Спортсмен"}],
            }
        ]
    }
    config_dir = config_dir_factory(groups=groups)

    with pytest.raises(ConfigError, match="время"):
        ConfigManager(config_dir).load()


def test_unknown_weekday_raises(config_dir_factory):
    groups = {
        "groups": [
            {
                "id": "g1",
                "name": "Группа",
                "schedule": [{"weekday": "недопонедельник", "start": "18:00", "end": "19:00"}],
                "athletes": [{"id": "a1", "full_name": "Спортсмен"}],
            }
        ]
    }
    config_dir = config_dir_factory(groups=groups)

    with pytest.raises(ConfigError, match="день недели"):
        ConfigManager(config_dir).load()


def test_duplicate_group_id_raises(config_dir_factory):
    one_group = {
        "id": "g1",
        "name": "Группа",
        "schedule": [{"weekday": "monday", "start": "18:00", "end": "19:00"}],
        "athletes": [{"id": "a1", "full_name": "Спортсмен"}],
    }
    groups = {"groups": [one_group, dict(one_group)]}
    config_dir = config_dir_factory(groups=groups)

    with pytest.raises(ConfigError, match="дублирующийся id группы"):
        ConfigManager(config_dir).load()


def test_unknown_athlete_in_absences_raises(config_dir_factory):
    absences = {
        "attendance": [
            {
                "date": "2026-09-28",
                "group_id": "g1",
                "confirmed_complete": True,
                "athletes": [{"athlete_id": "not-in-group", "reason": "family"}],
            }
        ]
    }
    config_dir = config_dir_factory(absences=absences)

    with pytest.raises(ConfigError, match="не найден в составе группы"):
        ConfigManager(config_dir).load()


def test_unknown_reason_key_in_absences_raises(config_dir_factory):
    absences = {
        "attendance": [
            {
                "date": "2026-09-28",
                "group_id": "g1",
                "confirmed_complete": True,
                "athletes": [{"athlete_id": "a1", "reason": "нет-такой-причины"}],
            }
        ]
    }
    config_dir = config_dir_factory(absences=absences)

    with pytest.raises(ConfigError, match="неизвестный ключ причины"):
        ConfigManager(config_dir).load()


def test_reason_and_comment_together_raises(config_dir_factory):
    absences = {
        "attendance": [
            {
                "date": "2026-09-28",
                "group_id": "g1",
                "confirmed_complete": True,
                "athletes": [
                    {"athlete_id": "a1", "reason": "family", "comment": "свой текст"}
                ],
            }
        ]
    }
    config_dir = config_dir_factory(absences=absences)

    with pytest.raises(ConfigError):
        ConfigManager(config_dir).load()


def test_confirmed_complete_with_empty_athletes_is_valid(config_dir_factory):
    absences = {
        "attendance": [
            {"date": "2026-09-28", "group_id": "g1", "confirmed_complete": True, "athletes": []}
        ]
    }
    config_dir = config_dir_factory(absences=absences)

    loaded = ConfigManager(config_dir).load()
    entry = loaded.attendance_for(date(2026, 9, 28), "g1")
    assert entry is not None
    assert entry.confirmed_complete is True
    assert entry.absent_athletes == ()

from __future__ import annotations

from journal_automation.paths import AppPaths


def test_resolve_uses_env_overrides(monkeypatch, tmp_path):
    data_root = tmp_path / "data-root"
    config_root = tmp_path / "config-root"
    monkeypatch.setenv("JOURNAL_APP_DATA_DIR", str(data_root))
    monkeypatch.setenv("JOURNAL_CONFIG_DIR", str(config_root))

    paths = AppPaths.resolve()

    assert paths.user_data_root == data_root
    assert paths.config_dir == config_root


def test_relative_configured_path_is_under_user_data_root(tmp_path):
    paths = AppPaths(user_data_root=tmp_path / "root", config_dir=tmp_path / "config")

    resolved = paths.resolve_configured_path("photos")

    assert resolved == tmp_path / "root" / "photos"


def test_absolute_configured_path_used_as_is(tmp_path):
    paths = AppPaths(user_data_root=tmp_path / "root", config_dir=tmp_path / "config")
    absolute = tmp_path / "elsewhere" / "photos"

    resolved = paths.resolve_configured_path(str(absolute))

    assert resolved == absolute


def test_ensure_directories_creates_paths(tmp_path):
    paths = AppPaths(user_data_root=tmp_path / "root", config_dir=tmp_path / "config")
    extra = paths.user_data_root / "sub"

    paths.ensure_directories(extra)

    assert paths.user_data_root.is_dir()
    assert extra.is_dir()

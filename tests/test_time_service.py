from __future__ import annotations

from datetime import datetime, timezone

import pytest

from journal_automation.services.time_service import TimeService


def test_now_converts_utc_clock_to_configured_timezone():
    # 2026-06-15 12:00 UTC -> Europe/Moscow (UTC+3 летом) = 15:00
    fixed_utc = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    service = TimeService("Europe/Moscow", clock=lambda: fixed_utc)

    now = service.now()

    assert now.tzinfo is not None
    assert now.utcoffset().total_seconds() == 3 * 3600
    assert now.hour == 15


def test_today_uses_configured_timezone_not_utc_date():
    # 23:30 UTC 2026-06-15 -> 02:30 2026-06-16 в Москве: другая календарная дата.
    fixed_utc = datetime(2026, 6, 15, 23, 30, tzinfo=timezone.utc)
    service = TimeService("Europe/Moscow", clock=lambda: fixed_utc)

    assert service.today().isoformat() == "2026-06-16"


def test_naive_clock_raises():
    naive = datetime(2026, 6, 15, 12, 0)
    service = TimeService("Europe/Moscow", clock=lambda: naive)

    with pytest.raises(ValueError, match="naive"):
        service.now()


def test_result_independent_of_which_timezone_configured():
    fixed_utc = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)

    moscow = TimeService("Europe/Moscow", clock=lambda: fixed_utc).now()
    tokyo = TimeService("Asia/Tokyo", clock=lambda: fixed_utc).now()

    # Один и тот же момент времени, разные настроенные часовые пояса —
    # разное локальное время, но один и тот же momento (UTC-эквивалент).
    assert moscow.hour != tokyo.hour
    assert moscow.astimezone(timezone.utc) == tokyo.astimezone(timezone.utc)

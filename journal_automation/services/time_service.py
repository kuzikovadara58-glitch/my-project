"""Работа со временем: только timezone-aware datetime (docs/SPEC.md, раздел 7).

Часовой пояс берётся из конфигурации (settings.yaml), а не из локальных
настроек машины, на которой запущено приложение — иначе расчёты будут
зависеть от часового пояса разработчика/сервера (docs/SPEC.md, требование
"расчёты не зависят от локального timezone разработчика").
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date as date_
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


class TimeService:
    def __init__(self, timezone_name: str, clock: Callable[[], datetime] | None = None) -> None:
        self._tz = ZoneInfo(timezone_name)
        # `clock` внедряется в тестах, чтобы не зависеть от реального
        # системного времени при проверке бизнес-логики.
        self._clock = clock or _default_clock

    @property
    def timezone(self) -> ZoneInfo:
        return self._tz

    def now(self) -> datetime:
        raw = self._clock()
        if raw.tzinfo is None:
            raise ValueError(
                "TimeService получил naive datetime от clock() — "
                "бизнес-логика не должна работать с naive datetime"
            )
        return raw.astimezone(self._tz)

    def today(self) -> date_:
        return self.now().date()

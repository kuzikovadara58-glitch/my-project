"""Расчёт момента заполнения занятия (docs/SPEC.md, раздел 4; этап 2 отложил

эту логику до планировщика — см. docs/PLAN.md, "Этап 2. Данные").
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from journal_automation.config.models import AutomationSettings
from journal_automation.domain.session import TrainingSession


def compute_fill_time(
    session: TrainingSession, automation: AutomationSettings, tz: ZoneInfo
) -> datetime:
    """Момент, когда занятие становится готово к обработке.

    Если задан `fill_after_start_minutes` — используется он (смещение от
    начала); иначе — `fill_after_end_minutes` (смещение от окончания). Ровно
    один из режимов действует одновременно (journal_automation/config/models.py).
    """

    if automation.fill_after_start_minutes is not None:
        return session.start_datetime(tz) + timedelta(minutes=automation.fill_after_start_minutes)
    return session.end_datetime(tz) + timedelta(minutes=automation.fill_after_end_minutes)

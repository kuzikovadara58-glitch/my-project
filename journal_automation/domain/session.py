"""Занятие (TrainingSession) — конкретный экземпляр тренировки на дату."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_
from datetime import datetime, time as time_

from journal_automation.config.models import Group
from journal_automation.domain.states import AutomationState, TrainingDomainState


def build_session_id(date: date_, group_id: str, start_time: time_) -> str:
    """Стабильный уникальный идентификатор занятия.

    Формат `ГГГГ-ММ-ДД:group_id:ЧЧ:ММ` — устойчив к повторным запускам
    (используется историей, защитой от дублей, планировщиком и GUI),
    docs/SPEC.md, раздел 8.
    """

    return f"{date.isoformat()}:{group_id}:{start_time.strftime('%H:%M')}"


@dataclass(frozen=True)
class TrainingSession:
    session_id: str
    date: date_
    group: Group
    start_time: time_
    end_time: time_
    domain_state: TrainingDomainState
    automation_state: AutomationState

    @property
    def group_id(self) -> str:
        return self.group.id

    def start_datetime(self, tz) -> datetime:
        return datetime.combine(self.date, self.start_time, tzinfo=tz)

    def end_datetime(self, tz) -> datetime:
        return datetime.combine(self.date, self.end_time, tzinfo=tz)

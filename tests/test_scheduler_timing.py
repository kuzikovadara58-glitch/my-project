from __future__ import annotations

from datetime import date, time
from zoneinfo import ZoneInfo

from journal_automation.config.models import AutomationSettings, Group
from journal_automation.domain.session import TrainingSession
from journal_automation.domain.states import AutomationState, TrainingDomainState
from journal_automation.scheduler.timing import compute_fill_time

MOSCOW = ZoneInfo("Europe/Moscow")

GROUP = Group(id="g1", name="Группа", journal_group_id="", schedule=(), athletes=())


def _session(start: time, end: time) -> TrainingSession:
    return TrainingSession(
        session_id="s1",
        date=date(2026, 9, 28),
        group=GROUP,
        start_time=start,
        end_time=end,
        domain_state=TrainingDomainState.PLANNED,
        automation_state=AutomationState.PENDING,
    )


def test_fill_after_start_minutes_used_when_set():
    session = _session(time(18, 0), time(19, 30))
    automation = AutomationSettings(fill_after_start_minutes=5, fill_after_end_minutes=10)

    fill_time = compute_fill_time(session, automation, MOSCOW)

    assert fill_time == session.start_datetime(MOSCOW).replace(minute=5, hour=18)


def test_fill_after_end_minutes_used_when_start_offset_not_set():
    session = _session(time(18, 0), time(19, 30))
    automation = AutomationSettings(fill_after_start_minutes=None, fill_after_end_minutes=10)

    fill_time = compute_fill_time(session, automation, MOSCOW)

    assert fill_time.hour == 19 and fill_time.minute == 40


def test_fill_time_zero_offset_equals_start():
    session = _session(time(18, 0, 5), time(18, 0, 7))
    automation = AutomationSettings(fill_after_start_minutes=0, fill_after_end_minutes=10)

    fill_time = compute_fill_time(session, automation, MOSCOW)

    assert fill_time == session.start_datetime(MOSCOW)

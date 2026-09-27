from __future__ import annotations

from datetime import date, datetime, timezone

from journal_automation.config.manager import ConfigManager
from journal_automation.domain.session import build_session_id
from journal_automation.domain.states import AutomationState, TrainingDomainState
from journal_automation.services.history_manager import HistoryManager
from journal_automation.services.time_service import TimeService
from journal_automation.services.training_service import TrainingService

MONDAY = date(2026, 9, 28)  # см. config/groups.yaml: g1 тренируется по понедельникам
TUESDAY = date(2026, 9, 29)


def _make_service(config_dir_factory, tmp_path, clock_utc: datetime, absences=None, history_name="history.json"):
    config_dir = config_dir_factory(absences=absences)
    config = ConfigManager(config_dir).load()
    time_service = TimeService(config.app.timezone, clock=lambda: clock_utc)
    history = HistoryManager(tmp_path / history_name)
    return TrainingService(config, time_service, history), history, config


def test_sessions_generated_only_on_matching_weekday(config_dir_factory, tmp_path):
    before_start = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    service, _history, _config = _make_service(config_dir_factory, tmp_path, before_start)

    monday_sessions = service.get_sessions_for_date(MONDAY)
    tuesday_sessions = service.get_sessions_for_date(TUESDAY)

    assert len(monday_sessions) == 1
    assert monday_sessions[0].group.id == "g1"
    assert tuesday_sessions == []


def test_session_id_is_stable_and_matches_expected_format(config_dir_factory, tmp_path):
    before_start = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    service, _history, _config = _make_service(config_dir_factory, tmp_path, before_start)

    session = service.get_sessions_for_date(MONDAY)[0]

    assert session.session_id == build_session_id(MONDAY, "g1", session.start_time)
    assert session.session_id == "2026-09-28:g1:18:00"


def test_domain_state_planned_before_end_completed_after(config_dir_factory, tmp_path):
    # Занятие 18:00-19:30 по Москве (UTC+3) -> 15:00-16:30 UTC.
    before_end = datetime(2026, 9, 28, 16, 0, tzinfo=timezone.utc)
    after_end = datetime(2026, 9, 28, 17, 0, tzinfo=timezone.utc)

    service_before, _, _ = _make_service(config_dir_factory, tmp_path, before_end)
    session_before = service_before.get_sessions_for_date(MONDAY)[0]
    assert session_before.domain_state is TrainingDomainState.PLANNED

    service_after, _, _ = _make_service(config_dir_factory, tmp_path, after_end)
    session_after = service_after.get_sessions_for_date(MONDAY)[0]
    assert session_after.domain_state is TrainingDomainState.COMPLETED


def test_automation_state_defaults_to_pending_without_history(config_dir_factory, tmp_path):
    clock = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    service, _history, _config = _make_service(config_dir_factory, tmp_path, clock)

    session = service.get_sessions_for_date(MONDAY)[0]

    assert session.automation_state is AutomationState.PENDING


def test_should_process_session_matrix(config_dir_factory, tmp_path):
    clock = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    service, history, _config = _make_service(config_dir_factory, tmp_path, clock)
    session_id = "2026-09-28:g1:18:00"

    cases = [
        (AutomationState.SUCCESS, False),
        (AutomationState.ERROR, True),
        (AutomationState.NEEDS_ATTENTION, True),
        (AutomationState.SKIPPED, False),
    ]
    for state, expected in cases:
        history.record_attempt(session_id, state)
        session = service.get_sessions_for_date(MONDAY)[0]
        decision = service.should_process_session(session)
        assert decision.should_process is expected, state

    # Без истории вовсе (новое занятие) — тоже должно обрабатываться.
    service_new, _new_history, _ = _make_service(
        config_dir_factory, tmp_path, clock, history_name="history-fresh.json"
    )
    fresh_session = service_new.get_sessions_for_date(MONDAY)[0]
    assert service_new.should_process_session(fresh_session).should_process is True


def test_absence_confirmation_none_when_no_data(config_dir_factory, tmp_path):
    clock = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    service, _history, _config = _make_service(config_dir_factory, tmp_path, clock, absences=None)

    session = service.get_sessions_for_date(MONDAY)[0]
    assert service.get_absence_confirmation(session) is None


def test_confirmed_complete_with_no_absentees_is_distinct_from_no_data(config_dir_factory, tmp_path):
    absences = {
        "attendance": [
            {"date": "2026-09-28", "group_id": "g1", "confirmed_complete": True, "athletes": []}
        ]
    }
    clock = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    service, _history, _config = _make_service(config_dir_factory, tmp_path, clock, absences=absences)

    session = service.get_sessions_for_date(MONDAY)[0]
    confirmation = service.get_absence_confirmation(session)

    assert confirmation is not None
    assert confirmation.confirmed_complete is True
    assert confirmation.absences == ()


def test_absences_not_confused_between_athletes(config_dir_factory, tmp_path):
    # a1 (мужской род) и a2 (женский род) — порядок в YAML намеренно
    # "перепутанный", чтобы проверить сопоставление по id, а не по позиции.
    absences = {
        "attendance": [
            {
                "date": "2026-09-28",
                "group_id": "g1",
                "confirmed_complete": True,
                "athletes": [
                    {"athlete_id": "a2", "reason": "family"},
                    {"athlete_id": "a1", "reason": "health"},
                ],
            }
        ]
    }
    clock = datetime(2026, 9, 28, 10, 0, tzinfo=timezone.utc)
    service, _history, _config = _make_service(config_dir_factory, tmp_path, clock, absences=absences)

    session = service.get_sessions_for_date(MONDAY)[0]
    confirmation = service.get_absence_confirmation(session)
    by_id = {a.athlete_id: a for a in confirmation.absences}

    assert by_id["a1"].comment.startswith("отпросился с тренировки в связи")
    assert by_id["a2"].comment.startswith("отпросилась с тренировки по семейным")

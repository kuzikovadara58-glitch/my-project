from __future__ import annotations

from datetime import datetime, timedelta
from datetime import time as time_
from zoneinfo import ZoneInfo

from journal_automation.automation.port import ProcessResult
from journal_automation.config.models import AutomationSettings
from journal_automation.domain.states import AutomationState
from journal_automation.scheduler.controller import AutomationController
from journal_automation.services.history_manager import HistoryManager
from journal_automation.services.time_service import TimeService
from tests._scheduler_doubles import FakeAutomationPort, FakeTrainingService, make_session
from tests.conftest import pump_events

MOSCOW = ZoneInfo("Europe/Moscow")


def _make_controller(tmp_path, sessions, results, now, idle_poll_seconds=0.05):
    time_service = TimeService("Europe/Moscow", clock=lambda: now)
    training_service = FakeTrainingService(sessions)
    history = HistoryManager(tmp_path / "history.json")
    automation = AutomationSettings(fill_after_start_minutes=0, fill_after_end_minutes=10)
    port = FakeAutomationPort(results)
    controller = AutomationController(
        training_service, history, port, time_service, automation,
        idle_poll_seconds=idle_poll_seconds,
    )
    return controller, history, port


def test_start_processes_due_session_and_emits_signals(qapp, tmp_path):
    now = datetime(2026, 9, 28, 18, 0, tzinfo=MOSCOW)
    session = make_session("s1", time_(18, 0), time_(18, 1))
    controller, history, port = _make_controller(
        tmp_path, [session], [ProcessResult(AutomationState.SUCCESS)], now
    )

    finished_ids: list[str] = []
    controller.session_finished.connect(finished_ids.append)
    statuses: list[str] = []
    controller.status_changed.connect(statuses.append)

    try:
        controller.start_automation()
        assert pump_events(qapp, lambda: "s1" in finished_ids, timeout=5.0)

        assert history.get("s1").automation_state is AutomationState.SUCCESS
        assert "running" in statuses
    finally:
        controller.shutdown()


def test_double_start_does_not_run_scheduler_twice(qapp, tmp_path):
    now = datetime(2026, 9, 28, 18, 0, tzinfo=MOSCOW)
    session = make_session("s1", time_(18, 0), time_(18, 1))
    controller, history, port = _make_controller(
        tmp_path, [session], [ProcessResult(AutomationState.SUCCESS)], now
    )

    finished_ids: list[str] = []
    controller.session_finished.connect(finished_ids.append)

    try:
        controller.start_automation()
        controller.start_automation()  # повторное нажатие — не должно создать второй scheduler
        assert pump_events(qapp, lambda: "s1" in finished_ids, timeout=5.0)
        # дать шанс возможному "второму" планировщику проявиться, если бы он был
        pump_events(qapp, lambda: False, timeout=0.3)

        assert port.calls == ["s1"]  # ровно один вызов, а не два
    finally:
        controller.shutdown()


def test_stop_updates_status_and_thread_finishes(qapp, tmp_path):
    now = datetime(2026, 9, 28, 18, 0, tzinfo=MOSCOW)
    far_session = make_session("s1", time_(20, 0), time_(21, 0))  # через 2 часа — будет WAITING
    controller, history, port = _make_controller(
        tmp_path, [far_session], [ProcessResult(AutomationState.SUCCESS)], now
    )

    statuses: list[str] = []
    controller.status_changed.connect(statuses.append)
    waiting_seen: list[str] = []
    controller.session_status_changed.connect(lambda sid, text: waiting_seen.append(sid))

    controller.start_automation()
    assert pump_events(qapp, lambda: "s1" in waiting_seen, timeout=5.0)

    controller.stop_automation()
    assert pump_events(qapp, lambda: "stopped" in statuses, timeout=5.0)
    assert pump_events(qapp, lambda: not controller.isRunning(), timeout=5.0)

    assert port.calls == []  # остановлено во время ожидания, обработка не началась


def test_shutdown_leaves_no_running_thread(qapp, tmp_path):
    now = datetime(2026, 9, 28, 18, 0, tzinfo=MOSCOW)
    far_session = make_session("s1", time_(20, 0), time_(21, 0))
    controller, _history, _port = _make_controller(
        tmp_path, [far_session], [ProcessResult(AutomationState.SUCCESS)], now
    )

    controller.start_automation()
    pump_events(qapp, lambda: controller.isRunning(), timeout=2.0)

    controller.shutdown()

    assert controller.isRunning() is False

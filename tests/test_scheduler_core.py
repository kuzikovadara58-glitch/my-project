from __future__ import annotations

import threading
import time as time_module
from datetime import datetime
from datetime import time as time_
from zoneinfo import ZoneInfo

from journal_automation.automation.port import ProcessResult
from journal_automation.config.models import AutomationSettings
from journal_automation.domain.states import AutomationState
from journal_automation.scheduler.core import SchedulerEventType, SchedulerLoop
from journal_automation.services.history_manager import HistoryManager
from journal_automation.services.time_service import TimeService
from tests._scheduler_doubles import FakeAutomationPort, FakeTrainingService, make_session

MOSCOW = ZoneInfo("Europe/Moscow")


def _run_until(loop: SchedulerLoop, stop_event: threading.Event, predicate, timeout: float = 3.0):
    thread = threading.Thread(target=loop.run, daemon=True)
    thread.start()
    deadline = time_module.monotonic() + timeout
    while time_module.monotonic() < deadline and not predicate():
        time_module.sleep(0.01)
    stop_event.set()
    thread.join(timeout=2.0)
    assert not thread.is_alive(), "поток планировщика не остановился вовремя"


def test_processes_due_session_and_records_success(tmp_path):
    now = datetime(2026, 9, 28, 18, 0, tzinfo=MOSCOW)
    time_service = TimeService("Europe/Moscow", clock=lambda: now)
    session = make_session("s1", time_(18, 0), time_(18, 1))
    training_service = FakeTrainingService([session])
    history = HistoryManager(tmp_path / "history.json")
    automation = AutomationSettings(fill_after_start_minutes=0, fill_after_end_minutes=10)
    port = FakeAutomationPort([ProcessResult(AutomationState.SUCCESS)])
    stop_event = threading.Event()
    events = []

    loop = SchedulerLoop(
        training_service, history, port, time_service, automation, stop_event,
        on_event=events.append, idle_poll_seconds=0.05,
    )

    _run_until(
        loop, stop_event,
        predicate=lambda: any(e.type is SchedulerEventType.PROCESSING_FINISHED for e in events),
    )

    record = history.get("s1")
    assert record is not None
    assert record.automation_state is AutomationState.SUCCESS
    assert port.calls == ["s1"]
    assert any(e.type is SchedulerEventType.STARTED for e in events)


def test_no_sessions_does_not_raise_and_emits_idle(tmp_path):
    now = datetime(2026, 9, 28, 18, 0, tzinfo=MOSCOW)
    time_service = TimeService("Europe/Moscow", clock=lambda: now)
    training_service = FakeTrainingService([])
    history = HistoryManager(tmp_path / "history.json")
    automation = AutomationSettings(fill_after_start_minutes=0, fill_after_end_minutes=10)
    port = FakeAutomationPort([])
    stop_event = threading.Event()
    events = []

    loop = SchedulerLoop(
        training_service, history, port, time_service, automation, stop_event,
        on_event=events.append, idle_poll_seconds=0.05,
    )

    _run_until(loop, stop_event, predicate=lambda: any(e.type is SchedulerEventType.IDLE for e in events))

    assert port.calls == []


def test_success_session_is_not_reprocessed(tmp_path):
    now = datetime(2026, 9, 28, 18, 0, tzinfo=MOSCOW)
    time_service = TimeService("Europe/Moscow", clock=lambda: now)
    session = make_session(
        "s1", time_(18, 0), time_(18, 1), automation_state=AutomationState.SUCCESS
    )
    # FakeTrainingService.should_process_session должен вести себя как
    # реальный TrainingService для уже успешного занятия — запрещаем явно.
    training_service = FakeTrainingService([session], allow=set())
    history = HistoryManager(tmp_path / "history.json")
    automation = AutomationSettings(fill_after_start_minutes=0, fill_after_end_minutes=10)
    port = FakeAutomationPort([ProcessResult(AutomationState.SUCCESS)])
    stop_event = threading.Event()
    events = []

    loop = SchedulerLoop(
        training_service, history, port, time_service, automation, stop_event,
        on_event=events.append, idle_poll_seconds=0.05,
    )

    _run_until(loop, stop_event, predicate=lambda: any(e.type is SchedulerEventType.IDLE for e in events))

    assert port.calls == []  # ни разу не вызван — занятие уже SUCCESS


def test_error_result_does_not_loop_forever_within_one_run(tmp_path):
    now = datetime(2026, 9, 28, 18, 0, tzinfo=MOSCOW)
    time_service = TimeService("Europe/Moscow", clock=lambda: now)
    session = make_session("s1", time_(18, 0), time_(18, 1))
    training_service = FakeTrainingService([session])  # should_process всегда True (как для ERROR)
    history = HistoryManager(tmp_path / "history.json")
    automation = AutomationSettings(fill_after_start_minutes=0, fill_after_end_minutes=10)
    port = FakeAutomationPort([ProcessResult(AutomationState.ERROR, "тестовая ошибка")])
    stop_event = threading.Event()
    events = []

    loop = SchedulerLoop(
        training_service, history, port, time_service, automation, stop_event,
        on_event=events.append, idle_poll_seconds=0.05,
    )

    # Ждём, пока после ERROR планировщик уйдёт в IDLE хотя бы один раз —
    # если бы защита от повторного запуска в рамках одного run не работала,
    # port.process_session вызывался бы бесконечно быстро по кругу.
    _run_until(
        loop, stop_event,
        predicate=lambda: sum(1 for e in events if e.type is SchedulerEventType.IDLE) >= 1,
    )

    assert port.calls == ["s1"]  # ровно один вызов за весь запуск
    assert history.get("s1").automation_state is AutomationState.ERROR


def test_stop_interrupts_waiting_without_processing(tmp_path):
    now = datetime(2026, 9, 28, 18, 0, tzinfo=MOSCOW)
    time_service = TimeService("Europe/Moscow", clock=lambda: now)
    # Занятие наступит через час — планировщик должен ждать, а не обрабатывать.
    session = make_session("s1", time_(19, 0), time_(19, 30))
    training_service = FakeTrainingService([session])
    history = HistoryManager(tmp_path / "history.json")
    automation = AutomationSettings(fill_after_start_minutes=0, fill_after_end_minutes=10)
    port = FakeAutomationPort([ProcessResult(AutomationState.SUCCESS)])
    stop_event = threading.Event()
    events = []

    loop = SchedulerLoop(
        training_service, history, port, time_service, automation, stop_event,
        on_event=events.append, idle_poll_seconds=0.05,
    )

    _run_until(loop, stop_event, predicate=lambda: any(e.type is SchedulerEventType.WAITING for e in events))

    assert port.calls == []
    assert history.get("s1") is None
    assert any(e.type is SchedulerEventType.STOPPED for e in events)


def test_cancelled_mid_processing_does_not_write_history(tmp_path):
    now = datetime(2026, 9, 28, 18, 0, tzinfo=MOSCOW)
    time_service = TimeService("Europe/Moscow", clock=lambda: now)
    session = make_session("s1", time_(18, 0), time_(18, 1))
    training_service = FakeTrainingService([session])
    history = HistoryManager(tmp_path / "history.json")
    automation = AutomationSettings(fill_after_start_minutes=0, fill_after_end_minutes=10)
    port = FakeAutomationPort([None])  # None = обработка "прервана" (кооперативная отмена)
    stop_event = threading.Event()
    events = []

    loop = SchedulerLoop(
        training_service, history, port, time_service, automation, stop_event,
        on_event=events.append, idle_poll_seconds=0.05,
    )

    _run_until(
        loop, stop_event,
        predicate=lambda: any(e.type is SchedulerEventType.PROCESSING_STARTED for e in events),
    )

    assert history.get("s1") is None
    assert not any(e.type is SchedulerEventType.PROCESSING_FINISHED for e in events)

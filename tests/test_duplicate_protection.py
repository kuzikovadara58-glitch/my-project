"""Сценарий из docs/PLAN.md (этап 3, раздел 19):

Session A -> SUCCESS -> "перезапуск программы" (новый HistoryManager на том
же файле, новый TrainingService) -> Session A не должна обрабатываться снова.

Использует настоящие ConfigManager/TrainingService (этап 2) и настоящий
SchedulerLoop + MockJournalAutomation (этап 3) — не только дублёры, чтобы
проверить сквозную интеграцию, а не только изолированную логику.
"""

from __future__ import annotations

import threading
import time as time_module
from datetime import datetime
from zoneinfo import ZoneInfo

from journal_automation.automation.mock import MockJournalAutomation
from journal_automation.config.manager import ConfigManager
from journal_automation.domain.states import AutomationState
from journal_automation.scheduler.core import SchedulerEventType, SchedulerLoop
from journal_automation.services.history_manager import HistoryManager
from journal_automation.services.time_service import TimeService
from journal_automation.services.training_service import TrainingService

MOSCOW = ZoneInfo("Europe/Moscow")
MONDAY_AFTER_TRAINING = datetime(2026, 9, 28, 20, 0, tzinfo=MOSCOW)  # g1: 18:00-19:30


def _run_until(loop: SchedulerLoop, stop_event: threading.Event, predicate, timeout: float = 5.0):
    thread = threading.Thread(target=loop.run, daemon=True)
    thread.start()
    deadline = time_module.monotonic() + timeout
    while time_module.monotonic() < deadline and not predicate():
        time_module.sleep(0.01)
    stop_event.set()
    thread.join(timeout=2.0)
    assert not thread.is_alive()


def test_session_success_survives_restart_and_is_not_reprocessed(config_dir_factory, tmp_path):
    config_dir = config_dir_factory()
    config = ConfigManager(config_dir).load()
    history_path = tmp_path / "history.json"

    # -- "первый запуск программы": обработать занятие один раз --
    time_service_1 = TimeService(config.app.timezone, clock=lambda: MONDAY_AFTER_TRAINING)
    history_1 = HistoryManager(history_path)
    training_service_1 = TrainingService(config, time_service_1, history_1)
    port_1 = MockJournalAutomation(simulate_error=False, step_delay_seconds=0.01)
    stop_event_1 = threading.Event()

    events_1: list = []
    loop_1 = SchedulerLoop(
        training_service_1, history_1, port_1, time_service_1, config.app.automation,
        stop_event_1, on_event=events_1.append, idle_poll_seconds=0.05,
    )

    _run_until(
        loop_1, stop_event_1,
        predicate=lambda: any(e.type is SchedulerEventType.PROCESSING_FINISHED for e in events_1),
    )

    session_id = "2026-09-28:g1:18:00"
    assert history_1.get(session_id).automation_state is AutomationState.SUCCESS

    # -- "перезапуск программы": новые объекты поверх того же файла истории --
    time_service_2 = TimeService(config.app.timezone, clock=lambda: MONDAY_AFTER_TRAINING)
    history_2 = HistoryManager(history_path)  # читает тот же файл заново
    training_service_2 = TrainingService(config, time_service_2, history_2)
    port_2 = MockJournalAutomation(simulate_error=False, step_delay_seconds=0.01)
    stop_event_2 = threading.Event()

    events_2: list = []
    loop_2 = SchedulerLoop(
        training_service_2, history_2, port_2, time_service_2, config.app.automation,
        stop_event_2, on_event=events_2.append, idle_poll_seconds=0.05,
    )

    _run_until(
        loop_2, stop_event_2,
        predicate=lambda: any(e.type is SchedulerEventType.IDLE for e in events_2),
    )

    assert history_2.get(session_id).automation_state is AutomationState.SUCCESS
    assert history_2.get(session_id).attempt_count == 1  # не увеличился повторной обработкой

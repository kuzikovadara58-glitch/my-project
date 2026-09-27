from __future__ import annotations

import threading
import time as time_module
from datetime import time as time_

from journal_automation.automation.mock import MockJournalAutomation
from journal_automation.domain.states import AutomationState
from tests._scheduler_doubles import make_session

SESSION = make_session("s1", time_(18, 0), time_(19, 30))


def test_success_scenario_is_fast_in_tests():
    mock = MockJournalAutomation(simulate_error=False, step_delay_seconds=0.01)
    stop_event = threading.Event()

    started = time_module.monotonic()
    result = mock.process_session(SESSION, stop_event)
    elapsed = time_module.monotonic() - started

    assert result is not None
    assert result.state is AutomationState.SUCCESS
    assert elapsed < 1.0  # тест не ждёт реальных минут (docs/SPEC.md, раздел 11)


def test_error_scenario_when_simulated():
    mock = MockJournalAutomation(simulate_error=True, step_delay_seconds=0.01)
    stop_event = threading.Event()

    result = mock.process_session(SESSION, stop_event)

    assert result is not None
    assert result.state is AutomationState.ERROR
    assert result.message


def test_stop_event_interrupts_processing_immediately():
    mock = MockJournalAutomation(simulate_error=False, step_delay_seconds=5.0)
    stop_event = threading.Event()
    stop_event.set()  # уже остановлено до начала обработки

    started = time_module.monotonic()
    result = mock.process_session(SESSION, stop_event)
    elapsed = time_module.monotonic() - started

    assert result is None
    assert elapsed < 1.0

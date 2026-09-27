"""Безопасная имитация обработки занятия — реальный сайт не затрагивается.

docs/SPEC.md, этап 3, раздел 15: "На этом этапе реальный электронный журнал
НЕ подключать". Используется `stop_event.wait()` вместо `time.sleep()` —
остановка автоматизации прерывает обработку немедленно между шагами, а не
только после полного цикла (кооперативная отмена, docs/ARCHITECTURE.md §2).
"""

from __future__ import annotations

import threading

from journal_automation.automation.port import ProcessResult
from journal_automation.domain.session import TrainingSession
from journal_automation.domain.states import AutomationState

# Шаги имитации: "проверка данных" -> "имитация работы". Число шагов и
# задержка между ними — только для визуальной демонстрации процесса
# (docs/SPEC.md, раздел 11), не для реальной длительности какой-либо операции.
_STEPS = 2


class MockJournalAutomation:
    def __init__(self, simulate_error: bool = False, step_delay_seconds: float = 0.5) -> None:
        self._simulate_error = simulate_error
        self._step_delay_seconds = step_delay_seconds

    def process_session(
        self, session: TrainingSession, stop_event: threading.Event
    ) -> ProcessResult | None:
        for _ in range(_STEPS):
            if stop_event.wait(self._step_delay_seconds):
                return None  # остановлено до завершения — не SUCCESS и не ERROR

        if self._simulate_error:
            return ProcessResult(
                state=AutomationState.ERROR,
                message="смоделированная ошибка (--simulate-error)",
            )
        return ProcessResult(state=AutomationState.SUCCESS, message=None)

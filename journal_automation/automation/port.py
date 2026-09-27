"""Интерфейс, за которым Scheduler не различает mock и реальный сайт (этап 3, §12).

Соответствует роли `JournalAdapter` из docs/ARCHITECTURE.md §5, но на этом
этапе сознательно сужен до одного метода: детальные операции
(login/attach_photo/set_attendance/save/verify_saved и т.д.) появятся, когда
будет изучен реальный сайт (этапы 5-6) — придумывать их сейчас означало бы
придумывать несуществующие селекторы и особенности сайта, чего делать нельзя
(docs/SPEC.md, раздел 15 этапа 3).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol

from journal_automation.domain.session import TrainingSession
from journal_automation.domain.states import AutomationState
from journal_automation.photos.models import TrainingPhoto


@dataclass(frozen=True)
class ProcessResult:
    state: AutomationState  # SUCCESS | ERROR (NEEDS_ATTENTION — задел на будущее)
    message: str | None = None


class JournalAutomationPort(Protocol):
    def process_session(
        self,
        session: TrainingSession,
        stop_event: threading.Event,
        photo: TrainingPhoto | None = None,
    ) -> ProcessResult | None:
        """Обрабатывает одно занятие.

        `photo` — уже выбранный и скачанный локально файл (этап 4,
        `journal_automation/photos/service.py`); может быть `None`, если
        источник фото не настроен (SchedulerLoop без `photo_service`) — это
        сохраняет обратную совместимость со сценариями этапа 3, где фото
        ещё не было частью конвейера.

        Возвращает `None`, если обработка была прервана через `stop_event` до
        завершения — кооперативная отмена (docs/ARCHITECTURE.md §2): в этом
        случае занятие не считается ни успешным, ни ошибочным и в историю
        ничего не пишется (см. journal_automation/scheduler/core.py).
        """
        ...

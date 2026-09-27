"""Логика планировщика без зависимости от Qt.

Решает, какое занятие и когда обрабатывать; поток и сигналы — забота
`journal_automation/scheduler/controller.py`. Такое разделение позволяет
тестировать логику планирования без запуска Qt-приложения (docs/PLAN.md,
этап 3, раздел 26).

Не занятой ожидание (`while True: pass`) не используется нигде — всё
ожидание идёт через `threading.Event.wait()`, который блокирует поток без
нагрузки на CPU и мгновенно прерывается при остановке (этап 3, раздел 9).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from journal_automation.automation.port import JournalAutomationPort
from journal_automation.config.models import AutomationSettings
from journal_automation.domain.session import TrainingSession
from journal_automation.domain.states import AutomationState
from journal_automation.photos.models import PhotoSelectionStatus
from journal_automation.photos.presentation import format_photo_status
from journal_automation.photos.service import PhotoService
from journal_automation.scheduler.timing import compute_fill_time
from journal_automation.services.history_manager import HistoryManager
from journal_automation.services.time_service import TimeService
from journal_automation.services.training_service import TrainingService

logger = logging.getLogger(__name__)


class SchedulerEventType(str, Enum):
    STARTED = "started"
    IDLE = "idle"
    WAITING = "waiting"
    PROCESSING_STARTED = "processing_started"
    PROCESSING_FINISHED = "processing_finished"
    STOPPED = "stopped"
    PHOTO_CHECKING = "photo_checking"  # запрос к источнику фото начат
    PHOTO_STATUS = "photo_status"  # готовый текст результата (docs/SPEC.md, этап 4, раздел 25)


@dataclass(frozen=True)
class SchedulerEvent:
    type: SchedulerEventType
    session_id: str | None = None
    message: str = ""


# Внутренние сигнальные значения для _check_photo — не часть публичного API.
_WAITING_FOR_PHOTO = object()
_PHOTO_UNRESOLVED = object()


class SchedulerLoop:
    def __init__(
        self,
        training_service: TrainingService,
        history: HistoryManager,
        automation_port: JournalAutomationPort,
        time_service: TimeService,
        automation_settings: AutomationSettings,
        stop_event: threading.Event,
        on_event: Callable[[SchedulerEvent], None] | None = None,
        idle_poll_seconds: float = 30.0,
        photo_service: PhotoService | None = None,
        photo_recheck_seconds: float = 60.0,
    ) -> None:
        self._training_service = training_service
        self._history = history
        self._automation_port = automation_port
        self._time_service = time_service
        self._automation_settings = automation_settings
        self._stop_event = stop_event
        self._on_event = on_event or (lambda event: None)
        self._idle_poll_seconds = idle_poll_seconds
        # Опционально: пока источник фото не настроен (этап 4), поведение
        # полностью совпадает с этапом 3 — фото не проверяется вовсе.
        self._photo_service = photo_service
        self._photo_recheck_seconds = photo_recheck_seconds
        # Защита от штормового авто-повтора ERROR/NEEDS_ATTENTION в рамках
        # ОДНОГО запуска автоматизации: контролируемый повтор (docs/SPEC.md,
        # раздел 9-10) означает "можно попробовать снова при следующем
        # запуске", а не "тут же по кругу", пока пользователь не остановит
        # автоматизацию сам.
        self._attempted_this_run: set[str] = set()

    def run(self) -> None:
        logger.info("Scheduler started")
        self._emit(SchedulerEventType.STARTED)
        while not self._stop_event.is_set():
            candidate = self._pick_next_candidate()
            if candidate is None:
                self._emit(SchedulerEventType.IDLE, message="нет занятий для обработки")
                if self._stop_event.wait(self._idle_poll_seconds):
                    break
                continue

            session, fill_time = candidate
            wait_seconds = (fill_time - self._time_service.now()).total_seconds()
            if wait_seconds > 0:
                logger.info("Session waiting: %s", session.session_id)
                self._emit(
                    SchedulerEventType.WAITING,
                    session.session_id,
                    f"{session.group.name}: ожидание до {fill_time:%H:%M:%S}",
                )
                if self._stop_event.wait(wait_seconds):
                    break
                continue

            self._process(session)

        logger.info("Scheduler stopped")
        self._emit(SchedulerEventType.STOPPED)

    def _pick_next_candidate(self) -> tuple[TrainingSession, datetime] | None:
        sessions = self._training_service.get_sessions_for_today()
        tz = self._time_service.timezone
        candidates: list[tuple[TrainingSession, datetime]] = []
        for session in sessions:
            if session.session_id in self._attempted_this_run:
                continue
            if not self._training_service.should_process_session(session).should_process:
                continue
            fill_time = compute_fill_time(session, self._automation_settings, tz)
            candidates.append((session, fill_time))
        if not candidates:
            return None
        return min(candidates, key=lambda pair: pair[1])

    def _process(self, session: TrainingSession) -> None:
        photo = None
        if self._photo_service is not None:
            photo = self._check_photo(session)
            if photo is _WAITING_FOR_PHOTO:
                return  # не в attempted_this_run — попробуем снова после паузы
            if photo is _PHOTO_UNRESOLVED:
                return  # уже записано в историю как NEEDS_ATTENTION внутри _check_photo

        logger.info("Session processing started: %s", session.session_id)
        self._emit(
            SchedulerEventType.PROCESSING_STARTED,
            session.session_id,
            f"начата обработка: {session.group.name}",
        )

        result = self._automation_port.process_session(session, self._stop_event, photo)
        self._attempted_this_run.add(session.session_id)

        if result is None:
            # Прервано остановкой до завершения — не пишем в историю вовсе,
            # занятие останется доступным для обработки при следующем запуске.
            logger.info("Session processing cancelled: %s", session.session_id)
            return

        self._history.record_attempt(session.session_id, result.state, error_message=result.message)

        if result.state is AutomationState.SUCCESS:
            logger.info("Session processing successful: %s", session.session_id)
        else:
            logger.warning("Session processing failed: %s (%s)", session.session_id, result.message)

        self._emit(
            SchedulerEventType.PROCESSING_FINISHED,
            session.session_id,
            f"{session.group.name}: {result.state.value}",
        )

    def _check_photo(self, session: TrainingSession):
        """Возвращает `TrainingPhoto`, либо один из внутренних сигналов:

        `_WAITING_FOR_PHOTO` — фото ещё может появиться, ждём и проверим
        занятие снова (кооперативно, через `stop_event.wait`), не считая
        это попыткой обработки. `_PHOTO_UNRESOLVED` — фото не найдено /
        источник недоступен / несколько кандидатов без возможности выбрать
        однозначно; занятие переведено в `NEEDS_ATTENTION` (docs/SPEC.md,
        этап 4, разделы 21-22, 29: "нет валидного фото -> нет финального
        заполнения журнала").
        """

        self._emit(SchedulerEventType.PHOTO_CHECKING, session.session_id, "проверяется...")
        result = self._photo_service.get_photo_for_session(session)
        photo_status_text = format_photo_status(result)
        self._emit(SchedulerEventType.PHOTO_STATUS, session.session_id, photo_status_text)

        if result.status is PhotoSelectionStatus.FOUND:
            return result.photo

        if result.status is PhotoSelectionStatus.WAITING_FOR_PHOTO:
            logger.info("Session waiting for photo: %s", session.session_id)
            self._emit(
                SchedulerEventType.WAITING,
                session.session_id,
                f"{session.group.name}: ожидание фото ({result.message})",
            )
            self._stop_event.wait(self._photo_recheck_seconds)
            return _WAITING_FOR_PHOTO

        # NOT_FOUND / SOURCE_UNAVAILABLE / AMBIGUOUS — терминально для этого запуска.
        self._attempted_this_run.add(session.session_id)
        message = f"фото: {result.message}"
        logger.warning("Session processing failed (photo): %s (%s)", session.session_id, message)
        self._history.record_attempt(
            session.session_id, AutomationState.NEEDS_ATTENTION, error_message=message
        )
        self._emit(
            SchedulerEventType.PROCESSING_FINISHED,
            session.session_id,
            f"{session.group.name}: {message}",
        )
        return _PHOTO_UNRESOLVED

    def _emit(
        self, event_type: SchedulerEventType, session_id: str | None = None, message: str = ""
    ) -> None:
        self._on_event(SchedulerEvent(type=event_type, session_id=session_id, message=message))

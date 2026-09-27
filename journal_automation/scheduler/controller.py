"""QThread-обёртка над SchedulerLoop (docs/ARCHITECTURE.md §2).

GUI-поток не блокируется: вся работа планировщика (и в будущем — браузера)
выполняется в этом фоновом потоке, обмен с GUI — только через Qt-сигналы, не
через прямой доступ к widgets (этап 3, раздел 8).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from journal_automation.automation.port import JournalAutomationPort
from journal_automation.config.models import AutomationSettings
from journal_automation.domain.session import TrainingSession
from journal_automation.photos.presentation import format_photo_status
from journal_automation.photos.service import PhotoService
from journal_automation.scheduler.core import SchedulerEvent, SchedulerEventType, SchedulerLoop
from journal_automation.services.history_manager import HistoryManager
from journal_automation.services.time_service import TimeService
from journal_automation.services.training_service import TrainingService

logger = logging.getLogger(__name__)


class AutomationController(QThread):
    status_changed = Signal(str)  # "running" | "stopped"
    event_logged = Signal(str)  # готовый текст для "Последнее событие"
    session_status_changed = Signal(str, str)  # session_id, временный текст статуса
    session_finished = Signal(str)  # session_id — забрать финальное состояние из истории
    photo_status_changed = Signal(str, str)  # session_id, текст "Фото: ..." (этап 4, раздел 25)

    def __init__(
        self,
        training_service: TrainingService,
        history: HistoryManager,
        automation_port: JournalAutomationPort,
        time_service: TimeService,
        automation_settings: AutomationSettings,
        idle_poll_seconds: float = 30.0,
        photo_service: PhotoService | None = None,
        photo_recheck_seconds: float = 60.0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._training_service = training_service
        self._history = history
        self._automation_port = automation_port
        self._time_service = time_service
        self._automation_settings = automation_settings
        self._idle_poll_seconds = idle_poll_seconds
        self._photo_service = photo_service
        self._photo_recheck_seconds = photo_recheck_seconds
        self._stop_event = threading.Event()

    def start_automation(self) -> None:
        """Вызывается из GUI-потока по нажатию кнопки."""

        if self.isRunning():
            return  # повторное нажатие не создаёт второй scheduler
        self._stop_event = threading.Event()
        logger.info("Automation started")
        self.status_changed.emit("running")
        self.start()  # QThread.start() -> вызовет self.run() в новом потоке

    def stop_automation(self) -> None:
        """Вызывается из GUI-потока по нажатию кнопки. Не блокирует GUI."""

        if not self.isRunning():
            return
        self._stop_event.set()

    def shutdown(self, timeout_ms: int = 3000) -> None:
        """Только для закрытия приложения — единственное место, где допустим

        блокирующий wait (этап 3, раздел 22): без него после закрытия окна
        мог бы остаться работающий поток/процесс.
        """

        if self.isRunning():
            self._stop_event.set()
            self.wait(timeout_ms)

    def run(self) -> None:  # выполняется в фоновом потоке
        loop = SchedulerLoop(
            training_service=self._training_service,
            history=self._history,
            automation_port=self._automation_port,
            time_service=self._time_service,
            automation_settings=self._automation_settings,
            stop_event=self._stop_event,
            on_event=self._handle_event,
            idle_poll_seconds=self._idle_poll_seconds,
            photo_service=self._photo_service,
            photo_recheck_seconds=self._photo_recheck_seconds,
        )
        loop.run()
        logger.info("Automation stopped")
        self.status_changed.emit("stopped")

    def _handle_event(self, event: SchedulerEvent) -> None:
        # Выполняется в фоновом потоке (вызывается из SchedulerLoop.run) —
        # безопасно, т.к. используются только Qt-сигналы, никогда не widgets
        # напрямую (docs/ARCHITECTURE.md §2).
        timestamp = datetime.now().strftime("%H:%M:%S")
        if event.message:
            self.event_logged.emit(f"{timestamp} — {event.message}")

        if event.type is SchedulerEventType.WAITING and event.session_id:
            self.session_status_changed.emit(event.session_id, f"🕐 Ожидание ({event.message})")
        elif event.type is SchedulerEventType.PROCESSING_STARTED and event.session_id:
            self.session_status_changed.emit(event.session_id, "🔵 Выполняется")
        elif event.type is SchedulerEventType.PROCESSING_FINISHED and event.session_id:
            self.session_finished.emit(event.session_id)
        elif event.type is SchedulerEventType.PHOTO_CHECKING and event.session_id:
            self.photo_status_changed.emit(event.session_id, "Фото: 🔄 проверяется...")
        elif event.type is SchedulerEventType.PHOTO_STATUS and event.session_id:
            self.photo_status_changed.emit(event.session_id, f"Фото: {event.message}")


class PhotoCheckWorker(QThread):
    """Одноразовая проверка фото по нажатию кнопки «Проверить фото» (раздел 26).

    Отдельный лёгкий поток, а не переиспользование `AutomationController` —
    работает независимо от того, запущена ли автоматизация, и не блокирует
    GUI (Google Drive API — блокирующий сетевой вызов).
    """

    result_ready = Signal(str, str)  # session_id, готовый текст "Фото: ..."

    def __init__(self, photo_service: PhotoService, session: TrainingSession, parent=None) -> None:
        super().__init__(parent)
        self._photo_service = photo_service
        self._session = session

    def run(self) -> None:
        result = self._photo_service.get_photo_for_session(self._session)
        self.result_ready.emit(self._session.session_id, f"Фото: {format_photo_status(result)}")

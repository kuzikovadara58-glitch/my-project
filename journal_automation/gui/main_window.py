"""Главный экран (docs/PLAN.md, этапы 3-4).

GUI не хранит расписание сам и не знает про сайт журнала или Google Drive —
только читает `TrainingService` (этап 2) и `PhotoService` (этап 4) и получает
обновления от `AutomationController` через сигналы (docs/ARCHITECTURE.md §2):
виджеты никогда не трогаются из фонового потока напрямую.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from journal_automation.config.manager import LoadedConfig
from journal_automation.domain.session import TrainingSession
from journal_automation.domain.states import AutomationState
from journal_automation.photos.service import PhotoService
from journal_automation.scheduler.controller import AutomationController, PhotoCheckWorker
from journal_automation.services.time_service import TimeService
from journal_automation.services.training_service import TrainingService

AUTOMATION_STATUS_LABELS: dict[AutomationState, str] = {
    AutomationState.PENDING: "🕐 Ожидание",
    AutomationState.WAITING: "🕐 Ожидание",
    AutomationState.RUNNING: "🔵 Выполняется",
    AutomationState.SUCCESS: "✅ Заполнено",
    AutomationState.ERROR: "❌ Ошибка",
    AutomationState.SKIPPED: "⏭ Пропущено",
    AutomationState.NEEDS_ATTENTION: "⚠ Требуется внимание",
}

_REFRESH_INTERVAL_MS = 2000


class MainWindow(QWidget):
    def __init__(
        self,
        training_service: TrainingService,
        controller: AutomationController,
        config: LoadedConfig,
        time_service: TimeService,
        photo_service: PhotoService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.training_service = training_service
        self.controller = controller
        self.config = config
        self.time_service = time_service
        self.photo_service = photo_service

        self._live_overrides: dict[str, str] = {}
        self._photo_status_by_session: dict[str, str] = {}
        self._sessions_by_id: dict[str, TrainingSession] = {}
        # Ссылки на активные PhotoCheckWorker — без этого Python может собрать
        # объект потока до завершения run() (раздел 26).
        self._photo_workers: set[PhotoCheckWorker] = set()

        self.setWindowTitle("Электронный журнал — автоматизация")
        self._build_ui()
        self._connect_signals()
        self._refresh_sessions()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_sessions)
        self._refresh_timer.start(_REFRESH_INTERVAL_MS)

    # -- построение интерфейса -------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("ЭЛЕКТРОННЫЙ ЖУРНАЛ")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        today = self.time_service.today()
        self.date_label = QLabel(f"Сегодня: {today:%d.%m.%Y}")
        layout.addWidget(self.date_label)

        self.status_label = QLabel("⚪ Автоматизация не запущена")
        layout.addWidget(self.status_label)

        layout.addWidget(QLabel("Тренировки сегодня"))

        self._sessions_layout = QVBoxLayout()
        sessions_container = QWidget()
        sessions_container.setLayout(self._sessions_layout)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(sessions_container)
        scroll_area.setMinimumHeight(160)
        layout.addWidget(scroll_area)

        self.next_label = QLabel("")
        layout.addWidget(self.next_label)

        buttons = QHBoxLayout()
        self.start_button = QPushButton("▶ ЗАПУСТИТЬ АВТОМАТИЗАЦИЮ")
        self.stop_button = QPushButton("■ ОСТАНОВИТЬ")
        self.stop_button.setEnabled(False)
        self.settings_button = QPushButton("⚙ Настройки")
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        buttons.addWidget(self.settings_button)
        layout.addLayout(buttons)

        self.last_event_label = QLabel("Последнее событие: —")
        layout.addWidget(self.last_event_label)

    def _connect_signals(self) -> None:
        self.start_button.clicked.connect(self._on_start_clicked)
        self.stop_button.clicked.connect(self._on_stop_clicked)
        self.settings_button.clicked.connect(self._on_settings_clicked)

        self.controller.status_changed.connect(self._on_status_changed)
        self.controller.event_logged.connect(self._on_event_logged)
        self.controller.session_status_changed.connect(self._on_session_status_changed)
        self.controller.session_finished.connect(self._on_session_finished)
        self.controller.photo_status_changed.connect(self._on_photo_status_changed)

    # -- обработчики кнопок ------------------------------------------------

    def _on_start_clicked(self) -> None:
        self.controller.start_automation()

    def _on_stop_clicked(self) -> None:
        self.controller.stop_automation()

    def _on_settings_clicked(self) -> None:
        automation = self.config.app.automation
        photos = self.config.app.photos
        fill_mode = (
            f"через {automation.fill_after_start_minutes} мин. после начала"
            if automation.fill_after_start_minutes is not None
            else f"через {automation.fill_after_end_minutes} мин. после окончания"
        )
        drive_reference = photos.google_drive.folder_url or photos.google_drive.folder_id or "(не настроено)"
        text = (
            f"Часовой пояс: {self.config.app.timezone}\n"
            f"Момент заполнения: {fill_mode}\n"
            f"Источник фото: {photos.source}\n"
            f"Папка Google Drive: {drive_reference}"
        )
        QMessageBox.information(self, "Настройки (только просмотр)", text)

    def _on_check_photo_clicked(self, session_id: str) -> None:
        session = self._sessions_by_id.get(session_id)
        if session is None or self.photo_service is None:
            return
        self._photo_status_by_session[session_id] = "Фото: 🔄 проверяется..."
        self._refresh_sessions()

        worker = PhotoCheckWorker(self.photo_service, session, parent=self)
        worker.result_ready.connect(self._on_photo_status_changed)
        worker.finished.connect(lambda w=worker: self._photo_workers.discard(w))
        self._photo_workers.add(worker)
        worker.start()

    # -- обработчики сигналов контроллера -----------------------------------

    def _on_status_changed(self, status: str) -> None:
        running = status == "running"
        if status == "running":
            self.status_label.setText("🟢 Автоматизация запущена")
        else:
            self.status_label.setText("⚪ Автоматизация остановлена")
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def _on_event_logged(self, text: str) -> None:
        self.last_event_label.setText(f"Последнее событие: {text}")

    def _on_session_status_changed(self, session_id: str, status_text: str) -> None:
        self._live_overrides[session_id] = status_text
        self._refresh_sessions()

    def _on_session_finished(self, session_id: str) -> None:
        self._live_overrides.pop(session_id, None)
        self._refresh_sessions()

    def _on_photo_status_changed(self, session_id: str, status_text: str) -> None:
        self._photo_status_by_session[session_id] = status_text
        self._refresh_sessions()

    # -- отрисовка списка занятий -------------------------------------------

    def _refresh_sessions(self) -> None:
        sessions = self.training_service.get_sessions_for_today()
        self._sessions_by_id = {s.session_id: s for s in sessions}

        while self._sessions_layout.count():
            item = self._sessions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not sessions:
            self._sessions_layout.addWidget(QLabel("Сегодня тренировок нет."))
        else:
            for session in sessions:
                self._sessions_layout.addWidget(self._build_session_row(session))

        self._update_next_session_label(sessions)

    def _build_session_row(self, session: TrainingSession) -> QWidget:
        row = QFrame()
        row.setFrameShape(QFrame.Shape.StyledPanel)
        row_layout = QVBoxLayout(row)

        header = QLabel(f"{session.start_time:%H:%M}-{session.end_time:%H:%M}  {session.group.name}")
        row_layout.addWidget(header)

        status_override = self._live_overrides.get(session.session_id)
        status_text = status_override or AUTOMATION_STATUS_LABELS.get(
            session.automation_state, session.automation_state.value
        )
        row_layout.addWidget(QLabel(status_text))

        if self.photo_service is not None:
            photo_row = QHBoxLayout()
            photo_text = self._photo_status_by_session.get(session.session_id, "Фото: проверяется...")
            photo_row.addWidget(QLabel(photo_text))

            check_button = QPushButton("🔄 Проверить фото")
            check_button.clicked.connect(
                lambda _checked=False, sid=session.session_id: self._on_check_photo_clicked(sid)
            )
            photo_row.addWidget(check_button)
            row_layout.addLayout(photo_row)

        return row

    def _update_next_session_label(self, sessions: list[TrainingSession]) -> None:
        pending = [
            s for s in sessions if self.training_service.should_process_session(s).should_process
        ]
        if pending:
            upcoming = min(pending, key=lambda s: s.start_time)
            self.next_label.setText(f"Следующая тренировка: {upcoming.start_time:%H:%M}")
        else:
            self.next_label.setText("Следующих тренировок на сегодня нет")

    # -- закрытие приложения -------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 (имя метода задано Qt)
        self.controller.shutdown()
        for worker in list(self._photo_workers):
            worker.wait(1000)
        super().closeEvent(event)

"""Главный экран (docs/PLAN.md, этап 3).

GUI не хранит расписание сам и не знает про сайт журнала — только читает
`TrainingService` (этап 2) и получает обновления от `AutomationController`
через сигналы (docs/ARCHITECTURE.md §2): виджеты никогда не трогаются из
фонового потока напрямую.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from journal_automation.config.manager import LoadedConfig
from journal_automation.domain.session import TrainingSession
from journal_automation.domain.states import AutomationState
from journal_automation.scheduler.controller import AutomationController
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
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.training_service = training_service
        self.controller = controller
        self.config = config
        self.time_service = time_service

        self._live_overrides: dict[str, str] = {}

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
        self.session_list = QListWidget()
        layout.addWidget(self.session_list)

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

    # -- обработчики кнопок ------------------------------------------------

    def _on_start_clicked(self) -> None:
        self.controller.start_automation()

    def _on_stop_clicked(self) -> None:
        self.controller.stop_automation()

    def _on_settings_clicked(self) -> None:
        automation = self.config.app.automation
        fill_mode = (
            f"через {automation.fill_after_start_minutes} мин. после начала"
            if automation.fill_after_start_minutes is not None
            else f"через {automation.fill_after_end_minutes} мин. после окончания"
        )
        text = (
            f"Часовой пояс: {self.config.app.timezone}\n"
            f"Папка с фото: {self.config.app.paths.photos}\n"
            f"Момент заполнения: {fill_mode}"
        )
        QMessageBox.information(self, "Настройки (только просмотр)", text)

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

    # -- отрисовка списка занятий -------------------------------------------

    def _refresh_sessions(self) -> None:
        sessions = self.training_service.get_sessions_for_today()
        self.session_list.clear()
        if not sessions:
            self.session_list.addItem("Сегодня тренировок нет.")
        else:
            for session in sessions:
                self.session_list.addItem(self._render_session_text(session))
        self._update_next_session_label(sessions)

    def _render_session_text(self, session: TrainingSession) -> str:
        override = self._live_overrides.get(session.session_id)
        status = override or AUTOMATION_STATUS_LABELS.get(
            session.automation_state, session.automation_state.value
        )
        return f"{session.start_time:%H:%M}-{session.end_time:%H:%M}  {session.group.name}\n{status}"

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
        super().closeEvent(event)

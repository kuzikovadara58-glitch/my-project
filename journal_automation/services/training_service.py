"""Генерация занятий на дату и защита от повторной автоматической обработки.

Собирает вместе конфигурацию (группы/расписание/посещаемость), время и
историю — но сам не читает YAML и не пишет в историю напрямую (это делают
ConfigManager и HistoryManager соответственно), только координирует их.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_

from journal_automation.config.manager import LoadedConfig
from journal_automation.domain.absence import AbsenceConfirmation, resolve_absence_confirmation
from journal_automation.domain.session import TrainingSession, build_session_id
from journal_automation.domain.states import AutomationState, TrainingDomainState
from journal_automation.services.history_manager import HistoryManager
from journal_automation.services.time_service import TimeService


@dataclass(frozen=True)
class RetryDecision:
    should_process: bool
    reason: str


class TrainingService:
    def __init__(
        self,
        config: LoadedConfig,
        time_service: TimeService,
        history: HistoryManager,
    ) -> None:
        self._config = config
        self._time_service = time_service
        self._history = history

    def get_sessions_for_date(self, target_date: date_) -> list[TrainingSession]:
        sessions: list[TrainingSession] = []
        weekday = target_date.weekday()
        for group in self._config.groups.values():
            for rule in group.schedule:
                if rule.weekday != weekday:
                    continue
                session_id = build_session_id(target_date, group.id, rule.start)
                sessions.append(
                    TrainingSession(
                        session_id=session_id,
                        date=target_date,
                        group=group,
                        start_time=rule.start,
                        end_time=rule.end,
                        domain_state=self._domain_state(target_date, rule.end),
                        automation_state=self._automation_state(session_id),
                    )
                )
        sessions.sort(key=lambda s: (s.start_time, s.group.name))
        return sessions

    def get_sessions_for_today(self) -> list[TrainingSession]:
        return self.get_sessions_for_date(self._time_service.today())

    def get_absence_confirmation(self, session: TrainingSession) -> AbsenceConfirmation | None:
        entry = self._config.attendance_for(session.date, session.group_id)
        if entry is None:
            return None
        return resolve_absence_confirmation(entry, session.group, self._config.absence_reasons)

    def should_process_session(self, session: TrainingSession) -> RetryDecision:
        """Защита от повторной обработки (docs/SPEC.md, раздел 10).

        Основана только на истории, не на времени — своевременность запуска
        (наступило ли время заполнения) решает планировщик (этап 3).
        """

        state = session.automation_state
        if state is AutomationState.SUCCESS:
            return RetryDecision(False, "занятие уже успешно обработано")
        if state is AutomationState.SKIPPED:
            return RetryDecision(
                False,
                "занятие пропущено по времени и не заполняется автоматически задним числом",
            )
        if state.allows_retry:
            return RetryDecision(True, f"допустим контролируемый повтор ({state.value})")
        return RetryDecision(True, "занятие ещё не обработано")

    def _domain_state(self, target_date: date_, end_time) -> TrainingDomainState:
        end_dt = self._time_service.now().replace(
            year=target_date.year,
            month=target_date.month,
            day=target_date.day,
            hour=end_time.hour,
            minute=end_time.minute,
            second=0,
            microsecond=0,
        )
        return (
            TrainingDomainState.COMPLETED
            if self._time_service.now() >= end_dt
            else TrainingDomainState.PLANNED
        )

    def _automation_state(self, session_id: str) -> AutomationState:
        record = self._history.get(session_id)
        return record.automation_state if record else AutomationState.PENDING

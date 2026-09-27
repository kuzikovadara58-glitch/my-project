"""Тестовые дублёры для сценариев планировщика (не тестовый файл сам по себе)."""

from __future__ import annotations

import threading
from datetime import date as date_
from datetime import time as time_

from journal_automation.automation.port import ProcessResult
from journal_automation.config.models import Group
from journal_automation.domain.session import TrainingSession
from journal_automation.domain.states import AutomationState, TrainingDomainState
from journal_automation.services.training_service import RetryDecision

DEMO_GROUP = Group(id="g1", name="Тестовая группа", journal_group_id="", schedule=(), athletes=())


def make_session(
    session_id: str,
    start: time_,
    end: time_,
    group: Group = DEMO_GROUP,
    domain_state: TrainingDomainState = TrainingDomainState.PLANNED,
    automation_state: AutomationState = AutomationState.PENDING,
    session_date: date_ = date_(2026, 9, 28),
) -> TrainingSession:
    return TrainingSession(
        session_id=session_id,
        date=session_date,
        group=group,
        start_time=start,
        end_time=end,
        domain_state=domain_state,
        automation_state=automation_state,
    )


class FakeTrainingService:
    """Подменяет TrainingService там, где SchedulerLoop нужны только два метода."""

    def __init__(self, sessions: list[TrainingSession], allow: set[str] | None = None) -> None:
        self._sessions = sessions
        # Если allow не задан — обрабатывать разрешено все переданные занятия.
        self._allow = allow if allow is not None else {s.session_id for s in sessions}

    def get_sessions_for_today(self) -> list[TrainingSession]:
        return list(self._sessions)

    def should_process_session(self, session: TrainingSession) -> RetryDecision:
        if session.session_id in self._allow:
            return RetryDecision(True, "тест: разрешено")
        return RetryDecision(False, "тест: запрещено")


class FakeAutomationPort:
    """Возвращает заранее заданные результаты по очереди, без реальных задержек."""

    def __init__(self, results: list[ProcessResult | None]) -> None:
        self._results = list(results)
        self.calls: list[str] = []

    def process_session(
        self, session: TrainingSession, stop_event: threading.Event, photo=None
    ) -> ProcessResult | None:
        self.calls.append(session.session_id)
        if not self._results:
            return ProcessResult(state=AutomationState.SUCCESS)
        return self._results.pop(0)

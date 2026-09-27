from __future__ import annotations

from datetime import datetime, timezone

from journal_automation.domain.states import AutomationState
from journal_automation.services.history_manager import HistoryManager


def test_record_created_and_retrieved(tmp_path):
    history = HistoryManager(tmp_path / "history.json")

    record = history.record_attempt("session-1", AutomationState.SUCCESS)

    assert record.session_id == "session-1"
    assert record.attempt_count == 1
    fetched = history.get("session-1")
    assert fetched is not None
    assert fetched.automation_state is AutomationState.SUCCESS


def test_was_successful_true_only_for_success(tmp_path):
    history = HistoryManager(tmp_path / "history.json")
    history.record_attempt("s-success", AutomationState.SUCCESS)
    history.record_attempt("s-error", AutomationState.ERROR)

    assert history.was_successful("s-success") is True
    assert history.was_successful("s-error") is False
    assert history.was_successful("s-unknown") is False


def test_attempt_count_increments_on_retry(tmp_path):
    history = HistoryManager(tmp_path / "history.json")
    history.record_attempt("s1", AutomationState.ERROR, error_message="boom")
    second = history.record_attempt("s1", AutomationState.SUCCESS)

    assert second.attempt_count == 2
    assert second.error_message is None


def test_history_persists_across_reload(tmp_path):
    path = tmp_path / "history.json"
    first = HistoryManager(path)
    first.record_attempt(
        "s1", AutomationState.SUCCESS, now=datetime(2026, 9, 28, 20, 0, tzinfo=timezone.utc)
    )

    reloaded = HistoryManager(path)

    record = reloaded.get("s1")
    assert record is not None
    assert record.automation_state is AutomationState.SUCCESS
    assert record.updated_at == datetime(2026, 9, 28, 20, 0, tzinfo=timezone.utc)


def test_error_message_not_required(tmp_path):
    history = HistoryManager(tmp_path / "history.json")
    record = history.record_attempt("s1", AutomationState.NEEDS_ATTENTION)

    assert record.error_message is None

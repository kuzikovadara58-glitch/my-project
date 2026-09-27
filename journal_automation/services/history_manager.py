"""Локальная история выполнения занятий — защита от повторной обработки.

Хранится в одном JSON-файле (docs/SPEC.md, раздел 9), запись атомарна
(пишется во временный файл и переименовывается) — частично записанный файл
не должен портить всю историю. Секреты сюда никогда не пишутся.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from journal_automation.domain.states import AutomationState


@dataclass(frozen=True)
class HistoryRecord:
    session_id: str
    automation_state: AutomationState
    updated_at: datetime
    attempt_count: int
    error_message: str | None = None

    def to_json_dict(self) -> dict:
        data = asdict(self)
        data["automation_state"] = self.automation_state.value
        data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_json_dict(cls, data: dict) -> "HistoryRecord":
        return cls(
            session_id=data["session_id"],
            automation_state=AutomationState(data["automation_state"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            attempt_count=int(data.get("attempt_count", 0)),
            error_message=data.get("error_message"),
        )


class HistoryManager:
    def __init__(self, history_file: Path) -> None:
        self._path = history_file
        self._records: dict[str, HistoryRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            self._records = {}
            return
        with self._path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        self._records = {
            item["session_id"]: HistoryRecord.from_json_dict(item) for item in raw.get("records", [])
        }

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"records": [record.to_json_dict() for record in self._records.values()]}
        fd, tmp_name = tempfile.mkstemp(
            dir=self._path.parent, prefix=".history-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp_name, self._path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def get(self, session_id: str) -> HistoryRecord | None:
        return self._records.get(session_id)

    def was_successful(self, session_id: str) -> bool:
        record = self.get(session_id)
        return record is not None and record.automation_state is AutomationState.SUCCESS

    def record_attempt(
        self,
        session_id: str,
        automation_state: AutomationState,
        error_message: str | None = None,
        now: datetime | None = None,
    ) -> HistoryRecord:
        previous = self._records.get(session_id)
        attempt_count = (previous.attempt_count if previous else 0) + 1
        timestamp = now or datetime.now(timezone.utc)
        record = HistoryRecord(
            session_id=session_id,
            automation_state=automation_state,
            updated_at=timestamp,
            attempt_count=attempt_count,
            error_message=error_message,
        )
        self._records[session_id] = record
        self._save()
        return record

    def all(self) -> tuple[HistoryRecord, ...]:
        return tuple(self._records.values())

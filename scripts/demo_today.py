"""Демонстрационный сценарий этапа 2 (docs/PLAN.md, критерий готовности §16).

Запуск: python scripts/demo_today.py

Ничего не пишет в реальный журнал и не обращается к сайту — только читает
локальную конфигурацию (config/) и локальную историю (docs/SPEC.md, раздел 15).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from journal_automation.app import build_training_service  # noqa: E402


def _ensure_utf8_stdout() -> None:
    # Консоль Windows по умолчанию использует однобайтовую кодировку страницы
    # (cp1251/cp866) и без этого превращает кириллицу в нечитаемые символы.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")


def main() -> None:
    _ensure_utf8_stdout()
    _config, training_service, _history = build_training_service()
    sessions = training_service.get_sessions_for_today()

    if not sessions:
        print("На сегодня тренировок по расписанию нет.")
        return

    for session in sessions:
        decision = training_service.should_process_session(session)
        confirmation = training_service.get_absence_confirmation(session)

        print(f"Занятие: {session.session_id}")
        print(f"  Группа: {session.group.name}")
        print(f"  Время: {session.start_time:%H:%M}-{session.end_time:%H:%M}")
        print(f"  Состояние тренировки: {session.domain_state.value}")
        print(f"  Состояние автоматизации: {session.automation_state.value}")
        print(f"  Обрабатывать сейчас? {decision.should_process} ({decision.reason})")

        if confirmation is None:
            print("  Посещаемость: данных нет")
        elif not confirmation.absences:
            status = "подтверждено, отсутствующих нет" if confirmation.confirmed_complete else "не подтверждена"
            print(f"  Посещаемость: {status}")
        else:
            status = "подтверждено" if confirmation.confirmed_complete else "НЕ подтверждено"
            print(f"  Отсутствуют ({status}):")
            for absence in confirmation.absences:
                print(f"    - {absence.full_name}: {absence.comment}")
        print()


if __name__ == "__main__":
    main()

"""Две независимые оси состояния занятия (docs/ARCHITECTURE.md, раздел 4).

Ось 1 — `TrainingDomainState`: реальный факт о самой тренировке (была ли она,
отменена ли), не имеет отношения к автоматизации журнала.

Ось 2 — `AutomationState`: состояние конвейера автоматизации (что происходит
с попыткой заполнить журнал для этого занятия).

Эти оси нельзя схлопывать в одну: тренировка может состояться (`COMPLETED`),
а автоматизация при этом ещё ждать данных (`WAITING`) или упасть с ошибкой
(`ERROR`) — и наоборот, отменённая тренировка (`CANCELLED`) не должна
запускать автоматизацию вовсе.

Соответствие с русскоязычным жизненным циклом из этапа 1
(docs/ARCHITECTURE.md §4.2), зафиксированное на этапе 2:

| Этап 1 (статус обработки)      | Этап 2 (`AutomationState`) |
|---------------------------------|-----------------------------|
| СОЗДАНО / ОЖИДАНИЕ_ВРЕМЕНИ      | `PENDING`                    |
| ЖДЁТ_ДАННЫХ                     | `WAITING`                    |
| В_ОБРАБОТКЕ / ОТПРАВЛЕНО_НА_СОХРАНЕНИЕ | `RUNNING`             |
| СОХРАНЕНО_ПОДТВЕРЖДЕНО          | `SUCCESS`                    |
| ОШИБКА                          | `ERROR`                      |
| КОНФЛИКТ / РЕЗУЛЬТАТ_НЕИЗВЕСТЕН | `NEEDS_ATTENTION`            |
| ПРОПУЩЕНО_ПО_ВРЕМЕНИ            | `SKIPPED`                    |
| ОТМЕНЕНО                        | (учитывается через `TrainingDomainState.CANCELLED`) |

`NEEDS_ATTENTION` объединяет случаи, требующие взгляда человека, но не
являющиеся жёсткой ошибкой сайта/адаптера (конфликт данных, неизвестный
результат сохранения) — оба допускают контролируемый повтор, в отличие от
`SKIPPED` (см. journal_automation/services/history_manager.py).
"""

from __future__ import annotations

from enum import Enum


class TrainingDomainState(str, Enum):
    UNKNOWN = "unknown"
    PLANNED = "planned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AutomationState(str, Enum):
    PENDING = "pending"
    WAITING = "waiting"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"
    NEEDS_ATTENTION = "needs_attention"

    @property
    def is_terminal_success(self) -> bool:
        return self is AutomationState.SUCCESS

    @property
    def allows_retry(self) -> bool:
        """Состояния, из которых допустим контролируемый повтор (SPEC.md §10).

        SKIPPED сюда намеренно не входит: пропущенное по времени занятие не
        заполняется автоматически задним числом (docs/SPEC.md, раздел 4).
        """

        return self in (AutomationState.ERROR, AutomationState.NEEDS_ATTENTION)

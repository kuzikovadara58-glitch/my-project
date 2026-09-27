"""Отсутствия: сопоставление причины конкретному спортсмену без риска перепутать.

Каждая запись причины/комментария всегда несёт при себе `athlete_id`
(journal_automation/config/models.py: AttendanceRecordConfig) и разрешается
в текст здесь по этому id, а не по позиции в списке — перестановка записей
не может привести к тому, что комментарий одного спортсмена достанется
другому (см. tests/test_absence_resolution.py).

Причины никогда не выбираются случайно и не придумываются — либо ключ
шаблона из absence_reasons.yaml, либо явный текст пользователя
(docs/SPEC.md, раздел 7).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_

from journal_automation.config.models import (
    AbsenceReason,
    AttendanceRecordConfig,
    AttendanceSourceEntry,
    Athlete,
    Group,
)

# Известные пары форм глагола для согласования по роду. Содержание причины
# не меняется — меняется только форма глагола в начале фразы.
_GENDERED_VERB_FORMS: dict[str, str] = {
    "отпросился": "отпросилась",
}


def _apply_gender(text_masculine: str, gender: str | None) -> str:
    if gender != "f":
        return text_masculine
    for masculine, feminine in _GENDERED_VERB_FORMS.items():
        if text_masculine.startswith(masculine):
            return feminine + text_masculine[len(masculine):]
    # Известной формы для согласования нет — используем текст как есть,
    # а не пытаемся угадать словоформу.
    return text_masculine


def resolve_comment(
    record: AttendanceRecordConfig,
    athlete: Athlete,
    absence_reasons: dict[str, AbsenceReason],
) -> str:
    if record.custom_comment is not None:
        return record.custom_comment
    reason = absence_reasons[record.reason_key]
    return _apply_gender(reason.text_masculine, athlete.gender)


@dataclass(frozen=True)
class ResolvedAbsence:
    athlete_id: str
    full_name: str
    comment: str
    reason_key: str | None


@dataclass(frozen=True)
class AbsenceConfirmation:
    """Итог по посещаемости одного занятия — вторая (недоменная) сущность,

    отдельная от постоянного состава группы (docs/SPEC.md, раздел 5) и от
    двух осей состояния занятия (docs/ARCHITECTURE.md §4): описывает именно
    то, что подтвердил пользователь по конкретной дате+группе.
    """

    date: date_
    group_id: str
    confirmed_complete: bool
    absences: tuple[ResolvedAbsence, ...]

    @property
    def has_confirmed_data(self) -> bool:
        """Отличает "подтверждено, отсутствующих нет" от "данных вовсе нет".

        `confirmed_complete=True` с пустым `absences` — это первое; сам факт
        отсутствия объекта `AbsenceConfirmation` для занятия — второе
        (docs/SPEC.md, раздел 6).
        """

        return self.confirmed_complete


def resolve_absence_confirmation(
    entry: AttendanceSourceEntry,
    group: Group,
    absence_reasons: dict[str, AbsenceReason],
) -> AbsenceConfirmation:
    resolved: list[ResolvedAbsence] = []
    for record in entry.absent_athletes:
        athlete = group.athlete_by_id(record.athlete_id)
        if athlete is None:
            # ConfigManager уже должен был это отловить при загрузке; здесь —
            # защитная проверка, а не основной путь валидации.
            raise ValueError(
                f"Спортсмен '{record.athlete_id}' не найден в группе '{group.id}'"
            )
        resolved.append(
            ResolvedAbsence(
                athlete_id=athlete.id,
                full_name=athlete.full_name,
                comment=resolve_comment(record, athlete, absence_reasons),
                reason_key=record.reason_key,
            )
        )
    return AbsenceConfirmation(
        date=entry.date,
        group_id=entry.group_id,
        confirmed_complete=entry.confirmed_complete,
        absences=tuple(resolved),
    )

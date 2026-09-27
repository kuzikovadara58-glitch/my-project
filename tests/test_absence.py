from __future__ import annotations

import pytest

from journal_automation.config.models import AbsenceReason, AttendanceRecordConfig, Athlete
from journal_automation.domain.absence import resolve_comment


REASONS = {
    "family": AbsenceReason(key="family", text_masculine="отпросился с тренировки по семейным обстоятельствам"),
}


def test_masculine_text_used_as_is_for_male_athlete():
    athlete = Athlete(id="a1", full_name="Иван", gender="m")
    record = AttendanceRecordConfig(athlete_id="a1", reason_key="family")

    assert resolve_comment(record, athlete, REASONS) == REASONS["family"].text_masculine


def test_feminine_form_applied_for_female_athlete():
    athlete = Athlete(id="a2", full_name="Мария", gender="f")
    record = AttendanceRecordConfig(athlete_id="a2", reason_key="family")

    result = resolve_comment(record, athlete, REASONS)

    assert result.startswith("отпросилась")
    assert result == "отпросилась с тренировки по семейным обстоятельствам"


def test_unknown_gender_falls_back_to_masculine_text():
    athlete = Athlete(id="a3", full_name="Без пола", gender=None)
    record = AttendanceRecordConfig(athlete_id="a3", reason_key="family")

    assert resolve_comment(record, athlete, REASONS) == REASONS["family"].text_masculine


def test_custom_comment_overrides_template_and_gender():
    athlete = Athlete(id="a2", full_name="Мария", gender="f")
    record = AttendanceRecordConfig(athlete_id="a2", custom_comment="Свой текст без изменений")

    assert resolve_comment(record, athlete, REASONS) == "Свой текст без изменений"


def test_record_requires_exactly_one_of_reason_or_comment():
    with pytest.raises(ValueError):
        AttendanceRecordConfig(athlete_id="a1")

    with pytest.raises(ValueError):
        AttendanceRecordConfig(athlete_id="a1", reason_key="family", custom_comment="и то и то")

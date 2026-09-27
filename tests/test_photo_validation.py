from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from journal_automation.config.models import Group, PhotosSettings
from journal_automation.domain.session import TrainingSession
from journal_automation.domain.states import AutomationState, TrainingDomainState
from journal_automation.photos.models import TrainingPhoto, TrainingPhotoValidationStatus
from journal_automation.photos.validation import is_photo_time_valid, validate_training_photo

MOSCOW = ZoneInfo("Europe/Moscow")
GROUP = Group(id="g1", name="Группа", journal_group_id="", schedule=(), athletes=())


def _session() -> TrainingSession:
    return TrainingSession(
        session_id="2026-09-28:g1:18:00",
        date=date(2026, 9, 28),
        group=GROUP,
        start_time=time(18, 0),
        end_time=time(19, 30),
        domain_state=TrainingDomainState.PLANNED,
        automation_state=AutomationState.PENDING,
    )


def _photo(captured_at) -> TrainingPhoto:
    return TrainingPhoto(
        source="google_drive",
        remote_file_id="f1",
        remote_name="photo.jpg",
        mime_type="image/jpeg",
        captured_at=captured_at,
        datetime_source="exif" if captured_at is not None else "unknown",
    )


def test_is_photo_time_valid_within_window():
    start = datetime(2026, 9, 28, 18, 0, tzinfo=MOSCOW)
    end = datetime(2026, 9, 28, 19, 30, tzinfo=MOSCOW)

    assert is_photo_time_valid(start, start, end, 15, 120) is True
    assert is_photo_time_valid(end, start, end, 15, 120) is True


def test_is_photo_time_valid_too_early():
    start = datetime(2026, 9, 28, 18, 0, tzinfo=MOSCOW)
    end = datetime(2026, 9, 28, 19, 30, tzinfo=MOSCOW)
    too_early = datetime(2026, 9, 28, 17, 30, tzinfo=MOSCOW)  # на 30 мин раньше допуска в 15

    assert is_photo_time_valid(too_early, start, end, 15, 120) is False


def test_is_photo_time_valid_too_late():
    start = datetime(2026, 9, 28, 18, 0, tzinfo=MOSCOW)
    end = datetime(2026, 9, 28, 19, 30, tzinfo=MOSCOW)
    too_late = datetime(2026, 9, 28, 22, 0, tzinfo=MOSCOW)  # позже допуска в 120 мин

    assert is_photo_time_valid(too_late, start, end, 15, 120) is False


def test_validate_training_photo_correct_date_and_time():
    settings = PhotosSettings()
    photo = _photo(datetime(2026, 9, 28, 18, 10, tzinfo=MOSCOW))

    result = validate_training_photo(photo, _session(), MOSCOW, settings)

    assert result.validation_status is TrainingPhotoValidationStatus.VALID
    assert result.validation_errors == ()


def test_validate_training_photo_wrong_date_is_invalid():
    settings = PhotosSettings()
    photo = _photo(datetime(2026, 9, 27, 18, 10, tzinfo=MOSCOW))  # другой день

    result = validate_training_photo(photo, _session(), MOSCOW, settings)

    assert result.validation_status is TrainingPhotoValidationStatus.INVALID
    assert any("дата фото" in error for error in result.validation_errors)


def test_validate_training_photo_missing_capture_time_is_invalid():
    settings = PhotosSettings()
    photo = _photo(None)

    result = validate_training_photo(photo, _session(), MOSCOW, settings)

    assert result.validation_status is TrainingPhotoValidationStatus.INVALID
    assert any("не удалось определить" in error for error in result.validation_errors)


def test_validate_training_photo_naive_datetime_treated_as_app_timezone():
    settings = PhotosSettings()
    photo = _photo(datetime(2026, 9, 28, 18, 10))  # без tzinfo

    result = validate_training_photo(photo, _session(), MOSCOW, settings)

    assert result.validation_status is TrainingPhotoValidationStatus.VALID

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from journal_automation.config.models import Group, PhotosSettings
from journal_automation.domain.session import TrainingSession
from journal_automation.domain.states import AutomationState, TrainingDomainState
from journal_automation.photos.models import PhotoSelectionStatus, TrainingPhoto
from journal_automation.photos.service import PhotoService
from journal_automation.photos.source import CandidateUnavailableError, PhotoSourceUnavailableError
from journal_automation.services.time_service import TimeService
from tests._fake_photo_source import FakePhotoSource, jpeg_bytes

MOSCOW = ZoneInfo("Europe/Moscow")
GROUP = Group(id="kids_1", name="Детская группа", journal_group_id="", schedule=(), athletes=())
SESSION = TrainingSession(
    session_id="2026-09-28:kids_1:18:00",
    date=date(2026, 9, 28),
    group=GROUP,
    start_time=time(18, 0),
    end_time=time(19, 30),
    domain_state=TrainingDomainState.PLANNED,
    automation_state=AutomationState.PENDING,
)


def _photo(file_id: str, name: str) -> TrainingPhoto:
    return TrainingPhoto(source="google_drive", remote_file_id=file_id, remote_name=name, mime_type="image/jpeg")


def _service(source, tmp_path, now=None, settings=None):
    time_service = TimeService("Europe/Moscow", clock=lambda: now or datetime(2026, 9, 28, 18, 5, tzinfo=MOSCOW))
    return PhotoService(source, settings or PhotosSettings(), time_service)


def test_single_valid_candidate_found(tmp_path):
    source = FakePhotoSource([_photo("f1", "kids_1_2026-09-28_18-05.jpg")], tmp_path)
    service = _service(source, tmp_path)

    result = service.get_photo_for_session(SESSION)

    assert result.status is PhotoSelectionStatus.FOUND
    assert result.photo.remote_file_id == "f1"


def test_wrong_date_candidate_filtered_before_download(tmp_path):
    # Имя файла явно указывает на другой день — не должно даже скачиваться.
    source = FakePhotoSource([_photo("f1", "kids_1_2026-09-01_18-05.jpg")], tmp_path)
    service = _service(source, tmp_path, now=datetime(2026, 9, 28, 18, 5, tzinfo=MOSCOW))

    result = service.get_photo_for_session(SESSION)

    assert source.download_calls == []
    assert result.status in (PhotoSelectionStatus.WAITING_FOR_PHOTO, PhotoSelectionStatus.NOT_FOUND)


def test_multiple_candidates_closest_to_start_wins(tmp_path):
    candidates = [
        _photo("far", "kids_1_2026-09-28_19-00.jpg"),
        _photo("close", "kids_1_2026-09-28_18-05.jpg"),
    ]
    source = FakePhotoSource(candidates, tmp_path)
    service = _service(source, tmp_path)

    result = service.get_photo_for_session(SESSION)

    assert result.status is PhotoSelectionStatus.FOUND
    assert result.photo.remote_file_id == "close"


def test_exif_preferred_over_filename_even_at_equal_distance(tmp_path):
    exif_candidate = _photo("exif-one", "unrelated_name.jpg")
    filename_candidate = _photo("filename-one", "kids_1_2026-09-28_18-00.jpg")
    source = FakePhotoSource([exif_candidate, filename_candidate], tmp_path)
    # exif-one несёт настоящий EXIF ровно на начало занятия; filename-one —
    # без EXIF, только по имени файла на то же самое время (равное расстояние).
    source.file_contents["exif-one"] = jpeg_bytes(datetime(2026, 9, 28, 18, 0))
    service = _service(source, tmp_path)

    result = service.get_photo_for_session(SESSION)

    assert result.status is PhotoSelectionStatus.FOUND
    assert result.photo.remote_file_id == "exif-one"
    assert result.photo.datetime_source == "exif"


def test_truly_ambiguous_candidates_return_ambiguous_status(tmp_path):
    candidates = [
        _photo("a", "kids_1_2026-09-28_18-05.jpg"),
        _photo("b", "kids_1_2026-09-28_18-05.jpg"),
    ]
    source = FakePhotoSource(candidates, tmp_path)
    service = _service(source, tmp_path)

    result = service.get_photo_for_session(SESSION)

    assert result.status is PhotoSelectionStatus.AMBIGUOUS
    assert len(result.candidates) == 2


def test_no_candidates_before_deadline_is_waiting(tmp_path):
    source = FakePhotoSource([], tmp_path)
    # До конца занятия (19:30) + wait_for_photo_until_minutes_after_end (30) —
    # дедлайн ещё далеко.
    service = _service(source, tmp_path, now=datetime(2026, 9, 28, 18, 5, tzinfo=MOSCOW))

    result = service.get_photo_for_session(SESSION)

    assert result.status is PhotoSelectionStatus.WAITING_FOR_PHOTO


def test_no_candidates_after_deadline_is_not_found(tmp_path):
    source = FakePhotoSource([], tmp_path)
    settings = PhotosSettings(wait_for_photo_until_minutes_after_end=0)
    # Занятие закончилось в 19:30, дедлайн (offset=0) уже прошёл.
    service = _service(source, tmp_path, now=datetime(2026, 9, 28, 20, 0, tzinfo=MOSCOW), settings=settings)

    result = service.get_photo_for_session(SESSION)

    assert result.status is PhotoSelectionStatus.NOT_FOUND


def test_source_unavailable_short_circuits_without_download(tmp_path):
    source = FakePhotoSource([_photo("f1", "kids_1_2026-09-28_18-05.jpg")], tmp_path)
    source.list_error = PhotoSourceUnavailableError("нет сети")
    service = _service(source, tmp_path)

    result = service.get_photo_for_session(SESSION)

    assert result.status is PhotoSelectionStatus.SOURCE_UNAVAILABLE
    assert source.download_calls == []


def test_vanished_candidate_is_skipped_not_fatal(tmp_path):
    candidates = [
        _photo("vanished", "kids_1_2026-09-28_18-04.jpg"),
        _photo("ok", "kids_1_2026-09-28_18-06.jpg"),
    ]
    source = FakePhotoSource(candidates, tmp_path)
    source.file_contents["vanished"] = CandidateUnavailableError("файл исчез")
    service = _service(source, tmp_path)

    result = service.get_photo_for_session(SESSION)

    assert result.status is PhotoSelectionStatus.FOUND
    assert result.photo.remote_file_id == "ok"


def test_download_cap_limits_number_of_downloads(tmp_path):
    candidates = [_photo(f"f{i}", f"kids_1_2026-09-28_18-{i:02d}.jpg") for i in range(10)]
    source = FakePhotoSource(candidates, tmp_path)
    service = _service(source, tmp_path)
    service._max_candidates_to_download = 3  # type: ignore[attr-defined]

    service.get_photo_for_session(SESSION)

    assert len(source.download_calls) <= 3


def test_drive_timestamp_fallback_disabled_by_default(tmp_path):
    # Нет EXIF, нет разбираемого имени файла, allow_drive_timestamp_fallback=False
    # по умолчанию -> дата/время неизвестны -> не может быть валидным.
    photo = TrainingPhoto(
        source="google_drive",
        remote_file_id="f1",
        remote_name="random_name_without_date.jpg",
        mime_type="image/jpeg",
        remote_created_at=datetime(2026, 9, 28, 18, 5, tzinfo=MOSCOW),
    )
    source = FakePhotoSource([photo], tmp_path)
    service = _service(source, tmp_path)

    result = service.get_photo_for_session(SESSION)

    assert result.status in (PhotoSelectionStatus.WAITING_FOR_PHOTO, PhotoSelectionStatus.NOT_FOUND)


def test_drive_timestamp_fallback_used_when_explicitly_enabled(tmp_path):
    photo = TrainingPhoto(
        source="google_drive",
        remote_file_id="f1",
        remote_name="random_name_without_date.jpg",
        mime_type="image/jpeg",
        remote_created_at=datetime(2026, 9, 28, 18, 5, tzinfo=MOSCOW),
    )
    source = FakePhotoSource([photo], tmp_path)
    settings = PhotosSettings(allow_drive_timestamp_fallback=True)
    service = _service(source, tmp_path, settings=settings)

    result = service.get_photo_for_session(SESSION)

    assert result.status is PhotoSelectionStatus.FOUND
    assert result.photo.datetime_source == "drive_created_time"

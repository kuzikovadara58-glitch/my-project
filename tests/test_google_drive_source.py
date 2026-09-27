from __future__ import annotations

from datetime import date, time

import pytest

from journal_automation.config.models import Group
from journal_automation.domain.session import TrainingSession
from journal_automation.domain.states import AutomationState, TrainingDomainState
from journal_automation.photos.cache import PhotoCache
from journal_automation.photos.google_drive_source import GoogleDrivePhotoSource
from journal_automation.photos.source import CandidateUnavailableError, PhotoSourceUnavailableError
from tests._fake_drive_service import FakeDriveService, FakeFilesResource, make_http_error

GROUP = Group(id="kids_1", name="Детская группа", journal_group_id="", schedule=(), athletes=())


def _session() -> TrainingSession:
    return TrainingSession(
        session_id="2026-09-28:kids_1:18:00",
        date=date(2026, 9, 28),
        group=GROUP,
        start_time=time(18, 0),
        end_time=time(19, 30),
        domain_state=TrainingDomainState.PLANNED,
        automation_state=AutomationState.PENDING,
    )


def _make_source(files_resource, cache_dir, **kwargs):
    service = FakeDriveService(files_resource)
    cache = PhotoCache(cache_dir)
    return GoogleDrivePhotoSource(
        service, folder_id="root-folder", cache=cache, sleep_fn=lambda _s: None, **kwargs
    )


def test_list_candidates_returns_metadata_only(tmp_path):
    files = FakeFilesResource()
    files.set_image_list_result(
        [
            {
                "id": "f1",
                "name": "kids_1_2026-09-28_18-07.jpg",
                "mimeType": "image/jpeg",
                "createdTime": "2026-09-28T18:07:03Z",
                "modifiedTime": "2026-09-28T18:07:03Z",
                "size": "12345",
            }
        ]
    )
    source = _make_source(files, tmp_path)

    candidates = source.list_candidates(_session())

    assert len(candidates) == 1
    photo = candidates[0]
    assert photo.remote_file_id == "f1"
    assert photo.local_path is None  # метаданные не подразумевают скачивание
    assert photo.size_bytes == 12345
    assert photo.remote_created_at is not None


def test_list_candidates_empty_folder_returns_empty_list(tmp_path):
    files = FakeFilesResource()
    files.set_image_list_result([])
    source = _make_source(files, tmp_path)

    assert source.list_candidates(_session()) == []


def test_list_candidates_permission_denied_raises_unavailable(tmp_path):
    files = FakeFilesResource()
    files.set_image_list_error(make_http_error(403))
    source = _make_source(files, tmp_path)

    with pytest.raises(PhotoSourceUnavailableError):
        source.list_candidates(_session())


def test_list_candidates_retries_transient_error_then_succeeds(tmp_path):
    files = FakeFilesResource()
    files.set_image_list_sequence(
        [
            (None, make_http_error(503)),
            (None, make_http_error(503)),
            ({"files": []}, None),
        ]
    )
    source = _make_source(files, tmp_path, max_retries=3, base_backoff_seconds=0.0)

    result = source.list_candidates(_session())

    assert result == []


def test_list_candidates_transient_error_exhausted_raises_unavailable(tmp_path):
    files = FakeFilesResource()
    files.set_image_list_sequence([(None, make_http_error(503))] * 5)
    source = _make_source(files, tmp_path, max_retries=2, base_backoff_seconds=0.0)

    with pytest.raises(PhotoSourceUnavailableError):
        source.list_candidates(_session())


def test_download_photo_writes_file_and_returns_path(tmp_path):
    files = FakeFilesResource()
    files.media_data["f1"] = b"fake-jpeg-bytes"
    source = _make_source(files, tmp_path)
    photo = _minimal_photo()

    path = source.download_photo(photo)

    assert path.is_file()
    assert path.read_bytes() == b"fake-jpeg-bytes"


def test_download_photo_reuses_cache_without_new_api_call(tmp_path):
    files = FakeFilesResource()
    files.media_data["f1"] = b"fake-jpeg-bytes"
    source = _make_source(files, tmp_path)
    photo = _minimal_photo()

    first_path = source.download_photo(photo)
    second_path = source.download_photo(photo)

    assert first_path == second_path
    assert files.get_media_calls == ["f1"]  # второй раз API не вызывался


def test_download_photo_disappeared_between_list_and_download_raises_candidate_unavailable(tmp_path):
    files = FakeFilesResource()
    files.media_errors["f1"] = make_http_error(404)
    source = _make_source(files, tmp_path)
    photo = _minimal_photo()

    with pytest.raises(CandidateUnavailableError):
        source.download_photo(photo)


def test_download_photo_other_error_raises_source_unavailable(tmp_path):
    files = FakeFilesResource()
    files.media_errors["f1"] = make_http_error(403)
    source = _make_source(files, tmp_path)
    photo = _minimal_photo()

    with pytest.raises(PhotoSourceUnavailableError):
        source.download_photo(photo)


def _minimal_photo():
    from journal_automation.photos.models import TrainingPhoto

    return TrainingPhoto(
        source="google_drive", remote_file_id="f1", remote_name="photo.jpg", mime_type="image/jpeg"
    )

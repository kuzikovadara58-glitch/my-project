from __future__ import annotations

from datetime import datetime, timezone

from journal_automation.domain.photo import (
    MIN_FILE_SIZE_BYTES,
    PhotoCandidate,
    PhotoValidationState,
    validate_photo_candidate,
)

SESSION_START = datetime(2026, 9, 28, 18, 0, tzinfo=timezone.utc)
SESSION_END = datetime(2026, 9, 28, 19, 30, tzinfo=timezone.utc)


def _make_file(tmp_path, name="photo.jpg", size=MIN_FILE_SIZE_BYTES + 1) -> "Path":
    path = tmp_path / name
    path.write_bytes(b"x" * size)
    return path


def test_missing_detected_datetime_needs_confirmation(tmp_path):
    path = _make_file(tmp_path)
    candidate = PhotoCandidate.from_file(path, session_id="s1", group_id="g1")

    state = validate_photo_candidate(
        candidate, SESSION_START, SESSION_END, 30, 120, known_hashes_for_session=frozenset()
    )

    assert state is PhotoValidationState.NEEDS_CONFIRMATION


def test_datetime_within_tolerance_confirmed(tmp_path):
    path = _make_file(tmp_path)
    taken_at = SESSION_END  # ровно в момент окончания — в пределах допуска
    candidate = PhotoCandidate.from_file(
        path, session_id="s1", group_id="g1", detected_datetime=taken_at, source_of_datetime="exif"
    )

    state = validate_photo_candidate(
        candidate, SESSION_START, SESSION_END, 30, 120, known_hashes_for_session=frozenset()
    )

    assert state is PhotoValidationState.CONFIRMED


def test_datetime_far_outside_tolerance_needs_confirmation(tmp_path):
    path = _make_file(tmp_path)
    taken_at = datetime(2026, 9, 20, 18, 0, tzinfo=timezone.utc)  # другая тренировка
    candidate = PhotoCandidate.from_file(
        path, session_id="s1", group_id="g1", detected_datetime=taken_at, source_of_datetime="exif"
    )

    state = validate_photo_candidate(
        candidate, SESSION_START, SESSION_END, 30, 120, known_hashes_for_session=frozenset()
    )

    assert state is PhotoValidationState.NEEDS_CONFIRMATION


def test_naive_detected_datetime_needs_confirmation(tmp_path):
    path = _make_file(tmp_path)
    naive = datetime(2026, 9, 28, 18, 30)
    candidate = PhotoCandidate.from_file(
        path, session_id="s1", group_id="g1", detected_datetime=naive, source_of_datetime="exif"
    )

    state = validate_photo_candidate(
        candidate, SESSION_START, SESSION_END, 30, 120, known_hashes_for_session=frozenset()
    )

    assert state is PhotoValidationState.NEEDS_CONFIRMATION


def test_wrong_extension_rejected(tmp_path):
    path = _make_file(tmp_path, name="photo.gif")
    candidate = PhotoCandidate.from_file(path, session_id="s1", group_id="g1")

    state = validate_photo_candidate(
        candidate, SESSION_START, SESSION_END, 30, 120, known_hashes_for_session=frozenset()
    )

    assert state is PhotoValidationState.REJECTED


def test_too_small_file_rejected(tmp_path):
    path = _make_file(tmp_path, size=10)
    candidate = PhotoCandidate.from_file(path, session_id="s1", group_id="g1")

    state = validate_photo_candidate(
        candidate, SESSION_START, SESSION_END, 30, 120, known_hashes_for_session=frozenset()
    )

    assert state is PhotoValidationState.REJECTED


def test_duplicate_hash_rejected(tmp_path):
    path = _make_file(tmp_path)
    candidate = PhotoCandidate.from_file(
        path, session_id="s1", group_id="g1", detected_datetime=SESSION_START, source_of_datetime="exif"
    )

    state = validate_photo_candidate(
        candidate,
        SESSION_START,
        SESSION_END,
        30,
        120,
        known_hashes_for_session=frozenset({candidate.file_hash}),
    )

    assert state is PhotoValidationState.REJECTED

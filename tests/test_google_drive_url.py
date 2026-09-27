from __future__ import annotations

import pytest

from journal_automation.photos.google_drive_url import (
    InvalidGoogleDriveFolderReference,
    extract_folder_id,
)

FOLDER_ID = "1A2b3C4d5E6f7G8h9I0jKlMnOpQrStUv"


@pytest.mark.parametrize(
    "url",
    [
        f"https://drive.google.com/drive/folders/{FOLDER_ID}",
        f"https://drive.google.com/drive/folders/{FOLDER_ID}?usp=sharing",
        f"https://drive.google.com/drive/u/0/folders/{FOLDER_ID}",
        f"https://drive.google.com/open?id={FOLDER_ID}",
        FOLDER_ID,
    ],
)
def test_extract_folder_id_supported_formats(url):
    assert extract_folder_id(url) == FOLDER_ID


def test_empty_value_raises():
    with pytest.raises(InvalidGoogleDriveFolderReference):
        extract_folder_id("")

    with pytest.raises(InvalidGoogleDriveFolderReference):
        extract_folder_id("   ")


def test_unrecognized_url_raises():
    with pytest.raises(InvalidGoogleDriveFolderReference):
        extract_folder_id("https://example.com/not-a-drive-link")


def test_too_short_bare_value_raises():
    with pytest.raises(InvalidGoogleDriveFolderReference):
        extract_folder_id("abc")

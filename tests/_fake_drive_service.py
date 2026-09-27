"""Дублёр googleapiclient Drive-сервиса для юнит-тестов (не тестовый файл сам

по себе). Не обращается к интернету — реализует ровно тот же интерфейс
(`.files().list(...).execute()` / `.files().get_media(fileId=...).execute()`),
что и настоящий `googleapiclient.discovery.Resource`.
"""

from __future__ import annotations

import httplib2
from googleapiclient.errors import HttpError


def make_http_error(status: int) -> HttpError:
    return HttpError(httplib2.Response({"status": status}), b'{"error": "test"}')


class _FakeRequest:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    def execute(self):
        if self._error is not None:
            raise self._error
        return self._result


class FakeFilesResource:
    def __init__(self) -> None:
        self.folder_lookup_result: dict = {"files": []}  # по умолчанию нет подпапки группы
        # Каждый вызов list() для основного запроса файлов (не подпапки)
        # берёт следующий элемент очереди; если очередь пуста — берётся
        # последний заданный элемент повторно (удобно для однократных тестов).
        self._image_list_queue: list[tuple[dict | None, Exception | None]] = [({"files": []}, None)]
        self.media_data: dict[str, bytes] = {}
        self.media_errors: dict[str, Exception] = {}
        self.list_calls: list[str] = []
        self.get_media_calls: list[str] = []

    def set_image_list_result(self, files: list[dict]) -> None:
        self._image_list_queue = [({"files": files}, None)]

    def set_image_list_error(self, error: Exception) -> None:
        self._image_list_queue = [(None, error)]

    def set_image_list_sequence(self, sequence: list[tuple[dict | None, Exception | None]]) -> None:
        self._image_list_queue = list(sequence)

    def list(self, q: str, fields: str | None = None, pageSize: int | None = None):
        self.list_calls.append(q)
        if "application/vnd.google-apps.folder" in q:
            return _FakeRequest(result=self.folder_lookup_result)

        if len(self._image_list_queue) > 1:
            result, error = self._image_list_queue.pop(0)
        else:
            result, error = self._image_list_queue[0]
        return _FakeRequest(result=result, error=error)

    def get_media(self, fileId: str):
        self.get_media_calls.append(fileId)
        if fileId in self.media_errors:
            return _FakeRequest(error=self.media_errors[fileId])
        return _FakeRequest(result=self.media_data.get(fileId, b""))


class FakeDriveService:
    def __init__(self, files_resource: FakeFilesResource) -> None:
        self._files_resource = files_resource

    def files(self) -> FakeFilesResource:
        return self._files_resource

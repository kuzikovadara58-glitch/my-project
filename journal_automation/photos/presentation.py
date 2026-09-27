"""Единое текстовое представление результата подбора фото для GUI и логов

(docs/SPEC.md, этап 4, раздел 25). Один источник форматирования — чтобы
планировщик (проверка в фоне) и ручная кнопка «Проверить фото» в GUI
показывали одинаковый текст для одинакового результата.
"""

from __future__ import annotations

from journal_automation.photos.models import PhotoSelectionResult, PhotoSelectionStatus


def format_photo_status(result: PhotoSelectionResult) -> str:
    if result.status is PhotoSelectionStatus.FOUND:
        name = result.photo.remote_name if result.photo else "?"
        return f"✅ найдено: {name}"
    if result.status is PhotoSelectionStatus.WAITING_FOR_PHOTO:
        return "🕐 ожидание (Google Drive)"
    if result.status is PhotoSelectionStatus.NOT_FOUND:
        return "⚠ не найдено"
    if result.status is PhotoSelectionStatus.SOURCE_UNAVAILABLE:
        return "❌ Google Drive недоступен"
    if result.status is PhotoSelectionStatus.AMBIGUOUS:
        names = ", ".join(p.remote_name for p in result.candidates) or "?"
        return f"⚠ найдено несколько подходящих фотографий: {names}"
    return result.message or "—"

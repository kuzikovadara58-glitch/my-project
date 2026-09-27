"""Источник фотографий для занятия (Google Drive) — этап 4.

Пакет намеренно не переэкспортирует всё через `__init__.py`: код,
которому не нужен Google API (например `journal_automation.config.manager`,
которому нужен только разбор ссылки), импортирует конкретный лёгкий модуль
(`journal_automation.photos.google_drive_url`), а не тянет за собой
googleapiclient/Pillow только ради разбора URL.
"""

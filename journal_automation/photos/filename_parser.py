"""Разбор рекомендуемого формата имени файла (docs/SPEC.md, этап 4, раздел 14).

Поддерживаются ровно два формата, без попытки угадывать произвольные имена:

    ГГГГ-ММ-ДД_ЧЧ-ММ.<ext>                например 2026-09-28_18-07.jpg
    <group_id>_ГГГГ-ММ-ДД_ЧЧ-ММ.<ext>     например kids_1_2026-09-28_18-07.jpg

Возвращаемое время наивное (без часового пояса) — имя файла не несёт
информации о часовом поясе съёмки; вызывающий код сопоставляет его с
часовым поясом приложения, как и время из расписания (этап 2).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath

_DATE_TIME = r"(?P<date>\d{4}-\d{2}-\d{2})_(?P<time>\d{2}-\d{2})"
_PATTERN_WITH_GROUP = re.compile(rf"^(?P<group>[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*)_{_DATE_TIME}$")
_PATTERN_PLAIN = re.compile(rf"^{_DATE_TIME}$")


def parse_filename(filename: str) -> tuple[datetime | None, str | None]:
    """Возвращает (наивное_время_съёмки, group_id) — оба `None`, если имя не

    соответствует ни одному из двух поддерживаемых форматов.
    """

    stem = PurePosixPath(filename).stem

    match = _PATTERN_WITH_GROUP.match(stem)
    if match:
        parsed = _parse_datetime(match["date"], match["time"])
        return parsed, (match["group"] if parsed is not None else None)

    match = _PATTERN_PLAIN.match(stem)
    if match:
        return _parse_datetime(match["date"], match["time"]), None

    return None, None


def _parse_datetime(date_part: str, time_part: str) -> datetime | None:
    try:
        return datetime.strptime(f"{date_part}_{time_part}", "%Y-%m-%d_%H-%M")
    except ValueError:
        return None

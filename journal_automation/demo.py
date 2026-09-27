"""Изолированный контекст для `python main.py --demo` (этап 3, раздел 13).

Не читает config/ и не пишет в реальную пользовательскую историю — группа,
расписание и история полностью синтетические и живут во временном каталоге,
который не переживает завершение процесса. Расписание намеренно рассчитано
от текущего момента (а не от дня недели из реального конфига), чтобы первое
занятие наступало через несколько секунд, а не через несколько часов/дней.
"""

from __future__ import annotations

import tempfile
from datetime import timedelta
from pathlib import Path

from journal_automation.app import AppContext
from journal_automation.config.manager import LoadedConfig
from journal_automation.config.models import (
    AppConfig,
    Athlete,
    AutomationSettings,
    Group,
    PathsSettings,
    TrainingSchedule,
)
from journal_automation.paths import AppPaths
from journal_automation.services.history_manager import HistoryManager
from journal_automation.services.time_service import TimeService
from journal_automation.services.training_service import TrainingService

DEMO_TIMEZONE = "Europe/Moscow"

# Через сколько секунд от запуска наступает первое/второе демо-занятие и
# сколько условно "длится" каждое (docs/PLAN.md, этап 3, критерий готовности).
#
# ВАЖНО: session_id строится с точностью до минуты (HH:MM, docs/SPEC.md,
# раздел 8 этапа 2) — это корректно для реального расписания (там соседние
# занятия всегда различаются минимум на минуты), но для демо-режима два
# занятия должны попасть в РАЗНЫЕ минуты, иначе у них совпадёт session_id и
# второе будет считаться уже обработанным первым. Разрыв заведомо больше 60
# секунд гарантирует переход через границу минуты при любом стартовом моменте.
_FIRST_SESSION_OFFSET_SECONDS = 5.0
_SECOND_SESSION_OFFSET_SECONDS = _FIRST_SESSION_OFFSET_SECONDS + 65.0
_SESSION_DURATION_SECONDS = 2.0


def build_demo_app_context() -> AppContext:
    tmp_root = Path(tempfile.mkdtemp(prefix="journal-automation-demo-"))
    paths = AppPaths(user_data_root=tmp_root, config_dir=tmp_root / "config")

    time_service = TimeService(DEMO_TIMEZONE)  # реальные часы, не подменяются
    now = time_service.now()
    today = now.date()

    def offset_rule(seconds_from_now: float) -> TrainingSchedule:
        start_dt = now + timedelta(seconds=seconds_from_now)
        end_dt = start_dt + timedelta(seconds=_SESSION_DURATION_SECONDS)
        return TrainingSchedule(weekday=today.weekday(), start=start_dt.time(), end=end_dt.time())

    demo_group = Group(
        id="demo_group",
        name="Демо-группа",
        journal_group_id="",
        schedule=(
            offset_rule(_FIRST_SESSION_OFFSET_SECONDS),
            offset_rule(_SECOND_SESSION_OFFSET_SECONDS),
        ),
        athletes=(Athlete(id="demo_athlete", full_name="Демо Спортсмен", gender="m"),),
    )

    # fill_after_start_minutes=0 даёт секундную точность запуска обработки —
    # занятие считается "готовым" сразу в момент своего начала.
    automation = AutomationSettings(fill_after_start_minutes=0, fill_after_end_minutes=10)
    app_config = AppConfig(timezone=DEMO_TIMEZONE, automation=automation, paths=PathsSettings())
    config = LoadedConfig(
        app=app_config,
        groups={"demo_group": demo_group},
        absence_reasons={},
        attendance=(),
    )

    history = HistoryManager(tmp_root / "history.json")
    training_service = TrainingService(config, time_service, history)

    return AppContext(
        paths=paths,
        config=config,
        time_service=time_service,
        history=history,
        training_service=training_service,
    )

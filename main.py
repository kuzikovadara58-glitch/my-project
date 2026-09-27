"""Точка входа desktop-приложения (docs/PLAN.md, этапы 3-4).

Запуск:
    python main.py                                 обычный режим (config/, реальная история)
    python main.py --demo                          демо-режим, фото "находится" сразу
    python main.py --demo --simulate-error          демо с ошибкой mock-обработки занятия
    python main.py --demo --simulate-photo-missing  демо: фото не появляется в Google Drive
    python main.py --demo --simulate-drive-error    демо: Google Drive недоступен
    python main.py --demo --simulate-photo-ambiguous демо: несколько подходящих фото

Реальный электронный журнал на этом этапе не подключается ни в одном из
режимов — обработка занятий выполняется MockJournalAutomation
(docs/SPEC.md, этап 3, раздел 15). Реальный Google Drive в demo-режиме тоже
не используется ни в одном сценарии (этап 4, раздел 30).
"""

from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from journal_automation.app import AppContext, build_app_context
from journal_automation.automation.mock import MockJournalAutomation
from journal_automation.demo import build_demo_app_context
from journal_automation.gui.main_window import MainWindow
from journal_automation.logging_setup import configure_logging
from journal_automation.scheduler.controller import AutomationController


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Электронный журнал — автоматизация")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="демонстрационный режим на временных данных (занятие через несколько секунд)",
    )
    parser.add_argument(
        "--simulate-error",
        action="store_true",
        help="только вместе с --demo: имитировать ошибку обработки занятия",
    )

    photo_group = parser.add_mutually_exclusive_group()
    photo_group.add_argument(
        "--simulate-photo-missing",
        action="store_true",
        help="только вместе с --demo: фото не появляется в Google Drive",
    )
    photo_group.add_argument(
        "--simulate-drive-error",
        action="store_true",
        help="только вместе с --demo: Google Drive недоступен",
    )
    photo_group.add_argument(
        "--simulate-photo-ambiguous",
        action="store_true",
        help="только вместе с --demo: несколько одинаково подходящих фото",
    )

    args = parser.parse_args(argv)
    if not args.demo and (
        args.simulate_error
        or args.simulate_photo_missing
        or args.simulate_drive_error
        or args.simulate_photo_ambiguous
    ):
        parser.error("флаги --simulate-* допустимы только вместе с --demo")
    return args


def _demo_photo_mode(args: argparse.Namespace) -> str:
    if args.simulate_photo_missing:
        return "missing"
    if args.simulate_drive_error:
        return "error"
    if args.simulate_photo_ambiguous:
        return "ambiguous"
    return "success"


def build_context(args: argparse.Namespace) -> AppContext:
    if args.demo:
        return build_demo_app_context(photo_mode=_demo_photo_mode(args))
    return build_app_context()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    context = build_context(args)

    log_dir = context.paths.resolve_configured_path(context.config.app.paths.logs)
    logger = configure_logging(log_dir)
    logger.info(
        "Application started (demo=%s, simulate_error=%s, photo_mode=%s)",
        args.demo, args.simulate_error, _demo_photo_mode(args) if args.demo else "n/a",
    )

    app = QApplication(sys.argv)

    automation_port = MockJournalAutomation(simulate_error=args.simulate_error)
    controller = AutomationController(
        training_service=context.training_service,
        history=context.history,
        automation_port=automation_port,
        time_service=context.time_service,
        automation_settings=context.config.app.automation,
        idle_poll_seconds=5.0 if args.demo else 30.0,
        photo_service=context.photo_service,
        photo_recheck_seconds=float(context.config.app.photos.recheck_interval_seconds),
    )

    window = MainWindow(
        context.training_service, controller, context.config, context.time_service,
        photo_service=context.photo_service,
    )
    window.show()

    exit_code = app.exec()

    logger.info("Application closed")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

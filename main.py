"""Точка входа desktop-приложения (docs/PLAN.md, этап 3).

Запуск:
    python main.py                            обычный режим (config/, реальная история)
    python main.py --demo                     демо-режим на временных данных
    python main.py --demo --simulate-error    демо с намеренной ошибкой mock-обработки

Реальный электронный журнал на этом этапе не подключается ни в одном из
режимов — обработка занятий выполняется MockJournalAutomation
(docs/SPEC.md, этап 3, раздел 15).
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
        help="демонстрационный режим на временных данных (занятия через несколько секунд)",
    )
    parser.add_argument(
        "--simulate-error",
        action="store_true",
        help="только вместе с --demo: имитировать ошибку обработки занятия",
    )
    args = parser.parse_args(argv)
    if args.simulate_error and not args.demo:
        parser.error("--simulate-error допустим только вместе с --demo")
    return args


def build_context(args: argparse.Namespace) -> AppContext:
    if args.demo:
        return build_demo_app_context()
    return build_app_context()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    context = build_context(args)

    log_dir = context.paths.resolve_configured_path(context.config.app.paths.logs)
    logger = configure_logging(log_dir)
    logger.info("Application started (demo=%s, simulate_error=%s)", args.demo, args.simulate_error)

    app = QApplication(sys.argv)

    automation_port = MockJournalAutomation(simulate_error=args.simulate_error)
    controller = AutomationController(
        training_service=context.training_service,
        history=context.history,
        automation_port=automation_port,
        time_service=context.time_service,
        automation_settings=context.config.app.automation,
        idle_poll_seconds=5.0 if args.demo else 30.0,
    )

    window = MainWindow(
        context.training_service, controller, context.config, context.time_service
    )
    window.show()

    exit_code = app.exec()

    logger.info("Application closed")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

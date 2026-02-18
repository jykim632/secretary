"""Entry point: starts all services (Telegram, Slack, Reminder Engine)."""

import asyncio
import logging
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.settings import settings

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ── Logging ────────────────────────────────────────────────


def setup_logging() -> None:
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    fh = RotatingFileHandler(
        log_dir / "secretary.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    fh.setFormatter(formatter)
    fh.setLevel(logging.INFO)

    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    ch.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(fh)
    root.addHandler(ch)

    # Quiet noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)


# ── Main ───────────────────────────────────────────────────


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Family Secretary...")

    from secretary.models.database import init_db

    await init_db()
    logger.info("Database initialized")

    tasks: list[asyncio.Task] = []

    # Start Telegram bot
    telegram_bot = None
    if settings.telegram_bot_token:
        from secretary.platforms.telegram_bot import TelegramBot

        telegram_bot = TelegramBot()
        await telegram_bot.start()
        logger.info("Telegram bot started")

        # Register as notification sender
        from secretary.services.notification_service import notification_service

        notification_service.register_sender("telegram", telegram_bot)

    # Start Slack bot
    slack_bot = None
    if settings.slack_bot_token and settings.slack_app_token:
        from secretary.platforms.slack_bot import SlackBot

        slack_bot = SlackBot()
        tasks.append(asyncio.create_task(_run_slack(slack_bot)))
        logger.info("Slack bot starting...")

        from secretary.services.notification_service import notification_service

        notification_service.register_sender("slack", slack_bot)

    # Start Reminder Engine
    from secretary.scheduler.reminder_engine import reminder_engine

    await reminder_engine.start()
    logger.info("Reminder engine started")

    # Wait for shutdown signal
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    logger.info("Family Secretary is running! Press Ctrl+C to stop.")
    await stop_event.wait()

    # Cleanup
    logger.info("Shutting down...")
    await reminder_engine.stop()
    if telegram_bot:
        await telegram_bot.stop()
    if slack_bot:
        await slack_bot.stop()
    for t in tasks:
        t.cancel()

    from secretary.agent.brain import agent_brain

    await agent_brain.close_all()
    logger.info("Goodbye!")


async def _run_slack(slack_bot) -> None:
    await slack_bot.start()


if __name__ == "__main__":
    asyncio.run(main())

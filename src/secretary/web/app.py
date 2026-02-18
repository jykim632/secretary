"""Web dashboard application — FastAPI app creation and component injection."""

import time
from typing import Any

from fastapi import FastAPI

_start_time: float = time.time()
_telegram_bot: Any = None
_slack_bot: Any = None
_reminder_engine: Any = None


def set_components(
    telegram_bot: Any = None,
    slack_bot: Any = None,
    reminder_engine: Any = None,
) -> None:
    """main.py에서 봇/엔진 참조를 주입한다."""
    global _telegram_bot, _slack_bot, _reminder_engine
    _telegram_bot = telegram_bot
    _slack_bot = slack_bot
    _reminder_engine = reminder_engine


def create_app() -> FastAPI:
    """FastAPI 인스턴스를 생성하고 라우터를 마운트한다."""
    app = FastAPI(title="Secretary Dashboard", docs_url=None, redoc_url=None)

    from secretary.web.routes import router

    app.include_router(router)
    return app

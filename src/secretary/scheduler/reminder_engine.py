"""APScheduler-based reminder engine. Polls every 30 seconds for due reminders."""

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from secretary.models.database import async_session
from secretary.services.calendar_service import get_due_reminders, mark_delivered
from secretary.services.notification_service import notification_service

logger = logging.getLogger(__name__)


class ReminderEngine:
    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None

    async def start(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._check_reminders,
            trigger=IntervalTrigger(seconds=30),
            id="reminder_check",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info("Reminder engine started (30s interval)")

    async def stop(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)

    async def _check_reminders(self) -> None:
        """Check for due reminders and send notifications."""
        try:
            async with async_session() as session:
                reminders = await get_due_reminders(session, datetime.now())
                for reminder in reminders:
                    text = f"⏰ 리마인더: {reminder.message}"
                    sent = await notification_service.notify_user(
                        session, reminder.user_id, text
                    )
                    if sent:
                        await mark_delivered(session, reminder.id)
                        logger.info(
                            "Delivered reminder #%d to user_id=%d",
                            reminder.id, reminder.user_id,
                        )
                    else:
                        logger.warning(
                            "Failed to deliver reminder #%d to user_id=%d",
                            reminder.id, reminder.user_id,
                        )
        except Exception:
            logger.exception("Error in reminder check")


reminder_engine = ReminderEngine()

"""APScheduler-based reminder engine. Polls every 30 seconds for due reminders."""

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
        """Check for due reminders and send notifications.

        반복 리마인더의 경우 mark_delivered()가 다음 알림 시간을 재설정한다.
        """
        try:
            async with async_session() as session:
                reminders = await get_due_reminders(session, datetime.now())
                for reminder in reminders:
                    # 반복 리마인더인 경우 반복 정보 표시
                    recur_label = ""
                    if reminder.is_recurring and reminder.recurrence_rule:
                        rule_labels = {
                            "daily": "매일",
                            "weekly": "매주",
                            "monthly": "매월",
                        }
                        label = rule_labels.get(
                            reminder.recurrence_rule.strip().lower(),
                            reminder.recurrence_rule,
                        )
                        recur_label = f" (반복: {label})"

                    text = f"⏰ 리마인더: {reminder.message}{recur_label}"
                    sent = await notification_service.notify_user(session, reminder.user_id, text)
                    if sent:
                        await mark_delivered(session, reminder.id)
                        if reminder.is_recurring and reminder.recurrence_rule:
                            # 세션을 refresh하여 갱신된 remind_at 확인
                            await session.refresh(reminder)
                            if not reminder.is_delivered:
                                logger.info(
                                    "Recurring reminder #%d delivered to user_id=%d, "
                                    "next at %s (rule=%s, delivered_count=%d)",
                                    reminder.id,
                                    reminder.user_id,
                                    reminder.remind_at,
                                    reminder.recurrence_rule,
                                    reminder.delivered_count,
                                )
                            else:
                                logger.info(
                                    "Recurring reminder #%d final delivery to user_id=%d "
                                    "(recurrence ended, delivered_count=%d)",
                                    reminder.id,
                                    reminder.user_id,
                                    reminder.delivered_count,
                                )
                        else:
                            logger.info(
                                "Delivered reminder #%d to user_id=%d",
                                reminder.id,
                                reminder.user_id,
                            )
                    else:
                        logger.warning(
                            "Failed to deliver reminder #%d to user_id=%d",
                            reminder.id,
                            reminder.user_id,
                        )
        except Exception:
            logger.exception("Error in reminder check")


reminder_engine = ReminderEngine()

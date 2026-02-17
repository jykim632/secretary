"""Cross-platform notification service.

Sends messages to users via their linked platform(s).
"""

import logging
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from secretary.models.user import UserPlatformLink

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PlatformSender(Protocol):
    async def send_message(self, platform_user_id: str, text: str) -> None: ...


class NotificationService:
    def __init__(self) -> None:
        self._senders: dict[str, PlatformSender] = {}

    def register_sender(self, platform: str, sender: PlatformSender) -> None:
        self._senders[platform] = sender

    async def notify_user(self, session: AsyncSession, user_id: int, text: str) -> bool:
        """Send a message to a user via their primary platform."""
        stmt = (
            select(UserPlatformLink)
            .where(UserPlatformLink.user_id == user_id)
            .order_by(UserPlatformLink.is_primary.desc())
        )
        result = await session.execute(stmt)
        links = list(result.scalars().all())

        if not links:
            logger.warning("No platform links for user_id=%d", user_id)
            return False

        # Try primary platform first, then fallback
        for link in links:
            sender = self._senders.get(link.platform)
            if sender:
                try:
                    await sender.send_message(link.platform_user_id, text)
                    return True
                except Exception:
                    logger.exception(
                        "Failed to send via %s to user_id=%d", link.platform, user_id
                    )
                    continue

        logger.error("All platform sends failed for user_id=%d", user_id)
        return False


# Singleton
notification_service = NotificationService()

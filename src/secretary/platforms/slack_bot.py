"""Slack bot using slack-bolt async (Socket Mode)."""

import logging

from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

from config.settings import settings
from secretary.agent.brain import agent_brain
from secretary.models.database import async_session, init_db
from secretary.models.user import FamilyGroup
from secretary.platforms.base import PlatformAdapter
from secretary.services.user_service import get_or_create_user, get_user_by_platform

logger = logging.getLogger(__name__)


class SlackBot(PlatformAdapter):
    def __init__(self) -> None:
        self._app: AsyncApp | None = None
        self._handler: AsyncSocketModeHandler | None = None

    async def start(self) -> None:
        await init_db()

        self._app = AsyncApp(token=settings.slack_bot_token)
        self._register_handlers()

        self._handler = AsyncSocketModeHandler(self._app, settings.slack_app_token)
        logger.info("Slack bot starting (Socket Mode)...")
        await self._handler.start_async()

    async def stop(self) -> None:
        if self._handler:
            await self._handler.close_async()

    async def send_message(self, platform_user_id: str, text: str) -> None:
        if self._app:
            await self._app.client.chat_postMessage(
                channel=platform_user_id,
                text=text,
            )

    def _register_handlers(self) -> None:
        if not self._app:
            return

        @self._app.event("app_mention")
        async def handle_mention(event, say):
            await self._process_message(event, say)

        @self._app.event("message")
        async def handle_dm(event, say):
            # Only respond to DMs (channel type "im")
            if event.get("channel_type") == "im":
                await self._process_message(event, say)

    async def _process_message(self, event: dict, say) -> None:
        slack_user_id = event.get("user", "")
        text = event.get("text", "").strip()

        if not text or not slack_user_id:
            return

        # Remove bot mention if present
        if text.startswith("<@"):
            text = text.split(">", 1)[-1].strip()

        async with async_session() as session:
            # Get Slack user info for display name
            user = await get_or_create_user(
                session,
                platform="slack",
                platform_user_id=slack_user_id,
                display_name=slack_user_id,  # Will be updated later
            )

            from secretary.models.conversation import ConversationHistory

            session.add(ConversationHistory(
                user_id=user.id,
                role="user",
                content=text,
                platform="slack",
            ))
            await session.commit()

            family_group = await session.get(FamilyGroup, user.family_group_id)
            family_name = family_group.name if family_group else settings.default_family_name

        try:
            response = await agent_brain.process_message(
                user_id=user.id,
                family_group_id=user.family_group_id,
                user_name=user.display_name,
                family_name=family_name,
                timezone=user.timezone,
                message=text,
            )
        except Exception:
            logger.exception("Agent error for user_id=%d", user.id)
            response = "죄송합니다, 처리 중 오류가 발생했습니다."

        async with async_session() as session:
            from secretary.models.conversation import ConversationHistory

            session.add(ConversationHistory(
                user_id=user.id,
                role="assistant",
                content=response,
                platform="slack",
            ))
            await session.commit()

        await say(response)

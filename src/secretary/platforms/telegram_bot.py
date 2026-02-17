"""Telegram bot using python-telegram-bot (polling mode)."""

import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config.settings import settings
from secretary.agent.brain import agent_brain
from secretary.models.database import async_session, init_db
from secretary.models.user import FamilyGroup
from secretary.platforms.base import PlatformAdapter
from secretary.services.user_service import get_or_create_user

logger = logging.getLogger(__name__)


class TelegramBot(PlatformAdapter):
    def __init__(self) -> None:
        self._app: Application | None = None

    async def start(self) -> None:
        await init_db()

        self._app = (
            Application.builder()
            .token(settings.telegram_bot_token)
            .build()
        )

        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("reset", self._handle_reset))
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )

        logger.info("Telegram bot starting (polling)...")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

    async def stop(self) -> None:
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def send_message(self, platform_user_id: str, text: str) -> None:
        if self._app:
            await self._app.bot.send_message(
                chat_id=int(platform_user_id),
                text=text,
            )

    # ── Handlers ───────────────────────────────────────────

    async def _handle_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        tg_user = update.effective_user
        if not tg_user:
            return
        async with async_session() as session:
            user = await get_or_create_user(
                session,
                platform="telegram",
                platform_user_id=str(tg_user.id),
                display_name=tg_user.full_name or tg_user.first_name,
            )
            role_msg = " (관리자)" if user.role == "admin" else ""
            await update.message.reply_text(
                f"안녕하세요, {user.display_name}님{role_msg}! 🏠\n"
                f"가족 비서입니다. 무엇을 도와드릴까요?\n\n"
                f"메모, 할일, 일정, 리마인더 등을 관리해드려요."
            )

    async def _handle_reset(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Reset the AI session for this user."""
        tg_user = update.effective_user
        if not tg_user:
            return
        async with async_session() as session:
            from secretary.services.user_service import get_user_by_platform

            user = await get_user_by_platform(session, "telegram", str(tg_user.id))
            if user:
                await agent_brain.reset_session(user.id)
                await update.message.reply_text("대화가 초기화되었습니다. 새로 시작할게요! 🔄")

    async def _handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        tg_user = update.effective_user
        if not tg_user or not update.message or not update.message.text:
            return

        async with async_session() as session:
            user = await get_or_create_user(
                session,
                platform="telegram",
                platform_user_id=str(tg_user.id),
                display_name=tg_user.full_name or tg_user.first_name,
            )

            # Save user message to conversation history
            from secretary.models.conversation import ConversationHistory

            session.add(ConversationHistory(
                user_id=user.id,
                role="user",
                content=update.message.text,
                platform="telegram",
            ))
            await session.commit()

            # Get family info
            family_group = await session.get(FamilyGroup, user.family_group_id)
            family_name = family_group.name if family_group else settings.default_family_name

        # Process through agent brain
        try:
            response = await agent_brain.process_message(
                user_id=user.id,
                family_group_id=user.family_group_id,
                user_name=user.display_name,
                family_name=family_name,
                timezone=user.timezone,
                message=update.message.text,
            )
        except Exception:
            logger.exception("Agent error for user_id=%d", user.id)
            response = "죄송합니다, 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."

        # Save assistant response
        async with async_session() as session:
            session.add(ConversationHistory(
                user_id=user.id,
                role="assistant",
                content=response,
                platform="telegram",
            ))
            await session.commit()

        await update.message.reply_text(response)

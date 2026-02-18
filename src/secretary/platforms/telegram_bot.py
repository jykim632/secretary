"""Telegram bot using python-telegram-bot (polling mode)."""

import asyncio
import logging
import re

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

# 텔레그램 메시지 최대 길이
TELEGRAM_MAX_LENGTH = 4096

# 청크 사이 전송 딜레이 (초) — 순서 보장용
CHUNK_SEND_DELAY = 0.3


def split_message(text: str, max_length: int = TELEGRAM_MAX_LENGTH) -> list[str]:
    """긴 텍스트를 텔레그램 메시지 제한에 맞게 분할한다.

    분할 우선순위:
    1. 코드 블록(```) 경계를 존중한다.
    2. 빈 줄(문단) 경계로 분할한다.
    3. 줄 단위로 분할한다 (최후 수단).
    """
    if len(text) <= max_length:
        return [text]

    # 코드 블록을 인식하면서 문단 단위로 분리
    segments = _split_into_segments(text)
    chunks: list[str] = []
    current = ""

    for segment in segments:
        # 현재 청크에 세그먼트를 추가해도 제한 이내인 경우
        candidate = current + segment if current else segment
        if len(candidate) <= max_length:
            current = candidate
            continue

        # 현재 청크가 비어있지 않으면 먼저 저장
        if current:
            chunks.append(current)
            current = ""

        # 세그먼트 자체가 제한을 초과하면 줄 단위로 분할
        if len(segment) > max_length:
            sub_chunks = _split_segment_by_lines(segment, max_length)
            # 마지막 조각은 다음 세그먼트와 합칠 수 있으므로 current에 보관
            for sc in sub_chunks[:-1]:
                chunks.append(sc)
            current = sub_chunks[-1] if sub_chunks else ""
        else:
            current = segment

    if current:
        chunks.append(current)

    return chunks


def _split_into_segments(text: str) -> list[str]:
    """텍스트를 코드 블록과 일반 텍스트 세그먼트로 분리한다.

    코드 블록은 하나의 세그먼트로 유지하고, 일반 텍스트는 빈 줄 기준으로 문단 분리한다.
    각 세그먼트 뒤에 원래의 구분자(빈 줄)를 포함한다.
    """
    # 코드 블록을 매칭 (```로 시작하고 ```로 끝나는 블록)
    code_block_pattern = re.compile(r"(```[^\n]*\n.*?```)", re.DOTALL)
    parts = code_block_pattern.split(text)

    segments: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.startswith("```"):
            # 코드 블록은 하나의 세그먼트로 유지
            segments.append(part)
        else:
            # 일반 텍스트: 빈 줄 기준으로 문단 분리 (구분자 포함)
            paragraphs = re.split(r"(\n\n+)", part)
            segments.extend(p for p in paragraphs if p)

    return segments


def _split_segment_by_lines(segment: str, max_length: int) -> list[str]:
    """단일 세그먼트가 max_length를 초과할 때 줄 단위로 분할한다.

    코드 블록 내부인 경우 분할된 각 조각에 코드 블록 마커를 보존한다.
    줄바꿈이 없는 긴 텍스트는 문자 단위로 잘라낸다.
    """
    is_code_block = segment.startswith("```")
    code_lang = ""
    inner = segment

    if is_code_block:
        # 첫 줄에서 언어 태그 추출
        first_newline = segment.index("\n") if "\n" in segment else len(segment)
        code_lang = segment[:first_newline]  # e.g. "```python"
        # 닫는 ``` 제거
        if segment.endswith("```"):
            inner = segment[first_newline + 1 : -3]
        else:
            inner = segment[first_newline + 1 :]

    lines = inner.split("\n")
    chunks: list[str] = []
    current_lines: list[str] = []
    current_len = 0

    # 코드 블록 래핑에 필요한 오버헤드 계산
    if is_code_block:
        # 여는 태그 + 줄바꿈 + 닫는 태그
        wrapper_overhead = len(code_lang) + 1 + 3  # "```lang\n" + "```"
    else:
        wrapper_overhead = 0

    content_max = max_length - wrapper_overhead

    for line in lines:
        # 단일 줄이 content_max를 초과하면 문자 단위로 분할
        if len(line) > content_max:
            # 먼저 현재 누적된 줄이 있으면 flush
            if current_lines:
                chunk_text = "\n".join(current_lines)
                if is_code_block:
                    chunk_text = f"{code_lang}\n{chunk_text}```"
                chunks.append(chunk_text)
                current_lines = []
                current_len = 0

            # 긴 줄을 content_max 단위로 잘라냄
            for pos in range(0, len(line), content_max):
                sub = line[pos : pos + content_max]
                if is_code_block:
                    sub = f"{code_lang}\n{sub}```"
                chunks.append(sub)
            continue

        # +1 은 줄바꿈 문자
        line_len = len(line) + (1 if current_lines else 0)
        if current_len + line_len + wrapper_overhead > max_length and current_lines:
            chunk_text = "\n".join(current_lines)
            if is_code_block:
                chunk_text = f"{code_lang}\n{chunk_text}```"
            chunks.append(chunk_text)
            current_lines = []
            current_len = 0

        current_lines.append(line)
        current_len += line_len

    if current_lines:
        chunk_text = "\n".join(current_lines)
        if is_code_block:
            chunk_text = f"{code_lang}\n{chunk_text}```"
        chunks.append(chunk_text)

    return chunks if chunks else [segment]


class TelegramBot(PlatformAdapter):
    def __init__(self) -> None:
        self._app: Application | None = None

    async def start(self) -> None:
        await init_db()

        self._app = Application.builder().token(settings.telegram_bot_token).build()

        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("reset", self._handle_reset))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

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
        """메시지를 전송한다. 4096자 초과 시 분할 전송한다."""
        if not self._app:
            return
        chunks = split_message(text)
        for i, chunk in enumerate(chunks):
            if i > 0:
                await asyncio.sleep(CHUNK_SEND_DELAY)
            await self._app.bot.send_message(
                chat_id=int(platform_user_id),
                text=chunk,
            )

    async def _send_reply_chunks(self, update: Update, text: str) -> None:
        """reply_text를 통해 분할 전송한다."""
        chunks = split_message(text)
        for i, chunk in enumerate(chunks):
            if i > 0:
                await asyncio.sleep(CHUNK_SEND_DELAY)
            await update.message.reply_text(chunk)

    # ── Handlers ───────────────────────────────────────────

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    async def _handle_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

            session.add(
                ConversationHistory(
                    user_id=user.id,
                    role="user",
                    content=update.message.text,
                    platform="telegram",
                )
            )
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
            session.add(
                ConversationHistory(
                    user_id=user.id,
                    role="assistant",
                    content=response,
                    platform="telegram",
                )
            )
            await session.commit()

        await self._send_reply_chunks(update, response)

"""Tests for conversation_service: 대화 이력 조회 및 포맷."""

from datetime import datetime, timedelta, timezone

import pytest

from secretary.models.conversation import ConversationHistory
from secretary.services.conversation_service import (
    format_conversation_history,
    get_recent_conversations,
)


@pytest.mark.asyncio
async def test_get_recent_conversations_empty(sample_family, db_session):
    """대화 이력이 없으면 빈 리스트를 반환한다."""
    admin = sample_family["admin"]
    messages = await get_recent_conversations(db_session, admin.id)
    assert messages == []


@pytest.mark.asyncio
async def test_get_recent_conversations_returns_messages(sample_family, db_session):
    """저장된 대화 이력을 시간순으로 반환한다."""
    admin = sample_family["admin"]

    db_session.add(
        ConversationHistory(
            user_id=admin.id,
            role="user",
            content="안녕하세요",
            platform="telegram",
        )
    )
    db_session.add(
        ConversationHistory(
            user_id=admin.id,
            role="assistant",
            content="안녕하세요! 무엇을 도와드릴까요?",
            platform="telegram",
        )
    )
    db_session.add(
        ConversationHistory(
            user_id=admin.id,
            role="user",
            content="오늘 일정 알려줘",
            platform="telegram",
        )
    )
    await db_session.commit()

    messages = await get_recent_conversations(db_session, admin.id)
    assert len(messages) == 3
    # 시간순 정렬 확인 (오래된 것 먼저)
    assert messages[0].content == "안녕하세요"
    assert messages[1].role == "assistant"
    assert messages[2].content == "오늘 일정 알려줘"


@pytest.mark.asyncio
async def test_get_recent_conversations_respects_max_messages(sample_family, db_session):
    """max_messages 제한을 초과하면 최신 N개만 반환한다."""
    admin = sample_family["admin"]

    for i in range(10):
        db_session.add(
            ConversationHistory(
                user_id=admin.id,
                role="user",
                content=f"메시지 {i}",
                platform="telegram",
            )
        )
    await db_session.commit()

    messages = await get_recent_conversations(db_session, admin.id, max_messages=3)
    assert len(messages) == 3
    # 가장 최신 3개가 시간순으로 반환
    assert messages[0].content == "메시지 7"
    assert messages[1].content == "메시지 8"
    assert messages[2].content == "메시지 9"


@pytest.mark.asyncio
async def test_get_recent_conversations_respects_ttl(sample_family, db_session):
    """TTL을 초과한 오래된 메시지는 제외된다."""
    admin = sample_family["admin"]

    # 오래된 메시지 (25시간 전)
    old_msg = ConversationHistory(
        user_id=admin.id,
        role="user",
        content="오래된 메시지",
        platform="telegram",
    )
    old_msg.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
    db_session.add(old_msg)

    # 최근 메시지
    db_session.add(
        ConversationHistory(
            user_id=admin.id,
            role="user",
            content="최근 메시지",
            platform="telegram",
        )
    )
    await db_session.commit()

    messages = await get_recent_conversations(db_session, admin.id, ttl_hours=24)
    assert len(messages) == 1
    assert messages[0].content == "최근 메시지"


@pytest.mark.asyncio
async def test_get_recent_conversations_filters_by_user(sample_family, db_session):
    """다른 사용자의 대화 이력은 조회되지 않는다."""
    admin = sample_family["admin"]
    member = sample_family["member"]

    db_session.add(
        ConversationHistory(
            user_id=admin.id,
            role="user",
            content="아빠 메시지",
            platform="telegram",
        )
    )
    db_session.add(
        ConversationHistory(
            user_id=member.id,
            role="user",
            content="엄마 메시지",
            platform="telegram",
        )
    )
    await db_session.commit()

    admin_msgs = await get_recent_conversations(db_session, admin.id)
    assert len(admin_msgs) == 1
    assert admin_msgs[0].content == "아빠 메시지"

    member_msgs = await get_recent_conversations(db_session, member.id)
    assert len(member_msgs) == 1
    assert member_msgs[0].content == "엄마 메시지"


# ── format_conversation_history 테스트 ──────────────────


def test_format_conversation_history_empty():
    """빈 리스트이면 빈 문자열을 반환한다."""
    assert format_conversation_history([]) == ""


def test_format_conversation_history_formats_correctly():
    """대화 이력을 올바르게 포맷한다."""
    msg1 = ConversationHistory(
        user_id=1,
        role="user",
        content="안녕하세요",
        platform="telegram",
    )
    msg2 = ConversationHistory(
        user_id=1,
        role="assistant",
        content="안녕하세요! 무엇을 도와드릴까요?",
        platform="telegram",
    )

    result = format_conversation_history([msg1, msg2])

    assert "## 이전 대화 이력" in result
    assert "[사용자] 안녕하세요" in result
    assert "[비서] 안녕하세요! 무엇을 도와드릴까요?" in result


def test_format_conversation_history_role_labels():
    """user는 '사용자', assistant는 '비서'로 표시된다."""
    user_msg = ConversationHistory(
        user_id=1,
        role="user",
        content="테스트",
        platform="telegram",
    )
    assistant_msg = ConversationHistory(
        user_id=1,
        role="assistant",
        content="응답",
        platform="telegram",
    )

    result = format_conversation_history([user_msg, assistant_msg])
    assert "[사용자] 테스트" in result
    assert "[비서] 응답" in result

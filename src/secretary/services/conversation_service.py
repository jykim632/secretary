"""대화 이력 조회 서비스.

세션 재생성 시 이전 대화 컨텍스트를 복원하기 위해
최근 대화 이력을 DB에서 조회하고 시스템 프롬프트용으로 포맷한다.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from secretary.models.conversation import ConversationHistory


async def get_recent_conversations(
    session: AsyncSession,
    user_id: int,
    max_messages: int = 20,
    ttl_hours: int = 24,
) -> list[ConversationHistory]:
    """최근 대화 이력을 조회한다.

    Args:
        session: DB 세션
        user_id: 사용자 ID
        max_messages: 최대 메시지 수
        ttl_hours: TTL (시간 단위). 이 시간 이전의 메시지는 무시한다.

    Returns:
        시간순(오래된 것 먼저)으로 정렬된 대화 이력 목록
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ttl_hours)

    stmt = (
        select(ConversationHistory)
        .where(
            ConversationHistory.user_id == user_id,
            ConversationHistory.created_at >= cutoff,
        )
        .order_by(ConversationHistory.created_at.desc(), ConversationHistory.id.desc())
        .limit(max_messages)
    )
    result = await session.execute(stmt)
    messages = list(result.scalars().all())

    # DB에서 desc로 가져왔으므로 시간순으로 뒤집기
    messages.reverse()
    return messages


async def cleanup_old_conversations(
    session: AsyncSession,
    retention_days: int = 30,
) -> int:
    """보관 기간이 지난 오래된 대화 이력을 삭제한다.

    Args:
        session: DB 세션
        retention_days: 보관 기간 (일 단위). 이 기간보다 오래된 대화 이력을 삭제한다.

    Returns:
        삭제된 레코드 수
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    stmt = delete(ConversationHistory).where(ConversationHistory.created_at < cutoff)
    result = await session.execute(stmt)
    await session.commit()

    return result.rowcount


def format_conversation_history(messages: list[ConversationHistory]) -> str:
    """대화 이력을 시스템 프롬프트에 삽입할 수 있는 형태로 포맷한다.

    Args:
        messages: 시간순 정렬된 대화 이력 목록

    Returns:
        포맷된 대화 이력 문자열. 메시지가 없으면 빈 문자열.
    """
    if not messages:
        return ""

    lines = []
    for msg in messages:
        role_label = "사용자" if msg.role == "user" else "비서"
        lines.append(f"[{role_label}] {msg.content}")

    return (
        "\n\n## 이전 대화 이력 (최근)\n"
        "아래는 이전 세션에서의 대화 내용입니다. 자연스럽게 이어서 대화하세요.\n\n"
        + "\n".join(lines)
    )

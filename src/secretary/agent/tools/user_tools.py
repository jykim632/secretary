"""MCP tools for user info and utility."""

from datetime import datetime
from typing import Any

from claude_agent_sdk import tool

from secretary.models.database import async_session
from secretary.models.user import User
from secretary.services.user_service import get_family_members


def get_user_tools(user_id: int) -> list:
    @tool(
        "get_my_info",
        "현재 사용자의 정보를 조회합니다.",
        {},
    )
    async def get_my_info_tool(args: dict[str, Any]) -> dict[str, Any]:
        async with async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                return _text("사용자 정보를 찾을 수 없습니다.")
            return _text(f"이름: {user.display_name}\n역할: {user.role}\n시간대: {user.timezone}")

    @tool(
        "get_family_members",
        "같은 가족 그룹의 구성원 목록을 보여줍니다.",
        {},
    )
    async def get_family_members_tool(args: dict[str, Any]) -> dict[str, Any]:
        async with async_session() as session:
            members = await get_family_members(session, user_id)
            if not members:
                return _text("가족 구성원이 없습니다.")
            lines = []
            for m in members:
                role_icon = "👑" if m.role == "admin" else "👤"
                lines.append(f"{role_icon} {m.display_name}")
            return _text("가족 구성원:\n" + "\n".join(lines))

    @tool(
        "get_current_datetime",
        "현재 날짜와 시간을 반환합니다.",
        {},
    )
    async def get_current_datetime_tool(args: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now()
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        weekday = weekdays[now.weekday()]
        return _text(
            f"{now.strftime('%Y년 %m월 %d일')} ({weekday}요일) {now.strftime('%H시 %M분')}"
        )

    return [get_my_info_tool, get_family_members_tool, get_current_datetime_tool]


def _text(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}]}

"""MCP tools for family group management (invites, joining)."""

from datetime import datetime
from typing import Any

from claude_agent_sdk import tool
from sqlalchemy import delete as sa_delete, select

from secretary.models.database import async_session
from secretary.models.user import FamilyGroup, User
from secretary.services.user_service import (
    create_family_invite,
    deactivate_invite,
    get_family_members,
    list_family_invites,
    use_invite_code,
    validate_invite_code,
)


def _text(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}]}


def get_family_tools(user_id: int) -> list:
    @tool(
        "create_family_invite",
        "가족 초대 코드를 생성합니다. 관리자(admin)만 사용 가능합니다.",
        {
            "expires_in_days": {
                "type": "integer",
                "description": "초대 코드 유효 기간 (일). 기본값 7일.",
            },
            "max_uses": {
                "type": "integer",
                "description": "최대 사용 횟수. 미지정 시 무제한.",
            },
        },
    )
    async def create_family_invite_tool(args: dict[str, Any]) -> dict[str, Any]:
        expires_in_days = args.get("expires_in_days")
        max_uses = args.get("max_uses")
        async with async_session() as session:
            invite = await create_family_invite(
                session, user_id, expires_in_days=expires_in_days, max_uses=max_uses
            )
            if not invite:
                return _text("초대 코드를 생성할 권한이 없습니다. 관리자만 생성할 수 있어요.")
            uses_info = f"최대 {invite.max_uses}회" if invite.max_uses else "무제한"
            return _text(
                f"초대 코드가 생성되었습니다!\n\n"
                f"코드: {invite.code}\n"
                f"만료: {invite.expires_at.strftime('%Y-%m-%d %H:%M')}\n"
                f"사용 횟수: {uses_info}"
            )

    @tool(
        "list_family_invites",
        "활성 상태인 가족 초대 코드 목록을 조회합니다. 관리자(admin)만 사용 가능합니다.",
        {},
    )
    async def list_family_invites_tool(args: dict[str, Any]) -> dict[str, Any]:
        async with async_session() as session:
            invites = await list_family_invites(session, user_id)
            if not invites:
                return _text("활성 초대 코드가 없습니다.")
            lines = []
            for inv in invites:
                uses = f"{inv.use_count}/{inv.max_uses}" if inv.max_uses else f"{inv.use_count}"
                expired = " (만료됨)" if inv.expires_at < datetime.now() else ""
                lines.append(
                    f"• {inv.code} | 만료: {inv.expires_at.strftime('%m/%d')} | "
                    f"사용: {uses}{expired}"
                )
            return _text("활성 초대 코드 목록:\n" + "\n".join(lines))

    @tool(
        "deactivate_family_invite",
        "초대 코드를 비활성화합니다. 코드를 생성한 관리자만 가능합니다.",
        {
            "invite_id": {
                "type": "integer",
                "description": "비활성화할 초대 코드의 ID",
                "required": True,
            },
        },
    )
    async def deactivate_family_invite_tool(args: dict[str, Any]) -> dict[str, Any]:
        invite_id = args.get("invite_id")
        if invite_id is None:
            return _text("초대 코드 ID를 지정해주세요.")
        async with async_session() as session:
            success = await deactivate_invite(session, invite_id, user_id)
            if success:
                return _text("초대 코드가 비활성화되었습니다.")
            return _text("초대 코드를 비활성화할 수 없습니다. 본인이 생성한 코드만 비활성화할 수 있어요.")

    @tool(
        "join_family_by_invite",
        "초대 코드를 사용하여 다른 가족 그룹에 합류합니다. 혼자 있는 그룹의 유일한 멤버인 경우에만 가능합니다.",
        {
            "invite_code": {
                "type": "string",
                "description": "가족 초대 코드 (8자리)",
                "required": True,
            },
        },
    )
    async def join_family_by_invite_tool(args: dict[str, Any]) -> dict[str, Any]:
        code = args.get("invite_code", "").strip()
        if not code:
            return _text("초대 코드를 입력해주세요.")

        async with async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                return _text("사용자 정보를 찾을 수 없습니다.")

            # Check if user is the only member in their current group
            members = await get_family_members(session, user_id)
            if len(members) > 1:
                return _text(
                    "현재 가족 그룹에 다른 구성원이 있어서 이동할 수 없습니다. "
                    "혼자 있는 그룹에서만 가족 합류가 가능합니다."
                )

            invite = await validate_invite_code(session, code)
            if not invite:
                return _text("유효하지 않은 초대 코드입니다. 만료되었거나 사용 횟수를 초과했을 수 있어요.")

            if invite.family_group_id == user.family_group_id:
                return _text("이미 해당 가족 그룹에 속해 있습니다.")

            # Save old group for cleanup
            old_group_id = user.family_group_id

            # Move user to new family
            user.family_group_id = invite.family_group_id
            user.role = "member"
            await use_invite_code(session, invite)

            # Delete empty old group
            old_members_result = await session.execute(
                select(User).where(User.family_group_id == old_group_id)
            )
            if not list(old_members_result.scalars().all()):
                await session.execute(
                    sa_delete(FamilyGroup).where(FamilyGroup.id == old_group_id)
                )

            await session.commit()

        # Reset agent session to reload tools with new family context
        from secretary.agent.brain import agent_brain

        await agent_brain.reset_session(user_id)

        return _text("가족 그룹에 합류했습니다! 새로운 가족과 함께 사용할 수 있어요. 🎉")

    return [
        create_family_invite_tool,
        list_family_invites_tool,
        deactivate_family_invite_tool,
        join_family_by_invite_tool,
    ]

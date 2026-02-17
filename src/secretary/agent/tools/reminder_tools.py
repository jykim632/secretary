"""MCP tools for reminder management."""

from datetime import datetime
from typing import Any

from claude_agent_sdk import tool

from secretary.models.database import async_session
from secretary.services.calendar_service import (
    cancel_reminder,
    list_reminders,
    set_reminder,
)


def get_reminder_tools(user_id: int) -> list:
    @tool(
        "set_reminder",
        "리마인더를 설정합니다. remind_at은 ISO 형식입니다. (예: 2025-03-15T15:00)",
        {
            "message": str,
            "remind_at": str,
            "is_recurring": bool,
            "recurrence_rule": str,  # e.g. "daily", "weekly", "monthly"
        },
    )
    async def set_reminder_tool(args: dict[str, Any]) -> dict[str, Any]:
        try:
            remind_at = datetime.fromisoformat(args["remind_at"])
        except (ValueError, KeyError):
            return _text("시간 형식이 올바르지 않습니다. (예: 2025-03-15T15:00)")
        async with async_session() as session:
            reminder = await set_reminder(
                session,
                user_id=user_id,
                message=args["message"],
                remind_at=remind_at,
                is_recurring=args.get("is_recurring", False),
                recurrence_rule=args.get("recurrence_rule"),
            )
            return _text(
                f"⏰ 리마인더 #{reminder.id} 설정됨\n"
                f"  {reminder.message}\n"
                f"  알림: {remind_at.strftime('%m/%d %H:%M')}"
            )

    @tool(
        "list_reminders",
        "설정된 리마인더 목록을 보여줍니다.",
        {"include_delivered": bool},
    )
    async def list_reminders_tool(args: dict[str, Any]) -> dict[str, Any]:
        async with async_session() as session:
            reminders = await list_reminders(
                session, user_id,
                include_delivered=args.get("include_delivered", False),
            )
            if not reminders:
                return _text("설정된 리마인더가 없습니다.")
            lines = []
            for r in reminders:
                status = "✅" if r.is_delivered else "⏳"
                time_str = r.remind_at.strftime("%m/%d %H:%M")
                lines.append(f"{status} #{r.id} [{time_str}] {r.message}")
            return _text("\n".join(lines))

    @tool(
        "cancel_reminder",
        "리마인더를 취소합니다.",
        {"reminder_id": int},
    )
    async def cancel_reminder_tool(args: dict[str, Any]) -> dict[str, Any]:
        async with async_session() as session:
            ok = await cancel_reminder(session, args["reminder_id"], user_id)
            if not ok:
                return _text("리마인더를 찾을 수 없거나 취소 권한이 없습니다.")
            return _text(f"리마인더 #{args['reminder_id']} 취소됨")

    return [set_reminder_tool, list_reminders_tool, cancel_reminder_tool]


def _text(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}]}

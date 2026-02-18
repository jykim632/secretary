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
        "리마인더를 설정합니다. remind_at은 ISO 형식입니다. (예: 2025-03-15T15:00)\n"
        "반복 리마인더: is_recurring=true, recurrence_rule='daily'|'weekly'|'monthly'\n"
        "반복 종료 조건: recurrence_count(횟수) 또는 recurrence_end_date(종료일, ISO 형식)",
        {
            "message": str,
            "remind_at": str,
            "is_recurring": bool,
            "recurrence_rule": str,  # e.g. "daily", "weekly", "monthly"
            "recurrence_count": int,  # 반복 횟수 제한 (선택)
            "recurrence_end_date": str,  # 반복 종료일 ISO 형식 (선택)
        },
    )
    async def set_reminder_tool(args: dict[str, Any]) -> dict[str, Any]:
        try:
            remind_at = datetime.fromisoformat(args["remind_at"])
        except (ValueError, KeyError):
            return _text("시간 형식이 올바르지 않습니다. (예: 2025-03-15T15:00)")

        # 반복 종료일 파싱
        recurrence_end_date = None
        if args.get("recurrence_end_date"):
            try:
                recurrence_end_date = datetime.fromisoformat(args["recurrence_end_date"])
            except ValueError:
                return _text("반복 종료일 형식이 올바르지 않습니다. (예: 2025-06-30T23:59)")

        async with async_session() as session:
            reminder = await set_reminder(
                session,
                user_id=user_id,
                message=args["message"],
                remind_at=remind_at,
                is_recurring=args.get("is_recurring", False),
                recurrence_rule=args.get("recurrence_rule"),
                recurrence_count=args.get("recurrence_count"),
                recurrence_end_date=recurrence_end_date,
            )
            lines = [
                f"⏰ 리마인더 #{reminder.id} 설정됨",
                f"  {reminder.message}",
                f"  알림: {remind_at.strftime('%m/%d %H:%M')}",
            ]
            if reminder.is_recurring and reminder.recurrence_rule:
                rule_labels = {"daily": "매일", "weekly": "매주", "monthly": "매월"}
                label = rule_labels.get(
                    reminder.recurrence_rule.strip().lower(),
                    reminder.recurrence_rule,
                )
                lines.append(f"  반복: {label}")
                if reminder.recurrence_count:
                    lines.append(f"  반복 횟수: {reminder.recurrence_count}회")
                if reminder.recurrence_end_date:
                    lines.append(f"  종료일: {reminder.recurrence_end_date.strftime('%Y/%m/%d')}")
            return _text("\n".join(lines))

    @tool(
        "list_reminders",
        "설정된 리마인더 목록을 보여줍니다.",
        {"include_delivered": bool},
    )
    async def list_reminders_tool(args: dict[str, Any]) -> dict[str, Any]:
        async with async_session() as session:
            reminders = await list_reminders(
                session,
                user_id,
                include_delivered=args.get("include_delivered", False),
            )
            if not reminders:
                return _text("설정된 리마인더가 없습니다.")
            lines = []
            for r in reminders:
                status = "✅" if r.is_delivered else "⏳"
                time_str = r.remind_at.strftime("%m/%d %H:%M")
                recur_info = ""
                if r.is_recurring and r.recurrence_rule:
                    rule_labels = {"daily": "매일", "weekly": "매주", "monthly": "매월"}
                    label = rule_labels.get(r.recurrence_rule.strip().lower(), r.recurrence_rule)
                    recur_info = f" 🔁{label}"
                    if r.recurrence_count:
                        recur_info += f"({r.delivered_count}/{r.recurrence_count})"
                lines.append(f"{status} #{r.id} [{time_str}] {r.message}{recur_info}")
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

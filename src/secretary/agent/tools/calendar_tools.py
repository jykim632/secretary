"""MCP tools for calendar/event management."""

from datetime import datetime
from typing import Any

from claude_agent_sdk import tool

from secretary.models.database import async_session
from secretary.services.calendar_service import (
    create_event,
    delete_event,
    get_today_schedule,
    list_events,
    update_event,
)


def get_calendar_tools(user_id: int, family_group_id: int) -> list:
    @tool(
        "create_event",
        "일정을 등록합니다. 기본적으로 가족 전체에게 공유됩니다.",
        {
            "title": str,
            "start_time": str,  # ISO format
            "end_time": str,
            "description": str,
            "visibility": str,
        },
    )
    async def create_event_tool(args: dict[str, Any]) -> dict[str, Any]:
        try:
            start = datetime.fromisoformat(args["start_time"])
        except (ValueError, KeyError):
            return _text("시작 시간 형식이 올바르지 않습니다. (예: 2025-03-15T14:00)")
        end = None
        if args.get("end_time"):
            try:
                end = datetime.fromisoformat(args["end_time"])
            except ValueError:
                pass
        async with async_session() as session:
            event = await create_event(
                session,
                user_id=user_id,
                title=args["title"],
                start_time=start,
                end_time=end,
                description=args.get("description", ""),
                visibility=args.get("visibility", "family"),
            )
            return _text(
                f"일정 #{event.id} 등록됨: {event.title} ({start.strftime('%m/%d %H:%M')})"
            )

    @tool(
        "list_events",
        "기간 내 일정을 조회합니다. start/end는 ISO 형식입니다.",
        {"start": str, "end": str},
    )
    async def list_events_tool(args: dict[str, Any]) -> dict[str, Any]:
        start = end = None
        if args.get("start"):
            start = datetime.fromisoformat(args["start"])
        if args.get("end"):
            end = datetime.fromisoformat(args["end"])
        async with async_session() as session:
            events = await list_events(session, user_id, family_group_id, start, end)
            if not events:
                return _text("해당 기간에 일정이 없습니다.")
            lines = []
            for e in events:
                time_str = e.start_time.strftime("%m/%d %H:%M")
                vis = "👨‍👩‍👧‍👦" if e.visibility == "family" else "🔒"
                lines.append(f"#{e.id} {vis} [{time_str}] {e.title}")
            return _text("\n".join(lines))

    @tool(
        "get_today_schedule",
        "오늘의 일정을 보여줍니다.",
        {},
    )
    async def get_today_schedule_tool(args: dict[str, Any]) -> dict[str, Any]:
        async with async_session() as session:
            events = await get_today_schedule(session, user_id, family_group_id)
            if not events:
                return _text("오늘 일정이 없습니다.")
            lines = ["📅 오늘의 일정:"]
            for e in events:
                time_str = e.start_time.strftime("%H:%M")
                lines.append(f"  • [{time_str}] {e.title}")
            return _text("\n".join(lines))

    @tool(
        "update_event",
        "일정을 수정합니다.",
        {"event_id": int, "title": str, "start_time": str, "end_time": str, "description": str},
    )
    async def update_event_tool(args: dict[str, Any]) -> dict[str, Any]:
        event_id = args.pop("event_id")
        if args.get("start_time"):
            try:
                args["start_time"] = datetime.fromisoformat(args["start_time"])
            except ValueError:
                return _text("시작 시간 형식이 올바르지 않습니다.")
        if args.get("end_time"):
            try:
                args["end_time"] = datetime.fromisoformat(args["end_time"])
            except ValueError:
                return _text("종료 시간 형식이 올바르지 않습니다.")
        updates = {k: v for k, v in args.items() if v is not None}
        async with async_session() as session:
            event = await update_event(session, event_id, user_id, **updates)
            if not event:
                return _text("일정을 찾을 수 없거나 수정 권한이 없습니다.")
            return _text(f"일정 #{event.id} 수정됨: {event.title}")

    @tool(
        "delete_event",
        "일정을 삭제합니다.",
        {"event_id": int},
    )
    async def delete_event_tool(args: dict[str, Any]) -> dict[str, Any]:
        async with async_session() as session:
            ok = await delete_event(session, args["event_id"], user_id)
            if not ok:
                return _text("일정을 찾을 수 없거나 삭제 권한이 없습니다.")
            return _text(f"일정 #{args['event_id']} 삭제됨")

    return [
        create_event_tool,
        list_events_tool,
        get_today_schedule_tool,
        update_event_tool,
        delete_event_tool,
    ]


def _text(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}]}

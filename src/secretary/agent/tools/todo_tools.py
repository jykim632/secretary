"""MCP tools for todo management."""

from datetime import datetime
from typing import Any

from claude_agent_sdk import tool

from secretary.models.database import async_session
from secretary.services.memo_service import (
    create_todo,
    delete_todo,
    list_todos,
    toggle_todo,
    update_todo,
)


def get_todo_tools(user_id: int, family_group_id: int) -> list:
    @tool(
        "create_todo",
        "할일을 추가합니다.",
        {
            "title": str,
            "due_date": str,  # ISO format or empty
            "visibility": str,
            "priority": int,  # 0=normal, 1=high, 2=urgent
        },
    )
    async def create_todo_tool(args: dict[str, Any]) -> dict[str, Any]:
        due = None
        if args.get("due_date"):
            try:
                due = datetime.fromisoformat(args["due_date"])
            except ValueError:
                return _text("날짜 형식이 올바르지 않습니다. (예: 2025-03-15T14:00)")
        async with async_session() as session:
            td = await create_todo(
                session,
                user_id=user_id,
                title=args["title"],
                due_date=due,
                visibility=args.get("visibility", "private"),
                priority=args.get("priority", 0),
            )
            return _text(f"할일 #{td.id} 추가됨: {td.title}")

    @tool(
        "list_todos",
        "할일 목록을 보여줍니다.",
        {"include_done": bool},
    )
    async def list_todos_tool(args: dict[str, Any]) -> dict[str, Any]:
        async with async_session() as session:
            todos = await list_todos(
                session,
                user_id,
                family_group_id,
                include_done=args.get("include_done", False),
            )
            if not todos:
                return _text("할일이 없습니다! 🎉")
            lines = []
            for t in todos:
                check = "✅" if t.is_done else "⬜"
                pri = {0: "", 1: "❗", 2: "🔥"}.get(t.priority, "")
                due = f" (기한: {t.due_date.strftime('%m/%d')})" if t.due_date else ""
                lines.append(f"{check} #{t.id} {pri}{t.title}{due}")
            return _text("\n".join(lines))

    @tool(
        "toggle_todo",
        "할일의 완료 상태를 토글합니다.",
        {"todo_id": int},
    )
    async def toggle_todo_tool(args: dict[str, Any]) -> dict[str, Any]:
        async with async_session() as session:
            td = await toggle_todo(session, args["todo_id"], user_id)
            if not td:
                return _text("할일을 찾을 수 없습니다.")
            status = "완료" if td.is_done else "미완료"
            return _text(f"#{td.id} {td.title} → {status}")

    @tool(
        "update_todo",
        "할일을 수정합니다.",
        {"todo_id": int, "title": str, "due_date": str, "visibility": str, "priority": int},
    )
    async def update_todo_tool(args: dict[str, Any]) -> dict[str, Any]:
        todo_id = args.pop("todo_id")
        if args.get("due_date"):
            try:
                args["due_date"] = datetime.fromisoformat(args["due_date"])
            except ValueError:
                return _text("날짜 형식이 올바르지 않습니다.")
        updates = {k: v for k, v in args.items() if v is not None}
        async with async_session() as session:
            td = await update_todo(session, todo_id, user_id, **updates)
            if not td:
                return _text("할일을 찾을 수 없습니다.")
            return _text(f"할일 #{td.id} 수정됨")

    @tool(
        "delete_todo",
        "할일을 삭제합니다.",
        {"todo_id": int},
    )
    async def delete_todo_tool(args: dict[str, Any]) -> dict[str, Any]:
        async with async_session() as session:
            ok = await delete_todo(session, args["todo_id"], user_id)
            if not ok:
                return _text("할일을 찾을 수 없거나 삭제 권한이 없습니다.")
            return _text(f"할일 #{args['todo_id']} 삭제됨")

    return [create_todo_tool, list_todos_tool, toggle_todo_tool, update_todo_tool, delete_todo_tool]


def _text(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}]}

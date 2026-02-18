"""MCP tools for memo management. user_id is bound via closure."""

from typing import Any

from claude_agent_sdk import tool

from secretary.models.database import async_session
from secretary.services.memo_service import (
    create_memo,
    delete_memo,
    list_memos,
    search_memos,
    update_memo,
)


def get_memo_tools(user_id: int, family_group_id: int) -> list:
    @tool(
        "create_memo",
        "메모를 생성합니다. visibility가 'family'이면 가족 전체가 볼 수 있습니다.",
        {
            "title": str,
            "content": str,
            "visibility": str,  # "private" or "family"
            "tags": str,
        },
    )
    async def create_memo_tool(args: dict[str, Any]) -> dict[str, Any]:
        async with async_session() as session:
            memo = await create_memo(
                session,
                user_id=user_id,
                title=args["title"],
                content=args.get("content", ""),
                visibility=args.get("visibility", "private"),
                tags=args.get("tags", ""),
            )
            return _text(f"메모 #{memo.id} 생성됨: {memo.title}")

    @tool(
        "list_memos",
        "내 메모와 가족 공유 메모를 목록으로 보여줍니다.",
        {},
    )
    async def list_memos_tool(args: dict[str, Any]) -> dict[str, Any]:
        async with async_session() as session:
            memos = await list_memos(session, user_id, family_group_id)
            if not memos:
                return _text("저장된 메모가 없습니다.")
            lines = []
            for m in memos:
                vis = "👨‍👩‍👧‍👦" if m.visibility == "family" else "🔒"
                lines.append(f"#{m.id} {vis} {m.title}")
            return _text("\n".join(lines))

    @tool(
        "search_memos",
        "키워드로 메모를 검색합니다.",
        {"query": str},
    )
    async def search_memos_tool(args: dict[str, Any]) -> dict[str, Any]:
        async with async_session() as session:
            memos = await search_memos(session, user_id, args["query"], family_group_id)
            if not memos:
                return _text("검색 결과가 없습니다.")
            lines = []
            for m in memos:
                lines.append(f"#{m.id} {m.title}\n  {m.content[:80]}")
            return _text("\n".join(lines))

    @tool(
        "update_memo",
        "메모를 수정합니다. 변경할 필드만 전달하세요.",
        {"memo_id": int, "title": str, "content": str, "visibility": str, "tags": str},
    )
    async def update_memo_tool(args: dict[str, Any]) -> dict[str, Any]:
        memo_id = args.pop("memo_id")
        # Remove keys with None/empty values for partial update
        updates = {k: v for k, v in args.items() if v is not None}
        async with async_session() as session:
            memo = await update_memo(session, memo_id, user_id, **updates)
            if not memo:
                return _text("메모를 찾을 수 없거나 수정 권한이 없습니다.")
            return _text(f"메모 #{memo.id} 수정됨: {memo.title}")

    @tool(
        "delete_memo",
        "메모를 삭제합니다.",
        {"memo_id": int},
    )
    async def delete_memo_tool(args: dict[str, Any]) -> dict[str, Any]:
        async with async_session() as session:
            ok = await delete_memo(session, args["memo_id"], user_id)
            if not ok:
                return _text("메모를 찾을 수 없거나 삭제 권한이 없습니다.")
            return _text(f"메모 #{args['memo_id']} 삭제됨")

    return [
        create_memo_tool,
        list_memos_tool,
        search_memos_tool,
        update_memo_tool,
        delete_memo_tool,
    ]


def _text(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}]}

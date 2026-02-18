from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from secretary.models.memo import Memo, Todo
from secretary.models.user import User


# ── Memo CRUD ──────────────────────────────────────────────


async def create_memo(
    session: AsyncSession,
    user_id: int,
    title: str,
    content: str = "",
    visibility: str = "private",
    tags: str = "",
) -> Memo:
    memo = Memo(
        user_id=user_id,
        title=title,
        content=content,
        visibility=visibility,
        tags=tags,
    )
    session.add(memo)
    await session.commit()
    await session.refresh(memo)
    return memo


async def list_memos(
    session: AsyncSession,
    user_id: int,
    family_group_id: int | None = None,
    include_family: bool = True,
) -> list[Memo]:
    """List user's own memos + family-visible memos from same group."""
    conditions = [Memo.user_id == user_id]
    if include_family and family_group_id:
        # Also include family-visible memos from other family members
        family_member_ids = await _get_family_member_ids(session, family_group_id)
        conditions = [
            or_(
                Memo.user_id == user_id,
                (Memo.user_id.in_(family_member_ids)) & (Memo.visibility == "family"),
            )
        ]
    stmt = select(Memo).where(*conditions).order_by(Memo.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def search_memos(
    session: AsyncSession,
    user_id: int,
    query: str,
    family_group_id: int | None = None,
) -> list[Memo]:
    """Search memos by title/content, respecting visibility."""
    like_pattern = f"%{query}%"
    family_member_ids = (
        await _get_family_member_ids(session, family_group_id) if family_group_id else []
    )

    stmt = (
        select(Memo)
        .where(
            or_(
                Memo.user_id == user_id,
                (Memo.user_id.in_(family_member_ids)) & (Memo.visibility == "family"),
            ),
            or_(
                Memo.title.ilike(like_pattern),
                Memo.content.ilike(like_pattern),
                Memo.tags.ilike(like_pattern),
            ),
        )
        .order_by(Memo.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_memo(
    session: AsyncSession,
    memo_id: int,
    user_id: int,
    **kwargs,
) -> Memo | None:
    memo = await session.get(Memo, memo_id)
    if not memo or memo.user_id != user_id:
        return None
    for key, value in kwargs.items():
        if hasattr(memo, key):
            setattr(memo, key, value)
    await session.commit()
    await session.refresh(memo)
    return memo


async def delete_memo(session: AsyncSession, memo_id: int, user_id: int) -> bool:
    memo = await session.get(Memo, memo_id)
    if not memo or memo.user_id != user_id:
        return False
    await session.delete(memo)
    await session.commit()
    return True


# ── Todo CRUD ──────────────────────────────────────────────


async def create_todo(
    session: AsyncSession,
    user_id: int,
    title: str,
    due_date=None,
    visibility: str = "private",
    priority: int = 0,
) -> Todo:
    todo = Todo(
        user_id=user_id,
        title=title,
        due_date=due_date,
        visibility=visibility,
        priority=priority,
    )
    session.add(todo)
    await session.commit()
    await session.refresh(todo)
    return todo


async def list_todos(
    session: AsyncSession,
    user_id: int,
    family_group_id: int | None = None,
    include_done: bool = False,
    include_family: bool = True,
) -> list[Todo]:
    conditions = []
    if include_family and family_group_id:
        family_member_ids = await _get_family_member_ids(session, family_group_id)
        conditions.append(
            or_(
                Todo.user_id == user_id,
                (Todo.user_id.in_(family_member_ids)) & (Todo.visibility == "family"),
            )
        )
    else:
        conditions.append(Todo.user_id == user_id)
    if not include_done:
        conditions.append(Todo.is_done == False)  # noqa: E712
    stmt = select(Todo).where(*conditions).order_by(Todo.priority.desc(), Todo.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def toggle_todo(session: AsyncSession, todo_id: int, user_id: int) -> Todo | None:
    todo = await session.get(Todo, todo_id)
    if not todo or todo.user_id != user_id:
        return None
    todo.is_done = not todo.is_done
    await session.commit()
    await session.refresh(todo)
    return todo


async def update_todo(
    session: AsyncSession,
    todo_id: int,
    user_id: int,
    **kwargs,
) -> Todo | None:
    todo = await session.get(Todo, todo_id)
    if not todo or todo.user_id != user_id:
        return None
    for key, value in kwargs.items():
        if hasattr(todo, key):
            setattr(todo, key, value)
    await session.commit()
    await session.refresh(todo)
    return todo


async def delete_todo(session: AsyncSession, todo_id: int, user_id: int) -> bool:
    todo = await session.get(Todo, todo_id)
    if not todo or todo.user_id != user_id:
        return False
    await session.delete(todo)
    await session.commit()
    return True


# ── Helpers ────────────────────────────────────────────────


async def _get_family_member_ids(session: AsyncSession, family_group_id: int) -> list[int]:
    stmt = select(User.id).where(User.family_group_id == family_group_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())

"""Tests for memo_service: memo and todo CRUD, visibility, ownership."""

import pytest

from secretary.services.memo_service import (
    create_memo,
    create_todo,
    delete_memo,
    delete_todo,
    list_memos,
    list_todos,
    search_memos,
    toggle_todo,
    update_memo,
    update_todo,
)


# ── Memo Tests ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_list_memo(sample_family, db_session):
    admin = sample_family["admin"]
    memo = await create_memo(db_session, admin.id, "장보기 목록", "우유, 계란")

    assert memo.id is not None
    assert memo.title == "장보기 목록"
    assert memo.visibility == "private"

    memos = await list_memos(db_session, admin.id)
    assert len(memos) == 1


@pytest.mark.asyncio
async def test_memo_family_visibility(sample_family, db_session):
    """Family-visible memo should appear in other member's list."""
    admin = sample_family["admin"]
    member = sample_family["member"]
    group = sample_family["group"]

    await create_memo(db_session, admin.id, "가족 공유 메모", visibility="family")
    await create_memo(db_session, admin.id, "비공개 메모", visibility="private")

    # Member should see only the family-visible memo from admin
    member_memos = await list_memos(db_session, member.id, group.id)
    assert len(member_memos) == 1
    assert member_memos[0].title == "가족 공유 메모"


@pytest.mark.asyncio
async def test_search_memos(sample_family, db_session):
    admin = sample_family["admin"]
    group = sample_family["group"]

    await create_memo(db_session, admin.id, "레시피", "김치찌개 만드는 법", tags="요리")
    await create_memo(db_session, admin.id, "회의록", "프로젝트 진행 상황")

    results = await search_memos(db_session, admin.id, "김치", group.id)
    assert len(results) == 1
    assert results[0].title == "레시피"

    # Search by tag
    results = await search_memos(db_session, admin.id, "요리", group.id)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_update_memo(sample_family, db_session):
    admin = sample_family["admin"]
    memo = await create_memo(db_session, admin.id, "원래 제목")

    updated = await update_memo(db_session, memo.id, admin.id, title="수정된 제목")
    assert updated is not None
    assert updated.title == "수정된 제목"


@pytest.mark.asyncio
async def test_update_memo_wrong_owner(sample_family, db_session):
    """Only the owner can update their memo."""
    admin = sample_family["admin"]
    member = sample_family["member"]
    memo = await create_memo(db_session, admin.id, "아빠 메모")

    result = await update_memo(db_session, memo.id, member.id, title="해킹")
    assert result is None


@pytest.mark.asyncio
async def test_delete_memo(sample_family, db_session):
    admin = sample_family["admin"]
    memo = await create_memo(db_session, admin.id, "삭제할 메모")

    assert await delete_memo(db_session, memo.id, admin.id) is True

    memos = await list_memos(db_session, admin.id)
    assert len(memos) == 0


@pytest.mark.asyncio
async def test_delete_memo_wrong_owner(sample_family, db_session):
    admin = sample_family["admin"]
    member = sample_family["member"]
    memo = await create_memo(db_session, admin.id, "아빠 메모")

    assert await delete_memo(db_session, memo.id, member.id) is False


# ── Todo Tests ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_list_todo(sample_family, db_session):
    admin = sample_family["admin"]
    todo = await create_todo(db_session, admin.id, "빨래하기", priority=2)

    assert todo.id is not None
    assert todo.priority == 2
    assert todo.is_done is False

    todos = await list_todos(db_session, admin.id)
    assert len(todos) == 1


@pytest.mark.asyncio
async def test_toggle_todo(sample_family, db_session):
    admin = sample_family["admin"]
    todo = await create_todo(db_session, admin.id, "빨래하기")

    toggled = await toggle_todo(db_session, todo.id, admin.id)
    assert toggled.is_done is True

    toggled2 = await toggle_todo(db_session, todo.id, admin.id)
    assert toggled2.is_done is False


@pytest.mark.asyncio
async def test_toggle_todo_wrong_owner(sample_family, db_session):
    admin = sample_family["admin"]
    member = sample_family["member"]
    todo = await create_todo(db_session, admin.id, "빨래하기")

    result = await toggle_todo(db_session, todo.id, member.id)
    assert result is None


@pytest.mark.asyncio
async def test_list_todos_excludes_done(sample_family, db_session):
    admin = sample_family["admin"]
    await create_todo(db_session, admin.id, "미완료")
    done = await create_todo(db_session, admin.id, "완료됨")
    await toggle_todo(db_session, done.id, admin.id)

    todos = await list_todos(db_session, admin.id, include_done=False)
    assert len(todos) == 1
    assert todos[0].title == "미완료"

    todos_all = await list_todos(db_session, admin.id, include_done=True)
    assert len(todos_all) == 2


@pytest.mark.asyncio
async def test_todo_family_visibility(sample_family, db_session):
    admin = sample_family["admin"]
    member = sample_family["member"]
    group = sample_family["group"]

    await create_todo(db_session, admin.id, "가족 할일", visibility="family")
    await create_todo(db_session, admin.id, "개인 할일", visibility="private")

    member_todos = await list_todos(db_session, member.id, group.id)
    assert len(member_todos) == 1
    assert member_todos[0].title == "가족 할일"


@pytest.mark.asyncio
async def test_update_todo(sample_family, db_session):
    admin = sample_family["admin"]
    todo = await create_todo(db_session, admin.id, "원래 할일")

    updated = await update_todo(db_session, todo.id, admin.id, title="수정된 할일", priority=1)
    assert updated.title == "수정된 할일"
    assert updated.priority == 1


@pytest.mark.asyncio
async def test_delete_todo(sample_family, db_session):
    admin = sample_family["admin"]
    todo = await create_todo(db_session, admin.id, "삭제할 할일")

    assert await delete_todo(db_session, todo.id, admin.id) is True
    assert await delete_todo(db_session, todo.id, admin.id) is False  # already deleted

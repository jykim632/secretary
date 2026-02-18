"""Tests for calendar_service: event CRUD, reminders, visibility."""

from datetime import datetime, timedelta

import pytest

from secretary.services.calendar_service import (
    cancel_reminder,
    create_event,
    delete_event,
    get_due_reminders,
    get_today_schedule,
    list_events,
    list_reminders,
    mark_delivered,
    set_reminder,
    update_event,
)


# ── Event Tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_list_event(sample_family, db_session):
    admin = sample_family["admin"]
    group = sample_family["group"]
    start = datetime(2026, 3, 1, 10, 0)

    event = await create_event(db_session, admin.id, "병원 예약", start, description="내과")

    assert event.id is not None
    assert event.visibility == "family"  # default

    events = await list_events(db_session, admin.id, group.id)
    assert len(events) == 1


@pytest.mark.asyncio
async def test_event_family_visibility(sample_family, db_session):
    """Family events should be visible to other members."""
    admin = sample_family["admin"]
    member = sample_family["member"]
    group = sample_family["group"]
    start = datetime(2026, 3, 1, 10, 0)

    await create_event(db_session, admin.id, "가족 일정", start, visibility="family")
    await create_event(db_session, admin.id, "개인 일정", start, visibility="private")

    member_events = await list_events(db_session, member.id, group.id)
    assert len(member_events) == 1
    assert member_events[0].title == "가족 일정"


@pytest.mark.asyncio
async def test_list_events_date_range(sample_family, db_session):
    admin = sample_family["admin"]
    group = sample_family["group"]

    await create_event(db_session, admin.id, "3월 일정", datetime(2026, 3, 15, 10, 0))
    await create_event(db_session, admin.id, "4월 일정", datetime(2026, 4, 15, 10, 0))

    march_events = await list_events(
        db_session, admin.id, group.id,
        start=datetime(2026, 3, 1),
        end=datetime(2026, 3, 31),
    )
    assert len(march_events) == 1
    assert march_events[0].title == "3월 일정"


@pytest.mark.asyncio
async def test_get_today_schedule(sample_family, db_session):
    admin = sample_family["admin"]
    group = sample_family["group"]
    now = datetime(2026, 3, 1, 12, 0)

    await create_event(db_session, admin.id, "오늘 일정", datetime(2026, 3, 1, 14, 0))
    await create_event(db_session, admin.id, "내일 일정", datetime(2026, 3, 2, 10, 0))

    today = await get_today_schedule(db_session, admin.id, group.id, now=now)
    assert len(today) == 1
    assert today[0].title == "오늘 일정"


@pytest.mark.asyncio
async def test_update_event(sample_family, db_session):
    admin = sample_family["admin"]
    start = datetime(2026, 3, 1, 10, 0)
    event = await create_event(db_session, admin.id, "원래 일정", start)

    updated = await update_event(db_session, event.id, admin.id, title="수정된 일정")
    assert updated.title == "수정된 일정"


@pytest.mark.asyncio
async def test_update_event_wrong_owner(sample_family, db_session):
    admin = sample_family["admin"]
    member = sample_family["member"]
    event = await create_event(db_session, admin.id, "아빠 일정", datetime(2026, 3, 1, 10, 0))

    result = await update_event(db_session, event.id, member.id, title="해킹")
    assert result is None


@pytest.mark.asyncio
async def test_delete_event(sample_family, db_session):
    admin = sample_family["admin"]
    event = await create_event(db_session, admin.id, "삭제할 일정", datetime(2026, 3, 1, 10, 0))

    assert await delete_event(db_session, event.id, admin.id) is True
    assert await delete_event(db_session, event.id, admin.id) is False


# ── Reminder Tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_and_list_reminders(sample_family, db_session):
    admin = sample_family["admin"]
    remind_at = datetime(2026, 3, 1, 9, 0)

    reminder = await set_reminder(db_session, admin.id, "약 먹기", remind_at)
    assert reminder.id is not None
    assert reminder.is_delivered is False

    reminders = await list_reminders(db_session, admin.id)
    assert len(reminders) == 1


@pytest.mark.asyncio
async def test_get_due_reminders(sample_family, db_session):
    admin = sample_family["admin"]
    now = datetime(2026, 3, 1, 12, 0)

    await set_reminder(db_session, admin.id, "과거 리마인더", now - timedelta(hours=1))
    await set_reminder(db_session, admin.id, "미래 리마인더", now + timedelta(hours=1))

    due = await get_due_reminders(db_session, now)
    assert len(due) == 1
    assert due[0].message == "과거 리마인더"


@pytest.mark.asyncio
async def test_mark_delivered(sample_family, db_session):
    admin = sample_family["admin"]
    now = datetime(2026, 3, 1, 12, 0)
    reminder = await set_reminder(db_session, admin.id, "전송할 리마인더", now - timedelta(hours=1))

    await mark_delivered(db_session, reminder.id)

    # Should no longer appear in due reminders
    due = await get_due_reminders(db_session, now)
    assert len(due) == 0

    # Should not appear in default list (exclude delivered)
    reminders = await list_reminders(db_session, admin.id)
    assert len(reminders) == 0

    # Should appear with include_delivered=True
    all_reminders = await list_reminders(db_session, admin.id, include_delivered=True)
    assert len(all_reminders) == 1


@pytest.mark.asyncio
async def test_cancel_reminder(sample_family, db_session):
    admin = sample_family["admin"]
    reminder = await set_reminder(db_session, admin.id, "취소할 리마인더", datetime(2026, 3, 1))

    assert await cancel_reminder(db_session, reminder.id, admin.id) is True
    assert await cancel_reminder(db_session, reminder.id, admin.id) is False  # already deleted


@pytest.mark.asyncio
async def test_cancel_reminder_wrong_owner(sample_family, db_session):
    admin = sample_family["admin"]
    member = sample_family["member"]
    reminder = await set_reminder(db_session, admin.id, "아빠 리마인더", datetime(2026, 3, 1))

    assert await cancel_reminder(db_session, reminder.id, member.id) is False

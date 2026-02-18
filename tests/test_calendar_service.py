"""Tests for calendar_service: event CRUD, reminders, visibility."""

from datetime import datetime, timedelta

import pytest

from secretary.services.calendar_service import (
    calculate_next_remind_at,
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
        db_session,
        admin.id,
        group.id,
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
async def test_mark_delivered_increments_delivered_count(sample_family, db_session):
    """일회성 리마인더도 delivered_count가 증가하는지 확인."""
    admin = sample_family["admin"]
    now = datetime(2026, 3, 1, 12, 0)
    reminder = await set_reminder(db_session, admin.id, "일회성", now - timedelta(hours=1))

    await mark_delivered(db_session, reminder.id)
    await db_session.refresh(reminder)

    assert reminder.is_delivered is True
    assert reminder.delivered_count == 1


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


# ── calculate_next_remind_at 단위 테스트 ─────────────────


def test_calculate_next_daily():
    """daily 규칙: 하루 뒤."""
    base = datetime(2026, 3, 1, 9, 0)
    result = calculate_next_remind_at(base, "daily")
    assert result == datetime(2026, 3, 2, 9, 0)


def test_calculate_next_weekly():
    """weekly 규칙: 7일 뒤."""
    base = datetime(2026, 3, 1, 9, 0)
    result = calculate_next_remind_at(base, "weekly")
    assert result == datetime(2026, 3, 8, 9, 0)


def test_calculate_next_monthly():
    """monthly 규칙: 다음 달 같은 일."""
    base = datetime(2026, 3, 15, 9, 0)
    result = calculate_next_remind_at(base, "monthly")
    assert result == datetime(2026, 4, 15, 9, 0)


def test_calculate_next_monthly_end_of_month():
    """monthly 규칙: 1월 31일 -> 2월은 28일(또는 29일)로 보정."""
    base = datetime(2026, 1, 31, 9, 0)
    result = calculate_next_remind_at(base, "monthly")
    # 2026년 2월은 28일이 마지막
    assert result == datetime(2026, 2, 28, 9, 0)


def test_calculate_next_monthly_december_to_january():
    """monthly 규칙: 12월 -> 다음 해 1월."""
    base = datetime(2026, 12, 15, 9, 0)
    result = calculate_next_remind_at(base, "monthly")
    assert result == datetime(2027, 1, 15, 9, 0)


def test_calculate_next_unknown_rule_fallback():
    """알 수 없는 규칙은 daily로 fallback."""
    base = datetime(2026, 3, 1, 9, 0)
    result = calculate_next_remind_at(base, "unknown_rule")
    assert result == datetime(2026, 3, 2, 9, 0)


# ── 반복 리마인더 통합 테스트 ─────────────────────────────


@pytest.mark.asyncio
async def test_recurring_daily_reminder_reschedules(sample_family, db_session):
    """매일 반복 리마인더: mark_delivered 후 다음 날로 재설정된다."""
    admin = sample_family["admin"]
    remind_at = datetime(2026, 3, 1, 9, 0)

    reminder = await set_reminder(
        db_session,
        admin.id,
        "매일 약 먹기",
        remind_at,
        is_recurring=True,
        recurrence_rule="daily",
    )

    # 첫 번째 발송
    await mark_delivered(db_session, reminder.id)
    await db_session.refresh(reminder)

    assert reminder.is_delivered is False  # 아직 반복 중
    assert reminder.remind_at == datetime(2026, 3, 2, 9, 0)
    assert reminder.delivered_count == 1

    # 두 번째 발송
    await mark_delivered(db_session, reminder.id)
    await db_session.refresh(reminder)

    assert reminder.is_delivered is False
    assert reminder.remind_at == datetime(2026, 3, 3, 9, 0)
    assert reminder.delivered_count == 2


@pytest.mark.asyncio
async def test_recurring_weekly_reminder_reschedules(sample_family, db_session):
    """매주 반복 리마인더: mark_delivered 후 7일 뒤로 재설정된다."""
    admin = sample_family["admin"]
    remind_at = datetime(2026, 3, 1, 9, 0)

    reminder = await set_reminder(
        db_session,
        admin.id,
        "주간 회의",
        remind_at,
        is_recurring=True,
        recurrence_rule="weekly",
    )

    await mark_delivered(db_session, reminder.id)
    await db_session.refresh(reminder)

    assert reminder.is_delivered is False
    assert reminder.remind_at == datetime(2026, 3, 8, 9, 0)
    assert reminder.delivered_count == 1


@pytest.mark.asyncio
async def test_recurring_monthly_reminder_reschedules(sample_family, db_session):
    """매월 반복 리마인더: mark_delivered 후 다음 달로 재설정된다."""
    admin = sample_family["admin"]
    remind_at = datetime(2026, 1, 31, 9, 0)

    reminder = await set_reminder(
        db_session,
        admin.id,
        "월말 보고",
        remind_at,
        is_recurring=True,
        recurrence_rule="monthly",
    )

    # 1/31 -> 2/28 (2026년은 평년)
    await mark_delivered(db_session, reminder.id)
    await db_session.refresh(reminder)

    assert reminder.is_delivered is False
    assert reminder.remind_at == datetime(2026, 2, 28, 9, 0)

    # 2/28 -> 3/28
    await mark_delivered(db_session, reminder.id)
    await db_session.refresh(reminder)

    assert reminder.remind_at == datetime(2026, 3, 28, 9, 0)


@pytest.mark.asyncio
async def test_recurring_reminder_stops_at_count(sample_family, db_session):
    """횟수 제한 반복 리마인더: recurrence_count에 도달하면 is_delivered=True."""
    admin = sample_family["admin"]
    remind_at = datetime(2026, 3, 1, 9, 0)

    reminder = await set_reminder(
        db_session,
        admin.id,
        "3회 반복",
        remind_at,
        is_recurring=True,
        recurrence_rule="daily",
        recurrence_count=3,
    )

    # 1회차 발송
    await mark_delivered(db_session, reminder.id)
    await db_session.refresh(reminder)
    assert reminder.is_delivered is False
    assert reminder.delivered_count == 1
    assert reminder.remind_at == datetime(2026, 3, 2, 9, 0)

    # 2회차 발송
    await mark_delivered(db_session, reminder.id)
    await db_session.refresh(reminder)
    assert reminder.is_delivered is False
    assert reminder.delivered_count == 2
    assert reminder.remind_at == datetime(2026, 3, 3, 9, 0)

    # 3회차 발송 → 종료
    await mark_delivered(db_session, reminder.id)
    await db_session.refresh(reminder)
    assert reminder.is_delivered is True
    assert reminder.delivered_count == 3


@pytest.mark.asyncio
async def test_recurring_reminder_stops_at_end_date(sample_family, db_session):
    """종료일 제한 반복 리마인더: 다음 알림이 종료일을 넘으면 is_delivered=True."""
    admin = sample_family["admin"]
    remind_at = datetime(2026, 3, 1, 9, 0)
    end_date = datetime(2026, 3, 3, 23, 59)

    reminder = await set_reminder(
        db_session,
        admin.id,
        "종료일 반복",
        remind_at,
        is_recurring=True,
        recurrence_rule="daily",
        recurrence_end_date=end_date,
    )

    # 1회차: 3/1 -> 3/2 (종료일 이전)
    await mark_delivered(db_session, reminder.id)
    await db_session.refresh(reminder)
    assert reminder.is_delivered is False
    assert reminder.remind_at == datetime(2026, 3, 2, 9, 0)

    # 2회차: 3/2 -> 3/3 (종료일 이전)
    await mark_delivered(db_session, reminder.id)
    await db_session.refresh(reminder)
    assert reminder.is_delivered is False
    assert reminder.remind_at == datetime(2026, 3, 3, 9, 0)

    # 3회차: 3/3 -> 3/4 (종료일 초과) → 종료
    await mark_delivered(db_session, reminder.id)
    await db_session.refresh(reminder)
    assert reminder.is_delivered is True


@pytest.mark.asyncio
async def test_recurring_reminder_not_in_due_after_reschedule(sample_family, db_session):
    """반복 리마인더가 재설정된 후에는 현재 시점의 due 목록에 나타나지 않는다."""
    admin = sample_family["admin"]
    now = datetime(2026, 3, 1, 12, 0)
    remind_at = datetime(2026, 3, 1, 9, 0)

    reminder = await set_reminder(
        db_session,
        admin.id,
        "반복 리마인더",
        remind_at,
        is_recurring=True,
        recurrence_rule="daily",
    )

    # 발송 전: due 목록에 있어야 함
    due = await get_due_reminders(db_session, now)
    assert len(due) == 1

    # 발송 후: 다음 날로 재설정되어 현재 시점 due 목록에서 사라짐
    await mark_delivered(db_session, reminder.id)
    due = await get_due_reminders(db_session, now)
    assert len(due) == 0

    # 다음 날 시점: 다시 due 목록에 나타남
    tomorrow = datetime(2026, 3, 2, 12, 0)
    due = await get_due_reminders(db_session, tomorrow)
    assert len(due) == 1


@pytest.mark.asyncio
async def test_recurring_reminder_shows_in_active_list(sample_family, db_session):
    """반복 리마인더는 is_delivered=False 상태를 유지하므로 활성 목록에 계속 나타난다."""
    admin = sample_family["admin"]
    remind_at = datetime(2026, 3, 1, 9, 0)

    await set_reminder(
        db_session,
        admin.id,
        "매일 반복",
        remind_at,
        is_recurring=True,
        recurrence_rule="daily",
    )

    # 발송 전
    reminders = await list_reminders(db_session, admin.id)
    assert len(reminders) == 1

    # 발송 후에도 활성 목록에 유지
    reminder = reminders[0]
    await mark_delivered(db_session, reminder.id)
    reminders = await list_reminders(db_session, admin.id)
    assert len(reminders) == 1


@pytest.mark.asyncio
async def test_set_recurring_reminder_with_all_fields(sample_family, db_session):
    """반복 리마인더 생성 시 모든 필드가 올바르게 저장되는지 확인."""
    admin = sample_family["admin"]
    remind_at = datetime(2026, 3, 1, 9, 0)
    end_date = datetime(2026, 6, 30, 23, 59)

    reminder = await set_reminder(
        db_session,
        admin.id,
        "전체 필드 테스트",
        remind_at,
        is_recurring=True,
        recurrence_rule="weekly",
        recurrence_count=10,
        recurrence_end_date=end_date,
    )

    assert reminder.is_recurring is True
    assert reminder.recurrence_rule == "weekly"
    assert reminder.recurrence_count == 10
    assert reminder.recurrence_end_date == end_date
    assert reminder.delivered_count == 0
    assert reminder.is_delivered is False

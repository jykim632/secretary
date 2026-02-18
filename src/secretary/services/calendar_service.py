from calendar import monthrange
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from secretary.models.calendar import Event, Reminder
from secretary.models.user import User


# ── Event CRUD ─────────────────────────────────────────────


async def create_event(
    session: AsyncSession,
    user_id: int,
    title: str,
    start_time: datetime,
    end_time: datetime | None = None,
    description: str = "",
    visibility: str = "family",
) -> Event:
    event = Event(
        user_id=user_id,
        title=title,
        start_time=start_time,
        end_time=end_time,
        description=description,
        visibility=visibility,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def list_events(
    session: AsyncSession,
    user_id: int,
    family_group_id: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[Event]:
    """List events in a date range, including family-visible ones."""
    family_ids = await _get_family_member_ids(session, family_group_id) if family_group_id else []
    conditions = [
        or_(
            Event.user_id == user_id,
            (Event.user_id.in_(family_ids)) & (Event.visibility == "family"),
        )
    ]
    if start:
        conditions.append(Event.start_time >= start)
    if end:
        conditions.append(Event.start_time <= end)
    stmt = select(Event).where(*conditions).order_by(Event.start_time)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_today_schedule(
    session: AsyncSession,
    user_id: int,
    family_group_id: int | None = None,
    now: datetime | None = None,
) -> list[Event]:
    now = now or datetime.now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)
    return await list_events(session, user_id, family_group_id, start_of_day, end_of_day)


async def update_event(
    session: AsyncSession,
    event_id: int,
    user_id: int,
    **kwargs,
) -> Event | None:
    event = await session.get(Event, event_id)
    if not event or event.user_id != user_id:
        return None
    for key, value in kwargs.items():
        if hasattr(event, key):
            setattr(event, key, value)
    await session.commit()
    await session.refresh(event)
    return event


async def delete_event(session: AsyncSession, event_id: int, user_id: int) -> bool:
    event = await session.get(Event, event_id)
    if not event or event.user_id != user_id:
        return False
    await session.delete(event)
    await session.commit()
    return True


# ── Reminder CRUD ──────────────────────────────────────────


async def set_reminder(
    session: AsyncSession,
    user_id: int,
    message: str,
    remind_at: datetime,
    is_recurring: bool = False,
    recurrence_rule: str | None = None,
    recurrence_count: int | None = None,
    recurrence_end_date: datetime | None = None,
) -> Reminder:
    reminder = Reminder(
        user_id=user_id,
        message=message,
        remind_at=remind_at,
        is_recurring=is_recurring,
        recurrence_rule=recurrence_rule,
        recurrence_count=recurrence_count,
        recurrence_end_date=recurrence_end_date,
    )
    session.add(reminder)
    await session.commit()
    await session.refresh(reminder)
    return reminder


async def list_reminders(
    session: AsyncSession,
    user_id: int,
    include_delivered: bool = False,
) -> list[Reminder]:
    conditions = [Reminder.user_id == user_id]
    if not include_delivered:
        conditions.append(Reminder.is_delivered == False)  # noqa: E712
    stmt = select(Reminder).where(*conditions).order_by(Reminder.remind_at)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_due_reminders(session: AsyncSession, now: datetime | None = None) -> list[Reminder]:
    """Get all undelivered reminders that are past due."""
    now = now or datetime.now()
    stmt = (
        select(Reminder)
        .where(
            Reminder.is_delivered == False,  # noqa: E712
            Reminder.remind_at <= now,
        )
        .order_by(Reminder.remind_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def calculate_next_remind_at(current: datetime, rule: str) -> datetime:
    """recurrence_rule에 따라 다음 알림 시간을 계산한다.

    지원하는 규칙: daily, weekly, monthly
    """
    rule_lower = rule.strip().lower()
    if rule_lower == "daily":
        return current + timedelta(days=1)
    elif rule_lower == "weekly":
        return current + timedelta(weeks=1)
    elif rule_lower == "monthly":
        # 같은 일자를 유지하되, 해당 월의 마지막 일을 초과하지 않도록 처리
        year = current.year
        month = current.month + 1
        if month > 12:
            month = 1
            year += 1
        max_day = monthrange(year, month)[1]
        day = min(current.day, max_day)
        return current.replace(year=year, month=month, day=day)
    else:
        # 알 수 없는 규칙은 daily로 fallback
        return current + timedelta(days=1)


def _is_recurrence_ended(reminder: Reminder, next_at: datetime) -> bool:
    """반복 종료 조건을 확인한다.

    - recurrence_count가 설정된 경우: delivered_count가 count에 도달하면 종료
    - recurrence_end_date가 설정된 경우: 다음 알림이 종료일을 넘으면 종료
    """
    if reminder.recurrence_count is not None:
        if reminder.delivered_count >= reminder.recurrence_count:
            return True
    if reminder.recurrence_end_date is not None:
        if next_at > reminder.recurrence_end_date:
            return True
    return False


async def mark_delivered(session: AsyncSession, reminder_id: int) -> None:
    """리마인더를 발송 완료 처리한다.

    반복 리마인더인 경우 다음 알림 시간을 계산하여 재설정한다.
    반복 종료 조건에 도달하면 최종 발송 완료로 마킹한다.
    """
    reminder = await session.get(Reminder, reminder_id)
    if not reminder:
        return

    reminder.delivered_count += 1

    if reminder.is_recurring and reminder.recurrence_rule:
        next_at = calculate_next_remind_at(reminder.remind_at, reminder.recurrence_rule)

        if _is_recurrence_ended(reminder, next_at):
            # 반복 종료 조건 도달 → 최종 발송 완료
            reminder.is_delivered = True
        else:
            # 다음 알림 시간으로 재설정 (is_delivered는 False 유지)
            reminder.remind_at = next_at
    else:
        # 일회성 리마인더 → 발송 완료
        reminder.is_delivered = True

    await session.commit()


async def cancel_reminder(session: AsyncSession, reminder_id: int, user_id: int) -> bool:
    reminder = await session.get(Reminder, reminder_id)
    if not reminder or reminder.user_id != user_id:
        return False
    await session.delete(reminder)
    await session.commit()
    return True


# ── Helpers ────────────────────────────────────────────────


async def _get_family_member_ids(session: AsyncSession, family_group_id: int) -> list[int]:
    stmt = select(User.id).where(User.family_group_id == family_group_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())

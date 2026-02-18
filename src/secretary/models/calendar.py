from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from secretary.models.database import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    start_time: Mapped[datetime] = mapped_column()
    end_time: Mapped[datetime | None] = mapped_column(nullable=True)
    visibility: Mapped[str] = mapped_column(String(20), default="family")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    message: Mapped[str] = mapped_column(Text)
    remind_at: Mapped[datetime] = mapped_column()
    is_recurring: Mapped[bool] = mapped_column(default=False)
    recurrence_rule: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 반복 종료 조건: 횟수 제한 또는 종료 날짜
    recurrence_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recurrence_end_date: Mapped[datetime | None] = mapped_column(nullable=True)
    # 현재까지 발송된 반복 횟수
    delivered_count: Mapped[int] = mapped_column(Integer, default=0)
    is_delivered: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

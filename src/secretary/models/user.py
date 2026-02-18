from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from secretary.models.database import Base


class FamilyGroup(Base):
    __tablename__ = "family_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    members: Mapped[list["User"]] = relationship(back_populates="family_group")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    family_group_id: Mapped[int] = mapped_column(ForeignKey("family_groups.id"))
    role: Mapped[str] = mapped_column(String(20), default="member")  # admin | member
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Seoul")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    family_group: Mapped["FamilyGroup"] = relationship(back_populates="members")
    platform_links: Mapped[list["UserPlatformLink"]] = relationship(back_populates="user")


class UserPlatformLink(Base):
    __tablename__ = "user_platform_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    platform: Mapped[str] = mapped_column(String(20))  # telegram | slack
    platform_user_id: Mapped[str] = mapped_column(String(100), unique=True)
    is_primary: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="platform_links")


class FamilyInvite(Base):
    __tablename__ = "family_invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_group_id: Mapped[int] = mapped_column(ForeignKey("family_groups.id"))
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    family_group: Mapped["FamilyGroup"] = relationship()
    creator: Mapped["User"] = relationship()

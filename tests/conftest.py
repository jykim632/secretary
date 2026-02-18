"""Shared fixtures: in-memory SQLite database for all tests."""

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from secretary.models.database import Base

# All models must be imported so Base.metadata knows about them
from secretary.models.user import FamilyGroup, User, UserPlatformLink  # noqa: F401
from secretary.models.memo import Memo, Todo  # noqa: F401
from secretary.models.calendar import Event, Reminder  # noqa: F401
from secretary.models.conversation import ConversationHistory  # noqa: F401


@pytest_asyncio.fixture
async def db_session():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def sample_family(db_session: AsyncSession):
    """Create a family group with two users (admin + member) for testing."""
    group = FamilyGroup(name="테스트가족")
    db_session.add(group)
    await db_session.flush()

    admin = User(
        display_name="아빠",
        family_group_id=group.id,
        role="admin",
        timezone="Asia/Seoul",
    )
    member = User(
        display_name="엄마",
        family_group_id=group.id,
        role="member",
        timezone="Asia/Seoul",
    )
    db_session.add_all([admin, member])
    await db_session.flush()

    link_admin = UserPlatformLink(
        user_id=admin.id,
        platform="telegram",
        platform_user_id="tg_admin_123",
        is_primary=True,
    )
    link_member = UserPlatformLink(
        user_id=member.id,
        platform="telegram",
        platform_user_id="tg_member_456",
        is_primary=True,
    )
    db_session.add_all([link_admin, link_member])
    await db_session.commit()

    return {"group": group, "admin": admin, "member": member}

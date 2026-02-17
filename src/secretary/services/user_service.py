from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config.settings import settings
from secretary.models.user import FamilyGroup, User, UserPlatformLink


async def get_or_create_user(
    session: AsyncSession,
    platform: str,
    platform_user_id: str,
    display_name: str,
) -> User:
    """Find user by platform link, or create new user + family group if first user."""
    stmt = (
        select(User)
        .join(UserPlatformLink)
        .where(
            UserPlatformLink.platform == platform,
            UserPlatformLink.platform_user_id == platform_user_id,
        )
    )
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user:
        return user

    # Check if any family group exists
    fg_result = await session.execute(select(FamilyGroup).limit(1))
    family_group = fg_result.scalar_one_or_none()

    if not family_group:
        # First user ever — create family group, user as admin
        family_group = FamilyGroup(name=settings.default_family_name)
        session.add(family_group)
        await session.flush()
        role = "admin"
    else:
        role = "member"

    user = User(
        display_name=display_name,
        family_group_id=family_group.id,
        role=role,
        timezone=settings.default_timezone,
    )
    session.add(user)
    await session.flush()

    link = UserPlatformLink(
        user_id=user.id,
        platform=platform,
        platform_user_id=platform_user_id,
        is_primary=True,
    )
    session.add(link)
    await session.commit()
    return user


async def get_user_by_platform(
    session: AsyncSession,
    platform: str,
    platform_user_id: str,
) -> User | None:
    stmt = (
        select(User)
        .join(UserPlatformLink)
        .where(
            UserPlatformLink.platform == platform,
            UserPlatformLink.platform_user_id == platform_user_id,
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_family_members(session: AsyncSession, user_id: int) -> list[User]:
    """Get all members in the same family group."""
    user = await session.get(User, user_id)
    if not user:
        return []
    stmt = (
        select(User)
        .where(User.family_group_id == user.family_group_id)
        .order_by(User.created_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def link_platform(
    session: AsyncSession,
    user_id: int,
    platform: str,
    platform_user_id: str,
) -> UserPlatformLink:
    """Link an additional platform account to an existing user."""
    link = UserPlatformLink(
        user_id=user_id,
        platform=platform,
        platform_user_id=platform_user_id,
        is_primary=False,
    )
    session.add(link)
    await session.commit()
    return link


async def get_user_platform_links(
    session: AsyncSession, user_id: int
) -> list[UserPlatformLink]:
    stmt = select(UserPlatformLink).where(UserPlatformLink.user_id == user_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())

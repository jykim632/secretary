import secrets
import string
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from secretary.models.user import FamilyGroup, FamilyInvite, User, UserPlatformLink


def _generate_invite_code(length: int = 8) -> str:
    """Generate a random invite code (uppercase letters + digits)."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def create_family_invite(
    session: AsyncSession,
    user_id: int,
    expires_in_days: int | None = None,
    max_uses: int | None = None,
) -> FamilyInvite | None:
    """Create a family invite code. Only admins can create invites."""
    user = await session.get(User, user_id)
    if not user or user.role != "admin":
        return None

    if expires_in_days is None:
        expires_in_days = settings.invite_code_default_expiry_days

    code = _generate_invite_code()
    invite = FamilyInvite(
        family_group_id=user.family_group_id,
        code=code,
        created_by=user_id,
        expires_at=datetime.now() + timedelta(days=expires_in_days),
        max_uses=max_uses,
    )
    session.add(invite)
    await session.commit()
    return invite


async def validate_invite_code(session: AsyncSession, code: str) -> FamilyInvite | None:
    """Validate an invite code. Returns the invite if valid, None otherwise."""
    stmt = select(FamilyInvite).where(
        FamilyInvite.code == code.upper(),
        FamilyInvite.is_active.is_(True),
        FamilyInvite.expires_at > datetime.now(),
    )
    result = await session.execute(stmt)
    invite = result.scalar_one_or_none()
    if not invite:
        return None

    # Check max_uses
    if invite.max_uses is not None and invite.use_count >= invite.max_uses:
        return None

    return invite


async def use_invite_code(session: AsyncSession, invite: FamilyInvite) -> None:
    """Increment the use count of an invite code."""
    invite.use_count += 1
    await session.commit()


async def deactivate_invite(
    session: AsyncSession, invite_id: int, user_id: int
) -> bool:
    """Deactivate an invite code. Only the creator can deactivate."""
    invite = await session.get(FamilyInvite, invite_id)
    if not invite or invite.created_by != user_id:
        return False
    invite.is_active = False
    await session.commit()
    return True


async def list_family_invites(
    session: AsyncSession, user_id: int
) -> list[FamilyInvite]:
    """List active invites for the user's family group. Admin only."""
    user = await session.get(User, user_id)
    if not user or user.role != "admin":
        return []

    stmt = select(FamilyInvite).where(
        FamilyInvite.family_group_id == user.family_group_id,
        FamilyInvite.is_active.is_(True),
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_or_create_user(
    session: AsyncSession,
    platform: str,
    platform_user_id: str,
    display_name: str,
    invite_code: str | None = None,
) -> User:
    """Find user by platform link, or create new user.

    - With valid invite_code: join that family as member
    - Without invite_code (or invalid): create new family group as admin
    """
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

    # Try to use invite code
    invite = None
    if invite_code:
        invite = await validate_invite_code(session, invite_code)

    if invite:
        # Join existing family as member
        family_group_id = invite.family_group_id
        role = "member"
        await use_invite_code(session, invite)
    else:
        # Create new family group, user as admin
        family_group = FamilyGroup(name=settings.default_family_name)
        session.add(family_group)
        await session.flush()
        family_group_id = family_group.id
        role = "admin"

    user = User(
        display_name=display_name,
        family_group_id=family_group_id,
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
        select(User).where(User.family_group_id == user.family_group_id).order_by(User.created_at)
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


async def get_user_platform_links(session: AsyncSession, user_id: int) -> list[UserPlatformLink]:
    stmt = select(UserPlatformLink).where(UserPlatformLink.user_id == user_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())

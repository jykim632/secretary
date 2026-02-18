"""Tests for user_service: registration, family group creation, platform linking, invites."""

from datetime import datetime, timedelta

import pytest

from secretary.models.user import FamilyGroup
from secretary.services.user_service import (
    create_family_invite,
    deactivate_invite,
    get_family_members,
    get_or_create_user,
    get_user_by_platform,
    get_user_platform_links,
    link_platform,
    list_family_invites,
    validate_invite_code,
)


@pytest.mark.asyncio
async def test_first_user_becomes_admin(db_session):
    """First user should auto-create a family group and be assigned admin role."""
    user = await get_or_create_user(db_session, "telegram", "tg_001", "아빠")

    assert user.role == "admin"
    assert user.display_name == "아빠"

    # Family group should exist
    group = await db_session.get(FamilyGroup, user.family_group_id)
    assert group is not None

    # Platform link should exist
    links = await get_user_platform_links(db_session, user.id)
    assert len(links) == 1
    assert links[0].platform == "telegram"
    assert links[0].is_primary is True


@pytest.mark.asyncio
async def test_second_user_becomes_member_with_invite(db_session):
    """Second user should join existing family group as member via invite code."""
    admin = await get_or_create_user(db_session, "telegram", "tg_001", "아빠")
    invite = await create_family_invite(db_session, admin.id)
    assert invite is not None

    user2 = await get_or_create_user(
        db_session, "telegram", "tg_002", "엄마", invite_code=invite.code
    )

    assert user2.role == "member"
    assert user2.family_group_id == admin.family_group_id


@pytest.mark.asyncio
async def test_no_invite_creates_new_group(db_session):
    """User without invite code should create their own family group."""
    admin = await get_or_create_user(db_session, "telegram", "tg_001", "아빠")
    user2 = await get_or_create_user(db_session, "telegram", "tg_002", "이웃")

    assert user2.role == "admin"
    assert user2.family_group_id != admin.family_group_id


@pytest.mark.asyncio
async def test_get_or_create_returns_existing(db_session):
    """Calling with same platform_user_id should return existing user, not create new."""
    user1 = await get_or_create_user(db_session, "telegram", "tg_001", "아빠")
    user2 = await get_or_create_user(db_session, "telegram", "tg_001", "아빠")

    assert user1.id == user2.id


@pytest.mark.asyncio
async def test_get_user_by_platform(db_session):
    """Look up user by platform credentials."""
    await get_or_create_user(db_session, "telegram", "tg_001", "아빠")

    found = await get_user_by_platform(db_session, "telegram", "tg_001")
    assert found is not None
    assert found.display_name == "아빠"

    not_found = await get_user_by_platform(db_session, "telegram", "tg_999")
    assert not_found is None


@pytest.mark.asyncio
async def test_get_family_members(sample_family, db_session):
    """Should return all members in the same family group."""
    admin = sample_family["admin"]
    members = await get_family_members(db_session, admin.id)

    assert len(members) == 2
    names = {m.display_name for m in members}
    assert names == {"아빠", "엄마"}


@pytest.mark.asyncio
async def test_get_family_members_invalid_user(db_session):
    """Should return empty list for non-existent user."""
    members = await get_family_members(db_session, 9999)
    assert members == []


@pytest.mark.asyncio
async def test_link_platform(sample_family, db_session):
    """Should add a second platform link to existing user."""
    admin = sample_family["admin"]
    new_link = await link_platform(db_session, admin.id, "slack", "slack_admin_789")

    assert new_link.platform == "slack"
    assert new_link.is_primary is False

    links = await get_user_platform_links(db_session, admin.id)
    assert len(links) == 2
    platforms = {lnk.platform for lnk in links}
    assert platforms == {"telegram", "slack"}


# ── Invite tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_family_invite_admin_only(db_session):
    """Only admin can create invites."""
    admin = await get_or_create_user(db_session, "telegram", "tg_001", "아빠")
    invite = await create_family_invite(db_session, admin.id)
    assert invite is not None
    assert len(invite.code) == 8
    assert invite.is_active is True

    # Create a member via invite
    member = await get_or_create_user(
        db_session, "telegram", "tg_002", "엄마", invite_code=invite.code
    )
    assert member.role == "member"

    # Member cannot create invite
    member_invite = await create_family_invite(db_session, member.id)
    assert member_invite is None


@pytest.mark.asyncio
async def test_validate_invite_code(db_session):
    """Valid code should pass, invalid/expired/exhausted should fail."""
    admin = await get_or_create_user(db_session, "telegram", "tg_001", "아빠")
    invite = await create_family_invite(db_session, admin.id)
    assert invite is not None

    # Valid code
    valid = await validate_invite_code(db_session, invite.code)
    assert valid is not None
    assert valid.id == invite.id

    # Invalid code
    invalid = await validate_invite_code(db_session, "ZZZZZZZZ")
    assert invalid is None

    # Case insensitive
    valid_lower = await validate_invite_code(db_session, invite.code.lower())
    assert valid_lower is not None


@pytest.mark.asyncio
async def test_invite_code_joins_family(db_session):
    """User with valid invite code should join the inviter's family."""
    admin = await get_or_create_user(db_session, "telegram", "tg_001", "아빠")
    invite = await create_family_invite(db_session, admin.id)
    assert invite is not None

    new_user = await get_or_create_user(
        db_session, "telegram", "tg_003", "딸", invite_code=invite.code
    )

    assert new_user.family_group_id == admin.family_group_id
    assert new_user.role == "member"

    # Invite use_count should be incremented
    await db_session.refresh(invite)
    assert invite.use_count == 1


@pytest.mark.asyncio
async def test_expired_invite_code(db_session):
    """Expired invite code should be rejected."""
    admin = await get_or_create_user(db_session, "telegram", "tg_001", "아빠")
    invite = await create_family_invite(db_session, admin.id)
    assert invite is not None

    # Manually expire it
    invite.expires_at = datetime.now() - timedelta(hours=1)
    await db_session.commit()

    result = await validate_invite_code(db_session, invite.code)
    assert result is None

    # User with expired code should create their own group
    user = await get_or_create_user(
        db_session, "telegram", "tg_004", "이웃", invite_code=invite.code
    )
    assert user.role == "admin"
    assert user.family_group_id != admin.family_group_id


@pytest.mark.asyncio
async def test_max_uses_invite(db_session):
    """Invite with max_uses should reject after exhausted."""
    admin = await get_or_create_user(db_session, "telegram", "tg_001", "아빠")
    invite = await create_family_invite(db_session, admin.id, max_uses=1)
    assert invite is not None

    # First use should work
    user1 = await get_or_create_user(
        db_session, "telegram", "tg_002", "엄마", invite_code=invite.code
    )
    assert user1.family_group_id == admin.family_group_id

    # Second use should fail (max_uses=1, already used once)
    result = await validate_invite_code(db_session, invite.code)
    assert result is None


@pytest.mark.asyncio
async def test_deactivate_invite(db_session):
    """Creator should be able to deactivate their invite."""
    admin = await get_or_create_user(db_session, "telegram", "tg_001", "아빠")
    invite = await create_family_invite(db_session, admin.id)
    assert invite is not None

    # Deactivate
    success = await deactivate_invite(db_session, invite.id, admin.id)
    assert success is True

    # Should no longer be valid
    result = await validate_invite_code(db_session, invite.code)
    assert result is None


@pytest.mark.asyncio
async def test_deactivate_invite_wrong_user(db_session):
    """Non-creator should not be able to deactivate invite."""
    admin = await get_or_create_user(db_session, "telegram", "tg_001", "아빠")
    invite = await create_family_invite(db_session, admin.id)
    assert invite is not None

    member = await get_or_create_user(
        db_session, "telegram", "tg_002", "엄마", invite_code=invite.code
    )

    success = await deactivate_invite(db_session, invite.id, member.id)
    assert success is False


@pytest.mark.asyncio
async def test_list_family_invites(db_session):
    """Admin should see active invites for their family."""
    admin = await get_or_create_user(db_session, "telegram", "tg_001", "아빠")
    await create_family_invite(db_session, admin.id)
    await create_family_invite(db_session, admin.id)

    invites = await list_family_invites(db_session, admin.id)
    assert len(invites) == 2

    # Member should see nothing
    invite = invites[0]
    member = await get_or_create_user(
        db_session, "telegram", "tg_002", "엄마", invite_code=invite.code
    )
    member_invites = await list_family_invites(db_session, member.id)
    assert len(member_invites) == 0

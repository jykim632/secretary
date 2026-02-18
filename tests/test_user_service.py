"""Tests for user_service: registration, family group creation, platform linking."""

import pytest

from secretary.models.user import FamilyGroup
from secretary.services.user_service import (
    get_family_members,
    get_or_create_user,
    get_user_by_platform,
    get_user_platform_links,
    link_platform,
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
async def test_second_user_becomes_member(db_session):
    """Second user should join existing family group as member."""
    await get_or_create_user(db_session, "telegram", "tg_001", "아빠")
    user2 = await get_or_create_user(db_session, "telegram", "tg_002", "엄마")

    assert user2.role == "member"


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

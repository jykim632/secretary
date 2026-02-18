"""Tests for AgentBrain: 에러 발생 시 세션 자동 복구."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from secretary.agent.brain import MAX_CONSECUTIVE_ERRORS, AgentBrain


@pytest.fixture
def brain():
    """AgentBrain 인스턴스를 생성한다."""
    return AgentBrain()


async def _async_iter(items):
    """리스트를 async iterator로 변환한다."""
    for item in items:
        yield item


def _make_fake_client(*, fail: bool = False):
    """테스트용 가짜 ClaudeSDKClient를 생성한다.

    fail=True이면 query() 호출 시 RuntimeError를 발생시킨다.
    """
    client = MagicMock()
    client.query = AsyncMock()
    client.__aexit__ = AsyncMock()
    if fail:
        client.query.side_effect = RuntimeError("test error")
    else:
        client.receive_response = MagicMock(return_value=_async_iter([]))
    return client


def _make_successful_client_with_message(assistant_msg):
    """AssistantMessage를 반환하는 가짜 클라이언트를 생성한다."""
    client = MagicMock()
    client.query = AsyncMock()
    client.__aexit__ = AsyncMock()
    client.receive_response = MagicMock(return_value=_async_iter([assistant_msg]))
    return client


@pytest.mark.asyncio
async def test_error_count_increments_on_exception(brain):
    """예외 발생 시 에러 카운트가 증가한다."""
    user_id = 1
    failing_client = _make_fake_client(fail=True)

    with patch.object(brain, "_get_or_create_session", return_value=failing_client):
        result = await brain.process_message(user_id, 1, "테스트", "가족", "Asia/Seoul", "안녕")

    assert result == "처리 중 오류가 발생했습니다. 다시 시도해주세요."
    assert brain._error_counts[user_id] == 1


@pytest.mark.asyncio
async def test_error_count_resets_on_success(brain):
    """성공 응답 시 에러 카운트가 초기화된다."""
    from claude_agent_sdk import AssistantMessage, TextBlock

    user_id = 1
    brain._error_counts[user_id] = 2  # 이미 에러가 2번 발생한 상태

    text_block = TextBlock(text="응답입니다")
    assistant_msg = AssistantMessage(content=[text_block], model="test-model")
    client = _make_successful_client_with_message(assistant_msg)

    with patch.object(brain, "_get_or_create_session", return_value=client):
        result = await brain.process_message(user_id, 1, "테스트", "가족", "Asia/Seoul", "안녕")

    assert result == "응답입니다"
    assert user_id not in brain._error_counts


@pytest.mark.asyncio
async def test_session_reset_after_max_consecutive_errors(brain):
    """연속 에러가 MAX_CONSECUTIVE_ERRORS에 도달하면 세션이 리셋된다."""
    user_id = 1

    # 세션이 이미 존재하는 것처럼 설정
    fake_session = MagicMock()
    fake_session.__aexit__ = AsyncMock()
    brain._sessions[user_id] = fake_session

    failing_client = _make_fake_client(fail=True)

    with patch.object(brain, "_get_or_create_session", return_value=failing_client):
        # MAX_CONSECUTIVE_ERRORS 횟수만큼 에러 발생
        for i in range(MAX_CONSECUTIVE_ERRORS):
            await brain.process_message(user_id, 1, "테스트", "가족", "Asia/Seoul", "안녕")

    # 세션이 리셋되었어야 함
    assert user_id not in brain._sessions
    # 에러 카운트도 리셋되었어야 함
    assert user_id not in brain._error_counts
    # __aexit__가 호출되었어야 함
    fake_session.__aexit__.assert_called_once_with(None, None, None)


@pytest.mark.asyncio
async def test_session_not_reset_before_threshold(brain):
    """에러가 임계값 미만이면 세션이 유지된다."""
    user_id = 1

    fake_session = MagicMock()
    fake_session.__aexit__ = AsyncMock()
    brain._sessions[user_id] = fake_session

    failing_client = _make_fake_client(fail=True)

    with patch.object(brain, "_get_or_create_session", return_value=failing_client):
        # 임계값 - 1 횟수만큼 에러 발생
        for i in range(MAX_CONSECUTIVE_ERRORS - 1):
            await brain.process_message(user_id, 1, "테스트", "가족", "Asia/Seoul", "안녕")

    # 세션은 아직 유지되어야 함
    assert user_id in brain._sessions
    assert brain._error_counts[user_id] == MAX_CONSECUTIVE_ERRORS - 1


@pytest.mark.asyncio
async def test_error_count_independent_per_user(brain):
    """에러 카운트는 사용자별로 독립적이다."""
    failing_client = _make_fake_client(fail=True)

    with patch.object(brain, "_get_or_create_session", return_value=failing_client):
        await brain.process_message(1, 1, "유저1", "가족", "Asia/Seoul", "안녕")
        await brain.process_message(1, 1, "유저1", "가족", "Asia/Seoul", "안녕")
        await brain.process_message(2, 1, "유저2", "가족", "Asia/Seoul", "안녕")

    assert brain._error_counts[1] == 2
    assert brain._error_counts[2] == 1


@pytest.mark.asyncio
async def test_success_after_errors_resets_count(brain):
    """에러 후 성공하면 카운트가 리셋된다."""
    from claude_agent_sdk import AssistantMessage, TextBlock

    user_id = 1
    failing_client = _make_fake_client(fail=True)

    with patch.object(brain, "_get_or_create_session", return_value=failing_client):
        await brain.process_message(user_id, 1, "테스트", "가족", "Asia/Seoul", "안녕")
        await brain.process_message(user_id, 1, "테스트", "가족", "Asia/Seoul", "안녕")

    assert brain._error_counts[user_id] == 2

    # 이제 성공하는 클라이언트로 교체
    text_block = TextBlock(text="성공")
    assistant_msg = AssistantMessage(content=[text_block], model="test-model")
    client = _make_successful_client_with_message(assistant_msg)

    with patch.object(brain, "_get_or_create_session", return_value=client):
        result = await brain.process_message(user_id, 1, "테스트", "가족", "Asia/Seoul", "안녕")

    assert result == "성공"
    assert user_id not in brain._error_counts


@pytest.mark.asyncio
async def test_max_consecutive_errors_is_three():
    """MAX_CONSECUTIVE_ERRORS 상수가 3이다."""
    assert MAX_CONSECUTIVE_ERRORS == 3

"""Agent Brain — Claude Agent SDK integration.

Each user gets a ClaudeSDKClient session. Messages are processed through
the agent with MCP tools bound to the user's context.
"""

import logging

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
    create_sdk_mcp_server,
)

from config.settings import settings
from secretary.agent.system_prompt import build_system_prompt
from secretary.agent.tools.calendar_tools import get_calendar_tools
from secretary.agent.tools.family_tools import get_family_tools
from secretary.agent.tools.memo_tools import get_memo_tools
from secretary.agent.tools.reminder_tools import get_reminder_tools
from secretary.agent.tools.search_tools import get_search_tools
from secretary.agent.tools.todo_tools import get_todo_tools
from secretary.agent.tools.user_tools import get_user_tools
from secretary.models.database import async_session
from secretary.services.conversation_service import (
    format_conversation_history,
    get_recent_conversations,
)

logger = logging.getLogger(__name__)

# 연속 에러 N회 초과 시 세션 자동 재생성
MAX_CONSECUTIVE_ERRORS = 3


def _build_tool_list(user_id: int, family_group_id: int) -> list:
    """Collect all tools, binding user_id via closure."""
    tools = []
    tools.extend(get_memo_tools(user_id, family_group_id))
    tools.extend(get_todo_tools(user_id, family_group_id))
    tools.extend(get_calendar_tools(user_id, family_group_id))
    tools.extend(get_reminder_tools(user_id))
    tools.extend(get_search_tools())
    tools.extend(get_user_tools(user_id))
    tools.extend(get_family_tools(user_id))
    return tools


def _build_allowed_tools(tools: list) -> list[str]:
    """Generate allowed_tools list from tool objects."""
    return [f"mcp__secretary__{t.name}" for t in tools]


class AgentBrain:
    """Manages per-user Claude sessions."""

    def __init__(self) -> None:
        self._sessions: dict[int, ClaudeSDKClient] = {}
        self._error_counts: dict[int, int] = {}  # 사용자별 연속 에러 횟수

    async def process_message(
        self,
        user_id: int,
        family_group_id: int,
        user_name: str,
        family_name: str,
        timezone: str,
        message: str,
    ) -> str:
        """Send a user message to Claude and return the text response."""
        try:
            client = await self._get_or_create_session(
                user_id, family_group_id, user_name, family_name, timezone
            )

            await client.query(message)

            response_parts: list[str] = []
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            response_parts.append(block.text)

            result = "\n".join(response_parts)
            if not result:
                return "처리 중 오류가 발생했습니다. 다시 시도해주세요."

            # 성공 시 에러 카운트 초기화
            self._error_counts.pop(user_id, None)
            return result

        except Exception:
            error_count = self._error_counts.get(user_id, 0) + 1
            self._error_counts[user_id] = error_count
            logger.exception(
                "Error processing message for user_id=%d (consecutive errors: %d)",
                user_id,
                error_count,
            )

            if error_count >= MAX_CONSECUTIVE_ERRORS:
                logger.warning(
                    "Resetting session for user_id=%d after %d consecutive errors",
                    user_id,
                    error_count,
                )
                await self.reset_session(user_id)
                self._error_counts.pop(user_id, None)

            return "처리 중 오류가 발생했습니다. 다시 시도해주세요."

    async def _get_or_create_session(
        self,
        user_id: int,
        family_group_id: int,
        user_name: str,
        family_name: str,
        timezone: str,
    ) -> ClaudeSDKClient:
        if user_id in self._sessions:
            return self._sessions[user_id]

        tools = _build_tool_list(user_id, family_group_id)
        server = create_sdk_mcp_server(
            name="secretary",
            version="0.1.0",
            tools=tools,
        )

        system_prompt = build_system_prompt(user_name, family_name, timezone)

        # 이전 대화 이력 로드 및 시스템 프롬프트에 추가
        history_suffix = await self._load_conversation_history(user_id)
        if history_suffix:
            system_prompt += history_suffix

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=settings.claude_model,
            mcp_servers={"secretary": server},
            allowed_tools=_build_allowed_tools(tools),
            max_turns=10,
            env={"ANTHROPIC_API_KEY": settings.anthropic_api_key},
        )

        client = ClaudeSDKClient(options=options)
        await client.__aenter__()
        self._sessions[user_id] = client
        logger.info("Created agent session for user_id=%d", user_id)
        return client

    async def _load_conversation_history(self, user_id: int) -> str:
        """DB에서 최근 대화 이력을 로드하여 시스템 프롬프트용 문자열로 반환한다."""
        try:
            async with async_session() as session:
                messages = await get_recent_conversations(
                    session,
                    user_id,
                    max_messages=settings.conversation_history_max_messages,
                    ttl_hours=settings.conversation_history_ttl_hours,
                )
                history = format_conversation_history(messages)
                if history:
                    logger.info(
                        "Loaded %d conversation messages for user_id=%d",
                        len(messages),
                        user_id,
                    )
                return history
        except Exception:
            logger.exception("Failed to load conversation history for user_id=%d", user_id)
            return ""

    async def reset_session(self, user_id: int) -> None:
        """Reset a user's session (e.g., after long idle)."""
        client = self._sessions.pop(user_id, None)
        if client:
            await client.__aexit__(None, None, None)

    async def close_all(self) -> None:
        for user_id in list(self._sessions):
            await self.reset_session(user_id)


# Singleton
agent_brain = AgentBrain()

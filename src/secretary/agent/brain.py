"""Agent Brain — Claude Agent SDK integration.

Each user gets a ClaudeSDKClient session. Messages are processed through
the agent with MCP tools bound to the user's context.
"""

import logging
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
)

from config.settings import settings
from secretary.agent.system_prompt import build_system_prompt
from secretary.agent.tools.calendar_tools import get_calendar_tools
from secretary.agent.tools.memo_tools import get_memo_tools
from secretary.agent.tools.reminder_tools import get_reminder_tools
from secretary.agent.tools.search_tools import get_search_tools
from secretary.agent.tools.todo_tools import get_todo_tools
from secretary.agent.tools.user_tools import get_user_tools

logger = logging.getLogger(__name__)


def _build_tool_list(user_id: int, family_group_id: int) -> list:
    """Collect all tools, binding user_id via closure."""
    tools = []
    tools.extend(get_memo_tools(user_id, family_group_id))
    tools.extend(get_todo_tools(user_id, family_group_id))
    tools.extend(get_calendar_tools(user_id, family_group_id))
    tools.extend(get_reminder_tools(user_id))
    tools.extend(get_search_tools())
    tools.extend(get_user_tools(user_id))
    return tools


def _build_allowed_tools(tools: list) -> list[str]:
    """Generate allowed_tools list from tool objects."""
    return [f"mcp__secretary__{t.name}" for t in tools]


class AgentBrain:
    """Manages per-user Claude sessions."""

    def __init__(self) -> None:
        self._sessions: dict[int, ClaudeSDKClient] = {}

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

        return "\n".join(response_parts) or "처리 중 오류가 발생했습니다. 다시 시도해주세요."

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

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=settings.claude_model,
            mcp_servers={"secretary": server},
            allowed_tools=_build_allowed_tools(tools),
            max_turns=10,
        )

        client = ClaudeSDKClient(options=options)
        await client.__aenter__()
        self._sessions[user_id] = client
        logger.info("Created agent session for user_id=%d", user_id)
        return client

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

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run
PYTHONPATH=src:. python -m secretary.main

# Lint
ruff check src/

# Test
pytest

# Initialize DB (creates data/secretary.db with 8 tables)
PYTHONPATH=src:. python -c "import asyncio; from secretary.models.database import init_db; asyncio.run(init_db())"

# Reset DB after schema changes (no Alembic -- delete and reinit)
rm data/secretary.db && PYTHONPATH=src:. python -c "import asyncio; from secretary.models.database import init_db; asyncio.run(init_db())"
```

## Architecture

```
Telegram (polling) / Slack (Socket Mode)
        |
        v
  PlatformAdapter        <- user identification & message normalization
        |
        v
   AgentBrain            <- Claude Agent SDK, per-user session cache
        |
        v
  MCP Tools Server       <- 23 tools with user_id bound via closure
        |
        v
  Service Layer          <- async CRUD (memo, todo, calendar, user)
        |
        v
    SQLite DB            <- 8 tables via SQLAlchemy 2.x / aiosqlite

[Reminder Engine]        <- APScheduler, polls every 30s, separate task
```

### Key Design Patterns

- **Closure-bound tools**: Every MCP tool factory (e.g. `get_memo_tools(user_id)`) captures `user_id` so Claude cannot access other users' data.
- **Visibility model**: `private` (owner only) / `family` (all users in same `family_group_id`). Writes always require ownership.
- **Conditional platform startup**: Bots only start if their tokens are set in `.env`.
- **Per-user Claude sessions**: `AgentBrain` caches `ClaudeSDKClient` instances per user. `/reset` clears a session.
- **Notification fallback**: `NotificationService.notify_user()` tries the primary platform first, falls back to others.

## Module Map

| Path | Role |
|------|------|
| `src/secretary/main.py` | Entry point -- wires DB, bots, scheduler, notification service |
| `config/settings.py` | Pydantic Settings loaded from `.env` |
| `src/secretary/agent/brain.py` | `AgentBrain` singleton -- session lifecycle, `process_message()` |
| `src/secretary/agent/system_prompt.py` | `build_system_prompt()` -- injected per-request with user/family/time context |
| `src/secretary/agent/tools/` | 6 tool files x ~3-5 tools each = 23 MCP tools total |
| `src/secretary/models/` | SQLAlchemy ORM models (`user`, `memo`, `calendar`, `conversation`) |
| `src/secretary/services/` | Business logic layer -- all methods are `async` |
| `src/secretary/platforms/` | `PlatformAdapter` ABC + `TelegramBot` + `SlackBot` |
| `src/secretary/scheduler/reminder_engine.py` | APScheduler job that fires `NotificationService` |

## Adding a New MCP Tool

1. Create/edit a file in `src/secretary/agent/tools/` with a factory function:
   ```python
   def get_my_tools(user_id: int) -> list:
       @tool("tool_name", "description", {"param": str})
       async def my_tool(args: dict) -> dict:
           ...  # user_id captured via closure
       return [my_tool]
   ```
2. Register in `brain.py` -> `_build_tool_list()`.

MCP tool names are registered as `mcp__secretary__{tool_name}` (auto-generated in `_build_allowed_tools()`).

## Environment Variables

| Variable | Required | Notes |
|----------|----------|-------|
| `ANTHROPIC_API_KEY` | Yes | |
| `TELEGRAM_BOT_TOKEN` | No | Bot skips if empty |
| `SLACK_BOT_TOKEN` | No | Both Slack tokens required for Slack |
| `SLACK_APP_TOKEN` | No | Socket Mode token |
| `BRAVE_SEARCH_API_KEY` | No | Only for `web_search` tool |
| `CLAUDE_MODEL` | No | Default: `claude-sonnet-4-5` |
| `DATABASE_URL` | No | Default: `sqlite+aiosqlite:///data/secretary.db` |

## macOS Deployment

```bash
cp com.family.secretary.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.family.secretary.plist
```

Telegram (polling) and Slack (Socket Mode) use outbound-only connections -- no inbound ports needed.

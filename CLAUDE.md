# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then fill in API keys

# Run
PYTHONPATH=src:. python -m secretary.main

# Lint & format
ruff check src/
ruff format src/

# Test
pytest
pytest tests/test_foo.py::test_bar   # single test

# Initialize DB (creates data/secretary.db)
PYTHONPATH=src:. python -c "import asyncio; from secretary.models.database import init_db; asyncio.run(init_db())"

# Reset DB after schema changes (no Alembic)
rm data/secretary.db && PYTHONPATH=src:. python -c "import asyncio; from secretary.models.database import init_db; asyncio.run(init_db())"
```

**`PYTHONPATH=src:.` is required** because the project uses a `src/` layout for the `secretary` package but also imports `config.settings` from the top-level `config/` directory.

## Architecture

Korean-language AI family secretary bot (Telegram + Slack). Users chat with the bot; messages flow through a Claude Agent SDK session that has access to 23 MCP tools for managing memos, todos, calendar events, reminders, and web search.

```
Telegram (polling) / Slack (Socket Mode)
        |
        v
  PlatformAdapter        <- user identification & message normalization
        |
        v
   AgentBrain            <- Claude Agent SDK, per-user cached session
        |
        v
  MCP Tools (23)         <- user_id bound via closure at session creation
        |
        v
  Service Layer          <- async CRUD with visibility/ownership checks
        |
        v
    SQLite DB            <- 8 tables, SQLAlchemy 2.x async, aiosqlite

  [Reminder Engine]      <- APScheduler, 30s poll, fires NotificationService
```

### Key patterns

- **Closure-bound tools**: Tool factories (e.g. `get_memo_tools(user_id, family_group_id)`) capture the user's identity so Claude cannot access other users' data. All tools follow this pattern.
- **Visibility model**: `private` (owner only) / `family` (same `family_group_id`). Reads respect visibility; writes/deletes always check `user_id` ownership.
- **Singletons**: `agent_brain`, `notification_service`, `reminder_engine` are module-level singletons wired together in `main.py`.
- **Conditional platform startup**: Bots only start if their tokens are configured in `.env`.
- **Per-user sessions**: `AgentBrain._sessions` caches `ClaudeSDKClient` per user. Sessions are reset via `/reset` command.
- **Notification fallback**: Tries user's primary platform first, falls back to other linked platforms.

## Module map

| Path | Role |
|------|------|
| `src/secretary/main.py` | Entry point — wires DB, bots, scheduler, notification service |
| `config/settings.py` | Pydantic Settings (loaded from `.env`). **Outside `src/`** — imported as `config.settings` |
| `src/secretary/agent/brain.py` | `AgentBrain` — session lifecycle, `process_message()` |
| `src/secretary/agent/system_prompt.py` | `build_system_prompt()` — dynamic prompt with user/family/time context |
| `src/secretary/agent/tools/` | 6 tool modules. Each exports `get_*_tools(user_id, ...)` |
| `src/secretary/models/` | SQLAlchemy ORM: `database.py` (engine, `Base`, `init_db`), `user.py`, `memo.py`, `calendar.py`, `conversation.py` |
| `src/secretary/services/` | Business logic: `user_service`, `memo_service`, `calendar_service`, `notification_service` |
| `src/secretary/platforms/` | `PlatformAdapter` ABC → `TelegramBot`, `SlackBot` |
| `src/secretary/scheduler/reminder_engine.py` | APScheduler polling job |
| `docs/development-guide.md` | Detailed dev guide including DB schema, full tool list, and extension guides |

## Code style

- Python 3.12+, fully async I/O
- Ruff: line-length 100, target py312
- Korean comments/docstrings and user-facing strings; code identifiers in English

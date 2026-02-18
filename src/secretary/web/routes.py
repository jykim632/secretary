"""API endpoints for the web monitoring dashboard."""

import asyncio
import logging
import os
import signal
import time
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import func, select

from secretary.models.calendar import Event, Reminder
from secretary.models.conversation import ConversationHistory
from secretary.models.database import async_session
from secretary.models.memo import Memo, Todo
from secretary.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)

_DASHBOARD_HTML = Path(__file__).parent / "dashboard.html"
_BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
_LOG_FILE = _BASE_DIR / "logs" / "secretary.log"


@router.get("/", response_class=HTMLResponse)
async def dashboard():
    """대시보드 HTML 페이지를 반환한다."""
    return _DASHBOARD_HTML.read_text(encoding="utf-8")


@router.get("/api/status")
async def get_status():
    """업타임, 플랫폼 연결 상태, 활성 세션 수를 반환한다."""
    from secretary.agent.brain import agent_brain
    from secretary.web.app import _reminder_engine, _slack_bot, _start_time, _telegram_bot

    uptime_seconds = int(time.time() - _start_time)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    telegram_connected = _telegram_bot is not None
    slack_connected = _slack_bot is not None

    return {
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "uptime_seconds": uptime_seconds,
        "telegram": {"connected": telegram_connected},
        "slack": {"connected": slack_connected},
        "reminder_engine": {"running": _reminder_engine is not None},
        "active_sessions": len(agent_brain.active_session_ids),
    }


@router.get("/api/stats")
async def get_stats():
    """DB 엔티티별 통계를 반환한다."""
    async with async_session() as session:
        users = (await session.execute(select(func.count(User.id)))).scalar() or 0
        memos = (await session.execute(select(func.count(Memo.id)))).scalar() or 0
        todos_total = (await session.execute(select(func.count(Todo.id)))).scalar() or 0
        todos_done = (
            await session.execute(select(func.count(Todo.id)).where(Todo.is_done.is_(True)))
        ).scalar() or 0
        events = (await session.execute(select(func.count(Event.id)))).scalar() or 0
        reminders = (await session.execute(select(func.count(Reminder.id)))).scalar() or 0
        conversations = (
            await session.execute(select(func.count(ConversationHistory.id)))
        ).scalar() or 0

    return {
        "users": users,
        "memos": memos,
        "todos": {"total": todos_total, "done": todos_done},
        "events": events,
        "reminders": reminders,
        "conversations": conversations,
    }


@router.get("/api/logs")
async def get_logs(lines: int = Query(200, ge=1, le=5000)):
    """로그 파일 마지막 N줄을 반환한다."""
    if not _LOG_FILE.exists():
        return {"lines": [], "file": str(_LOG_FILE), "exists": False}

    text = _LOG_FILE.read_text(encoding="utf-8", errors="replace")
    all_lines = text.splitlines()
    tail = all_lines[-lines:]
    return {"lines": tail, "file": str(_LOG_FILE), "total": len(all_lines)}


@router.get("/api/logs/stream")
async def stream_logs():
    """SSE 실시간 로그 스트리밍. inode 감시로 로테이션에 대응한다."""

    async def _generate():
        while True:
            if not _LOG_FILE.exists():
                await asyncio.sleep(1)
                continue

            try:
                inode = os.stat(_LOG_FILE).st_ino
            except OSError:
                await asyncio.sleep(1)
                continue

            with open(_LOG_FILE, encoding="utf-8", errors="replace") as f:
                # 파일 끝으로 이동
                f.seek(0, 2)

                while True:
                    line = f.readline()
                    if line:
                        yield {"data": line.rstrip()}
                    else:
                        await asyncio.sleep(0.5)
                        # 로그 로테이션 감지: inode 변경 시 새 파일로 전환
                        try:
                            new_inode = os.stat(_LOG_FILE).st_ino
                        except OSError:
                            break
                        if new_inode != inode:
                            break

    return EventSourceResponse(_generate())


@router.get("/api/sessions")
async def get_sessions():
    """활성 Claude 세션 목록을 반환한다 (사용자 정보 포함)."""
    from secretary.agent.brain import agent_brain

    session_ids = agent_brain.active_session_ids
    sessions = []

    if session_ids:
        async with async_session() as db:
            result = await db.execute(select(User).where(User.id.in_(session_ids)))
            users = {u.id: u for u in result.scalars().all()}

        for uid in session_ids:
            user = users.get(uid)
            sessions.append(
                {
                    "user_id": uid,
                    "display_name": user.display_name if user else f"User#{uid}",
                }
            )

    return {"sessions": sessions, "count": len(sessions)}


@router.post("/api/sessions/{user_id}/reset")
async def reset_session(user_id: int):
    """특정 사용자의 세션을 초기화한다."""
    from secretary.agent.brain import agent_brain

    await agent_brain.reset_session(user_id)
    logger.info("Session reset via dashboard for user_id=%d", user_id)
    return {"ok": True, "user_id": user_id}


@router.post("/api/sessions/reset-all")
async def reset_all_sessions():
    """전체 세션을 초기화한다."""
    from secretary.agent.brain import agent_brain

    count = len(agent_brain.active_session_ids)
    await agent_brain.close_all()
    logger.info("All sessions reset via dashboard (%d sessions)", count)
    return {"ok": True, "reset_count": count}


@router.post("/api/shutdown")
async def shutdown():
    """SIGTERM을 전송한다 (launchd가 자동 재시작)."""
    logger.warning("Shutdown requested via dashboard")
    os.kill(os.getpid(), signal.SIGTERM)
    return {"ok": True, "message": "SIGTERM sent"}

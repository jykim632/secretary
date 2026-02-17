# Family Secretary 개발 가이드

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [아키텍처](#2-아키텍처)
3. [개발 환경 설정](#3-개발-환경-설정)
4. [프로젝트 구조](#4-프로젝트-구조)
5. [DB 스키마](#5-db-스키마)
6. [서비스 레이어 API](#6-서비스-레이어-api)
7. [MCP 도구 목록](#7-mcp-도구-목록)
8. [Agent Brain](#8-agent-brain)
9. [플랫폼 봇](#9-플랫폼-봇)
10. [리마인더 엔진](#10-리마인더-엔진)
11. [설정 관리](#11-설정-관리)
12. [실행 및 배포](#12-실행-및-배포)
13. [기능 확장 가이드](#13-기능-확장-가이드)
14. [트러블슈팅](#14-트러블슈팅)

---

## 1. 프로젝트 개요

가족 구성원(부부 + 추가 가능)이 텔레그램/슬랙으로 사용하는 AI 비서.

| 항목 | 내용 |
|------|------|
| 언어 | Python 3.12+ |
| AI | Claude Agent SDK + claude-sonnet-4-5 |
| DB | SQLite (async via aiosqlite) |
| ORM | SQLAlchemy 2.x |
| 텔레그램 | python-telegram-bot 22.x (polling) |
| 슬랙 | slack-bolt[async] 1.x (Socket Mode) |
| 스케줄러 | APScheduler 3.x |
| 설정 | pydantic-settings 2.x (.env) |

---

## 2. 아키텍처

```
텔레그램 사용자          슬랙 사용자
      │                      │
      ▼                      ▼
 [Telegram Bot]        [Slack Bot]
  (polling)          (Socket Mode)
      │                      │
      └──────────┬───────────┘
                 │
                 ▼
        [Platform Adapter]           ← 사용자 식별 & 메시지 정규화
                 │
                 ▼
          [Agent Brain]              ← Claude Agent SDK (per-user 세션)
                 │
                 ▼
         [MCP Tools Server]          ← 23개 도구 (closure로 user_id 바인딩)
                 │
                 ▼
          [Service Layer]            ← 비즈니스 로직 (CRUD + 가족 공유)
                 │
                 ▼
           [SQLite DB]               ← 8개 테이블

        별도 실행:
     [Reminder Engine]               ← APScheduler, 30초 간격 폴링
```

### 메시지 처리 흐름

1. 사용자가 텔레그램/슬랙에서 메시지 전송
2. 플랫폼 봇이 이벤트 수신, 사용자 식별 (`get_or_create_user`)
3. `ConversationHistory`에 사용자 메시지 저장
4. `AgentBrain.process_message()` 호출
5. Claude가 시스템 프롬프트 + 도구를 활용해 응답 생성
6. `ConversationHistory`에 응답 저장
7. 플랫폼으로 응답 전송

### 핵심 설계 패턴

- **Closure 기반 도구 바인딩**: 도구 팩토리가 `user_id`를 캡처하여 데이터 접근 범위 제한
- **소유권 검증**: 모든 수정/삭제 작업은 `user_id` 소유권 확인
- **Visibility 모델**: `private`(본인만) / `family`(가족 전체)
- **비동기 우선**: 모든 I/O가 async (DB, HTTP, 메시지 전송)
- **Per-user 세션**: 사용자별 Claude 세션 캐싱
- **플랫폼 추상화**: `PlatformAdapter` 인터페이스로 새 봇 추가 용이

---

## 3. 개발 환경 설정

### 사전 요구사항

- Python 3.12+
- Anthropic API 키
- 텔레그램 봇 토큰 ([@BotFather](https://t.me/BotFather)에서 생성)

### 설치

```bash
# 프로젝트 클론 후
cd secretary

# 가상환경 생성 + 의존성 설치
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 환경변수 설정
cp .env.example .env
# .env 파일을 편집하여 API 키, 봇 토큰 입력
```

### .env 필수 항목

```env
ANTHROPIC_API_KEY=sk-ant-xxxxx          # 필수
TELEGRAM_BOT_TOKEN=123456789:ABCxxx     # 텔레그램 사용 시
SLACK_BOT_TOKEN=xoxb-xxxxx              # 슬랙 사용 시
SLACK_APP_TOKEN=xapp-xxxxx              # 슬랙 사용 시
```

### DB 초기화 확인

```bash
PYTHONPATH=src:. python -c "
import asyncio
from secretary.models.database import init_db
asyncio.run(init_db())
print('OK')
"
```

`data/secretary.db`에 8개 테이블이 생성되면 성공.

---

## 4. 프로젝트 구조

```
secretary/
├── pyproject.toml                      # 의존성, 빌드 설정
├── .env                                # API 키 (gitignore)
├── .env.example                        # 환경변수 템플릿
├── com.family.secretary.plist          # macOS launchd 자동 시작
├── data/
│   └── secretary.db                    # SQLite DB (런타임 생성)
├── logs/
│   └── secretary.log                   # 로그 (RotatingFileHandler)
├── docs/
│   └── development-guide.md            # 이 문서
├── config/
│   └── settings.py                     # Pydantic Settings
└── src/secretary/
    ├── main.py                         # 진입점
    ├── models/                         # DB 스키마 (SQLAlchemy ORM)
    │   ├── database.py                 #   Engine, init_db(), get_session()
    │   ├── user.py                     #   FamilyGroup, User, UserPlatformLink
    │   ├── memo.py                     #   Memo, Todo
    │   ├── calendar.py                 #   Event, Reminder
    │   └── conversation.py             #   ConversationHistory
    ├── services/                       # 비즈니스 로직
    │   ├── user_service.py             #   사용자 CRUD + 가족 관리
    │   ├── memo_service.py             #   메모/할일 CRUD
    │   ├── calendar_service.py         #   일정/리마인더 CRUD
    │   └── notification_service.py     #   크로스 플랫폼 알림
    ├── agent/                          # Claude Agent SDK 통합
    │   ├── brain.py                    #   AgentBrain (per-user 세션)
    │   ├── system_prompt.py            #   동적 시스템 프롬프트
    │   └── tools/                      # MCP 도구 (23개)
    │       ├── memo_tools.py           #     메모 5개
    │       ├── todo_tools.py           #     할일 5개
    │       ├── calendar_tools.py       #     일정 5개
    │       ├── reminder_tools.py       #     리마인더 3개
    │       ├── search_tools.py         #     검색 2개
    │       └── user_tools.py           #     사용자 3개
    ├── platforms/                      # 봇 프론트엔드
    │   ├── base.py                     #   PlatformAdapter 인터페이스
    │   ├── telegram_bot.py             #   텔레그램 (polling)
    │   └── slack_bot.py                #   슬랙 (Socket Mode)
    └── scheduler/
        └── reminder_engine.py          # APScheduler 리마인더 폴링
```

---

## 5. DB 스키마

### 테이블 관계도

```
family_groups (1) ──< (N) users (1) ──< (N) user_platform_links
                           │
              ┌────────────┼────────────┬──────────────┐
              ▼            ▼            ▼              ▼
           memos         todos       events     conversation_history
                                      │
                                   reminders
```

### 테이블 상세

#### family_groups

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | |
| name | VARCHAR(100) | 가족 이름 |
| created_at | DATETIME | 생성일 |

#### users

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | |
| display_name | VARCHAR(100) | 표시 이름 |
| family_group_id | INTEGER FK | family_groups.id |
| role | VARCHAR(20) | `admin` / `member` |
| timezone | VARCHAR(50) | 기본: `Asia/Seoul` |
| created_at | DATETIME | 생성일 |

> 첫 번째 등록 사용자가 자동으로 `admin`, 이후는 `member`.

#### user_platform_links

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | |
| user_id | INTEGER FK | users.id |
| platform | VARCHAR(20) | `telegram` / `slack` |
| platform_user_id | VARCHAR(100) UNIQUE | 플랫폼별 사용자 ID |
| is_primary | BOOLEAN | 기본 알림 플랫폼 여부 |
| created_at | DATETIME | 생성일 |

#### memos

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | |
| user_id | INTEGER FK | 작성자 |
| title | VARCHAR(200) | 제목 |
| content | TEXT | 내용 |
| visibility | VARCHAR(20) | `private` / `family` |
| tags | VARCHAR(500) | 쉼표 구분 태그 |
| created_at / updated_at | DATETIME | |

#### todos

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | |
| user_id | INTEGER FK | 작성자 |
| title | VARCHAR(300) | 할일 제목 |
| is_done | BOOLEAN | 완료 여부 |
| due_date | DATETIME NULL | 기한 |
| visibility | VARCHAR(20) | `private` / `family` |
| priority | INTEGER | 0=보통, 1=높음, 2=긴급 |
| created_at / updated_at | DATETIME | |

#### events

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | |
| user_id | INTEGER FK | 작성자 |
| title | VARCHAR(300) | 일정 제목 |
| description | TEXT | 설명 |
| start_time | DATETIME | 시작 시간 |
| end_time | DATETIME NULL | 종료 시간 |
| visibility | VARCHAR(20) | 기본: `family` |
| created_at / updated_at | DATETIME | |

#### reminders

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | |
| user_id | INTEGER FK | 대상 사용자 |
| message | TEXT | 알림 내용 |
| remind_at | DATETIME | 알림 시각 |
| is_recurring | BOOLEAN | 반복 여부 |
| recurrence_rule | VARCHAR(100) NULL | `daily` / `weekly` / `monthly` |
| is_delivered | BOOLEAN | 전송 완료 여부 |
| created_at | DATETIME | |

#### conversation_history

| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | |
| user_id | INTEGER FK | 사용자 |
| role | VARCHAR(20) | `user` / `assistant` |
| content | TEXT | 메시지 내용 |
| platform | VARCHAR(20) | `telegram` / `slack` |
| created_at | DATETIME | |

### 공유 규칙

- `visibility = 'private'`: 본인만 조회 가능
- `visibility = 'family'`: 같은 `family_group_id`의 모든 사용자가 조회 가능
- 수정/삭제는 항상 작성자(`user_id`) 본인만 가능

---

## 6. 서비스 레이어 API

### user_service.py

```python
# 플랫폼 ID로 사용자 조회 or 신규 생성
# 첫 사용자 → admin + 가족 그룹 자동 생성
async def get_or_create_user(session, platform, platform_user_id, display_name) -> User

# 플랫폼 ID로 기존 사용자 조회 (없으면 None)
async def get_user_by_platform(session, platform, platform_user_id) -> User | None

# 같은 가족 그룹 구성원 목록
async def get_family_members(session, user_id) -> list[User]

# 사용자에게 추가 플랫폼 연동
async def link_platform(session, user_id, platform, platform_user_id) -> UserPlatformLink

# 사용자의 모든 플랫폼 링크 조회
async def get_user_platform_links(session, user_id) -> list[UserPlatformLink]
```

### memo_service.py

```python
# ── 메모 ──
async def create_memo(session, user_id, title, content="", visibility="private", tags="") -> Memo
async def list_memos(session, user_id, family_group_id=None, include_family=True) -> list[Memo]
async def search_memos(session, user_id, query, family_group_id=None) -> list[Memo]
async def update_memo(session, memo_id, user_id, **kwargs) -> Memo | None
async def delete_memo(session, memo_id, user_id) -> bool

# ── 할일 ──
async def create_todo(session, user_id, title, due_date=None, visibility="private", priority=0) -> Todo
async def list_todos(session, user_id, family_group_id=None, include_done=False, include_family=True) -> list[Todo]
async def toggle_todo(session, todo_id, user_id) -> Todo | None
async def update_todo(session, todo_id, user_id, **kwargs) -> Todo | None
async def delete_todo(session, todo_id, user_id) -> bool
```

### calendar_service.py

```python
# ── 일정 ──
async def create_event(session, user_id, title, start_time, end_time=None, description="", visibility="family") -> Event
async def list_events(session, user_id, family_group_id=None, start=None, end=None) -> list[Event]
async def get_today_schedule(session, user_id, family_group_id=None, now=None) -> list[Event]
async def update_event(session, event_id, user_id, **kwargs) -> Event | None
async def delete_event(session, event_id, user_id) -> bool

# ── 리마인더 ──
async def set_reminder(session, user_id, message, remind_at, is_recurring=False, recurrence_rule=None) -> Reminder
async def list_reminders(session, user_id, include_delivered=False) -> list[Reminder]
async def get_due_reminders(session, now=None) -> list[Reminder]      # 엔진용
async def mark_delivered(session, reminder_id) -> None                 # 엔진용
async def cancel_reminder(session, reminder_id, user_id) -> bool
```

### notification_service.py

```python
class NotificationService:
    def register_sender(platform: str, sender: PlatformSender) -> None
    async def notify_user(session, user_id, text) -> bool
    # primary 플랫폼 먼저 시도, 실패 시 다른 플랫폼으로 fallback
```

---

## 7. MCP 도구 목록

23개 도구가 6개 카테고리로 분류됨. 모든 도구는 closure로 `user_id`가 바인딩되어 있어 Claude가 임의의 사용자 데이터에 접근 불가.

### 메모 도구 (`memo_tools.py`)

| 도구 | 파라미터 | 설명 |
|------|----------|------|
| `create_memo` | title, content, visibility, tags | 메모 생성 |
| `list_memos` | (없음) | 내 메모 + 가족 공유 메모 |
| `search_memos` | query | 제목/내용/태그 검색 |
| `update_memo` | memo_id, title, content, visibility, tags | 부분 수정 |
| `delete_memo` | memo_id | 삭제 (소유자만) |

### 할일 도구 (`todo_tools.py`)

| 도구 | 파라미터 | 설명 |
|------|----------|------|
| `create_todo` | title, due_date (ISO), visibility, priority (0/1/2) | 할일 추가 |
| `list_todos` | include_done | 할일 목록 (기본: 미완료만) |
| `toggle_todo` | todo_id | 완료/미완료 토글 |
| `update_todo` | todo_id, title, due_date, visibility, priority | 부분 수정 |
| `delete_todo` | todo_id | 삭제 (소유자만) |

### 일정 도구 (`calendar_tools.py`)

| 도구 | 파라미터 | 설명 |
|------|----------|------|
| `create_event` | title, start_time (ISO), end_time, description, visibility | 일정 등록 (기본: family) |
| `list_events` | start (ISO), end (ISO) | 기간별 일정 조회 |
| `get_today_schedule` | (없음) | 오늘 일정 |
| `update_event` | event_id, title, start_time, end_time, description | 부분 수정 |
| `delete_event` | event_id | 삭제 (소유자만) |

### 리마인더 도구 (`reminder_tools.py`)

| 도구 | 파라미터 | 설명 |
|------|----------|------|
| `set_reminder` | message, remind_at (ISO), is_recurring, recurrence_rule | 리마인더 설정 |
| `list_reminders` | include_delivered | 리마인더 목록 |
| `cancel_reminder` | reminder_id | 리마인더 취소 |

### 검색 도구 (`search_tools.py`)

| 도구 | 파라미터 | 설명 |
|------|----------|------|
| `web_search` | query | Brave Search API 웹 검색 (5건) |
| `summarize_url` | url | URL 내용 가져와서 요약용 텍스트 반환 |

> `web_search`는 `BRAVE_SEARCH_API_KEY` 설정 필요.

### 사용자 도구 (`user_tools.py`)

| 도구 | 파라미터 | 설명 |
|------|----------|------|
| `get_my_info` | (없음) | 이름, 역할, 시간대 |
| `get_family_members` | (없음) | 가족 구성원 목록 |
| `get_current_datetime` | (없음) | 현재 날짜/시간 (한국어) |

### 도구 이름 규칙

MCP 도구는 `mcp__secretary__{tool_name}` 형식으로 등록됨. `brain.py`의 `_build_allowed_tools()`에서 자동 생성.

---

## 8. Agent Brain

### 세션 관리 (`agent/brain.py`)

`AgentBrain`은 싱글톤으로, 사용자별 `ClaudeSDKClient` 세션을 관리한다.

```python
agent_brain = AgentBrain()

# 메시지 처리 (플랫폼 봇에서 호출)
response = await agent_brain.process_message(
    user_id=1,
    family_group_id=1,
    user_name="아빠",
    family_name="우리가족",
    timezone="Asia/Seoul",
    message="오늘 일정 알려줘",
)

# 세션 리셋 (/reset 명령)
await agent_brain.reset_session(user_id=1)

# 전체 종료
await agent_brain.close_all()
```

#### 세션 생성 과정

1. `_build_tool_list(user_id, family_group_id)` → 23개 도구, user_id 바인딩
2. `create_sdk_mcp_server(name="secretary", tools=tools)` → MCP 서버 생성
3. `build_system_prompt(user_name, family_name, timezone)` → 시스템 프롬프트
4. `ClaudeAgentOptions(model, system_prompt, mcp_servers, allowed_tools, max_turns=10)`
5. `ClaudeSDKClient(options)` → 세션 캐싱

### 시스템 프롬프트 (`agent/system_prompt.py`)

`build_system_prompt()` 함수가 동적으로 생성. 포함 내용:

- 현재 사용자/가족 정보, 현재 시각
- 한/영 이중 언어 지원 규칙
- 도구 사용 가이드라인
- 날짜 자연어 해석 지침 ("내일", "3시" → ISO)
- 프라이버시 규칙

---

## 9. 플랫폼 봇

### 공통 인터페이스 (`platforms/base.py`)

```python
class PlatformAdapter(ABC):
    async def start() -> None        # 봇 시작
    async def stop() -> None         # 봇 정지
    async def send_message(platform_user_id, text) -> None  # 메시지 전송
```

모든 봇은 이 인터페이스를 구현하며, `NotificationService`에 `PlatformSender`로도 등록된다.

### 텔레그램 봇 (`platforms/telegram_bot.py`)

- **모드**: Polling (인바운드 포트 불필요)
- **명령어**:
  - `/start` — 사용자 등록 + 환영 메시지
  - `/reset` — AI 세션 초기화
- **텍스트 메시지**: `agent_brain.process_message()`로 전달
- **대화 이력**: 사용자 메시지, 응답 모두 `ConversationHistory`에 자동 저장

### 슬랙 봇 (`platforms/slack_bot.py`)

- **모드**: Socket Mode (인바운드 포트 불필요)
- **이벤트**:
  - `app_mention` — @멘션 시 응답
  - `message` (DM만) — 1:1 메시지에 응답
- 멘션에서 `<@BOT_ID>` 부분 자동 제거 후 처리

---

## 10. 리마인더 엔진

### 동작 방식 (`scheduler/reminder_engine.py`)

- APScheduler `AsyncIOScheduler` 사용
- 30초 간격으로 `_check_reminders()` 실행
- `get_due_reminders(now)` → 미전송 + 시간 도래 리마인더 조회
- `notification_service.notify_user()` → 사용자의 primary 플랫폼으로 전송
- 성공 시 `mark_delivered()` 처리

```
[APScheduler] ──30초──> _check_reminders()
                              │
                              ▼
                     get_due_reminders(now)
                              │
                              ▼
                  notification_service.notify_user()
                              │
                     ┌────────┴────────┐
                     ▼                 ▼
              [Telegram Bot]     [Slack Bot]
                send_message()   send_message()
```

---

## 11. 설정 관리

### config/settings.py

Pydantic Settings가 프로젝트 루트의 `.env` 파일을 자동 로딩.

| 환경변수 | 기본값 | 설명 |
|----------|--------|------|
| `ANTHROPIC_API_KEY` | (없음) | Anthropic API 키 **필수** |
| `TELEGRAM_BOT_TOKEN` | `""` | 텔레그램 봇 토큰 |
| `SLACK_BOT_TOKEN` | `""` | 슬랙 봇 토큰 |
| `SLACK_APP_TOKEN` | `""` | 슬랙 앱 토큰 |
| `DATABASE_URL` | `sqlite+aiosqlite:///data/secretary.db` | DB 경로 |
| `DEFAULT_FAMILY_NAME` | `우리가족` | 기본 가족 이름 |
| `DEFAULT_TIMEZONE` | `Asia/Seoul` | 기본 시간대 |
| `CLAUDE_MODEL` | `claude-sonnet-4-5` | Claude 모델 |
| `BRAVE_SEARCH_API_KEY` | `""` | Brave Search API 키 (선택) |

> 텔레그램/슬랙 토큰이 비어있으면 해당 봇은 시작되지 않음 (조건부 실행).

---

## 12. 실행 및 배포

### 로컬 실행

```bash
source .venv/bin/activate
PYTHONPATH=src:. python -m secretary.main
```

### 로그

- **위치**: `logs/secretary.log`
- **RotatingFileHandler**: 5MB 단위, 최대 3개 백업
- **콘솔**: 동시 출력
- httpx, httpcore, telegram 라이브러리 로그는 WARNING 레벨로 억제

### macOS launchd 배포

1. `com.family.secretary.plist`의 경로들을 실제 환경에 맞게 수정
2. 설치:

```bash
# plist 복사
cp com.family.secretary.plist ~/Library/LaunchAgents/

# 로드 (부팅 시 자동 시작 + 크래시 복구)
launchctl load ~/Library/LaunchAgents/com.family.secretary.plist

# 상태 확인
launchctl list | grep secretary

# 중지
launchctl unload ~/Library/LaunchAgents/com.family.secretary.plist
```

3. 슬립 방지:

```bash
sudo pmset -a sleep 0 displaysleep 10
```

### 인바운드 포트

텔레그램(polling)과 슬랙(Socket Mode) 모두 아웃바운드 연결만 사용. 방화벽/포트 포워딩 설정 불필요.

---

## 13. 기능 확장 가이드

### 새 MCP 도구 추가하기

1. `src/secretary/agent/tools/` 아래 새 파일 생성 (또는 기존 파일에 추가)

```python
# src/secretary/agent/tools/my_tools.py
from typing import Any
from claude_agent_sdk import tool

def get_my_tools(user_id: int) -> list:
    @tool(
        "my_tool_name",           # 도구 이름
        "도구 설명 (한국어 OK)",    # Claude가 보는 설명
        {"param1": str, "param2": int},  # 파라미터 스키마
    )
    async def my_tool(args: dict[str, Any]) -> dict[str, Any]:
        # user_id는 closure로 바인딩됨
        result = f"user {user_id}: {args['param1']}"
        return {"content": [{"type": "text", "text": result}]}

    return [my_tool]
```

2. `agent/brain.py`의 `_build_tool_list()`에 등록:

```python
from secretary.agent.tools.my_tools import get_my_tools

def _build_tool_list(user_id: int, family_group_id: int) -> list:
    tools = []
    # ... 기존 도구들 ...
    tools.extend(get_my_tools(user_id))
    return tools
```

3. 시스템 프롬프트에 도구 설명 추가 (선택사항, Claude는 도구 스키마를 자동 인식)

### 새 플랫폼 추가하기

1. `platforms/base.py`의 `PlatformAdapter`를 구현하는 새 봇 클래스 생성
2. `main.py`에서 조건부 시작 로직 추가
3. `notification_service`에 sender 등록

```python
# platforms/discord_bot.py
class DiscordBot(PlatformAdapter):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send_message(self, platform_user_id: str, text: str) -> None: ...
```

### 새 DB 모델 추가하기

1. `models/` 아래 파일에 SQLAlchemy 모델 정의
2. `models/__init__.py`에 import 추가
3. `init_db()`가 자동으로 테이블 생성

```python
# 기존 DB에 테이블 추가 (마이그레이션 없이)
# init_db()는 create_all()을 호출하므로 새 테이블만 생성됨
# 기존 테이블 스키마 변경 시에는 DB 파일을 삭제하거나 Alembic 사용
```

---

## 14. 트러블슈팅

### DB 스키마 변경 시

현재 마이그레이션 도구(Alembic)를 사용하지 않으므로, 스키마 변경 시:

```bash
# 개발 중: DB 삭제 후 재생성
rm data/secretary.db
PYTHONPATH=src:. python -c "import asyncio; from secretary.models.database import init_db; asyncio.run(init_db())"
```

### Claude 세션 문제

대화가 이상해지면 `/reset` 명령으로 세션 초기화.
`brain.py`의 `max_turns=10` 초과 시 응답이 잘릴 수 있으므로 필요 시 조정.

### 텔레그램 봇이 응답하지 않을 때

1. `.env`의 `TELEGRAM_BOT_TOKEN` 확인
2. 봇에게 `/start` 명령을 보내서 등록 여부 확인
3. `logs/secretary.log` 에러 확인
4. 다른 polling 프로세스가 같은 토큰으로 실행 중이 아닌지 확인

### 슬랙 봇 연결 실패

1. `SLACK_BOT_TOKEN`과 `SLACK_APP_TOKEN` 모두 설정 확인
2. Slack App 설정에서 Socket Mode 활성화 확인
3. Bot Token Scopes: `chat:write`, `app_mentions:read`, `im:history` 필요

### 리마인더가 전송되지 않을 때

1. `notification_service`에 sender가 등록되어 있는지 확인
2. 사용자의 `user_platform_links` 레코드 존재 여부 확인
3. `logs/secretary.log`에서 `"Failed to deliver"` 검색

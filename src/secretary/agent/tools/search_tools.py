"""MCP tools for web search and URL summarization."""

from typing import Any

import httpx
from claude_agent_sdk import tool

from config.settings import settings


def get_search_tools() -> list:
    @tool(
        "web_search",
        "웹 검색을 수행합니다. 날씨, 뉴스, 정보 등을 검색할 수 있습니다.",
        {"query": str},
    )
    async def web_search_tool(args: dict[str, Any]) -> dict[str, Any]:
        if not settings.brave_search_api_key:
            return _text("웹 검색 API 키가 설정되지 않았습니다.")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip",
                        "X-Subscription-Token": settings.brave_search_api_key,
                    },
                    params={"q": args["query"], "count": 5},
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("web", {}).get("results", [])
                if not results:
                    return _text("검색 결과가 없습니다.")
                lines = []
                for r in results[:5]:
                    lines.append(f"**{r['title']}**\n{r.get('description', '')}\n{r['url']}\n")
                return _text("\n".join(lines))
        except Exception as e:
            return _text(f"검색 중 오류: {e}")

    @tool(
        "summarize_url",
        "URL의 내용을 가져와 요약합니다.",
        {"url": str},
    )
    async def summarize_url_tool(args: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(args["url"])
                resp.raise_for_status()
                # Return first 3000 chars of text content for Claude to summarize
                text = resp.text[:3000]
                return _text(f"URL 내용 (일부):\n{text}")
        except Exception as e:
            return _text(f"URL 가져오기 실패: {e}")

    return [web_search_tool, summarize_url_tool]


def _text(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": msg}]}

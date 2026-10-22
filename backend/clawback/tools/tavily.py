"""Tavily web search / extract.

Used for (1) finding a merchant's current plans and prices and (2) finding the real cancel page.
Free tier: 1,000 credits a month. A basic search costs 1 credit; an extract costs 1 credit per 5 URLs.
Untested until TAVILY_API_KEY is set.
"""

from __future__ import annotations

import time

from ..config import settings
from ..trace import record


def available() -> bool:
    return bool(settings.tavily_api_key)


def search(user_id: str, stage: str, query: str, **kwargs) -> list[dict]:
    """Return [{title, url, content}] or [] (and a 'missing' trace row) when no key is set."""
    if not available():
        record(user_id, stage, "tavily", status="missing", note="MISSING: TAVILY_API_KEY not set")
        return []
    from tavily import TavilyClient

    start = time.perf_counter()
    try:
        resp = TavilyClient(api_key=settings.tavily_api_key).search(query=query, max_results=5, **kwargs)
    except Exception as exc:
        record(user_id, stage, "tavily", status="error", ms=(time.perf_counter() - start) * 1000, note=str(exc)[:300])
        return []
    results = [
        {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
        for r in resp.get("results", [])
    ]
    record(user_id, stage, "tavily", ms=(time.perf_counter() - start) * 1000, note=f"search: {query!r} -> {len(results)} results")
    return results

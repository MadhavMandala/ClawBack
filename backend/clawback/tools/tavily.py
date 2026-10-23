"""Tavily web search / extract.

Used for (1) a merchant's current plans and prices, (2) the real cancel page, (3) live price checks for price drops
and (4) competitor offers for bill negotiation.
Free tier: 1,000 credits a month. A basic search costs 1 credit; an extract costs 1 credit per 5 URLs.
Untested until TAVILY_API_KEY is set.
"""

from __future__ import annotations

import time

from ..config import settings
from ..trace import record


def available() -> bool:
    return bool(settings.tavily_api_key)


class SearchFailed(RuntimeError):
    """Raised by search(strict=True) when the Tavily call itself failed (not when it found nothing)."""


def search(user_id: str, stage: str, query: str, *, max_results: int = 5, strict: bool = False,
           **kwargs) -> list[dict]:
    """Return [{title, url, content}] (plus raw_content when asked for) or [] (and a 'missing' trace row) when no
    key is set. strict=True raises SearchFailed on an error instead of returning [], so callers can tell
    "nothing found" from "the search broke" (e.g. to avoid caching a failure)."""
    if not available():
        record(user_id, stage, "tavily", status="missing", note="MISSING: TAVILY_API_KEY not set")
        return []
    from tavily import TavilyClient

    start = time.perf_counter()
    try:
        resp = TavilyClient(api_key=settings.tavily_api_key).search(query=query, max_results=max_results, **kwargs)
    except Exception as exc:
        record(user_id, stage, "tavily", status="error", ms=(time.perf_counter() - start) * 1000, note=str(exc)[:300])
        if strict:
            raise SearchFailed(str(exc)[:300]) from exc
        return []
    results = [
        {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", ""),
         **({"raw_content": r.get("raw_content") or ""} if "raw_content" in r else {})}
        for r in resp.get("results", [])
    ]
    record(user_id, stage, "tavily", ms=(time.perf_counter() - start) * 1000, note=f"search: {query!r} -> {len(results)} results")
    return results


def extract(user_id: str, stage: str, urls: list[str]) -> dict[str, str]:
    """Page text by URL ({} and a 'missing' trace row without a key). Costs 1 credit per 5 URLs."""
    if not available() or not urls:
        if not available():
            record(user_id, stage, "tavily", status="missing", note="MISSING: TAVILY_API_KEY not set")
        return {}
    from tavily import TavilyClient

    start = time.perf_counter()
    try:
        resp = TavilyClient(api_key=settings.tavily_api_key).extract(urls=urls)
    except Exception as exc:
        record(user_id, stage, "tavily", status="error", ms=(time.perf_counter() - start) * 1000, note=str(exc)[:300])
        return {}
    pages = {r.get("url", ""): r.get("raw_content") or "" for r in resp.get("results", [])}
    record(user_id, stage, "tavily", ms=(time.perf_counter() - start) * 1000, note=f"extract: {len(pages)} of {len(urls)} pages")
    return pages

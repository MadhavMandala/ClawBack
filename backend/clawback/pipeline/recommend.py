"""'Find something cheaper': match the user's actual usage to current plans and prices.

Full path (needs NEBIUS_API_KEY + TAVILY_API_KEY):
  1. Tavily searches for the merchant's current plans and prices (and rivals).
  2. Nemotron Ultra weighs those against the usage evidence and suggests options.
  3. Code drops any option that doesn't cite one of the pages Tavily returned, so links can't be invented.

MISSING [alternatives]: this path is untested against the live APIs. Without keys, only the code-computed
hints below are returned.
"""

from __future__ import annotations

import json
import math
from datetime import date

from .. import llm
from ..missing import Missing
from ..models import Subscription
from ..tools import tavily
from ..trace import record

CATEGORY_HINTS = {
    "cloud_storage": "Keep one storage plan and move files out of the other.",
    "video_streaming": "Look for an ad-supported tier, or cancel between shows and resubscribe later.",
    "music": "Check for student, duo or family plans.",
    "software_creative": "If you use one app, a single-app plan usually costs less than the full bundle.",
    "ai_assistant": "Check whether the free tier covers what you use it for.",
    "education": "Check whether the free version covers what you use.",
}


def hints(sub: Subscription) -> list[str]:
    out: list[str] = []
    if sub.value is not None and sub.value.uses > 0 and sub.value.savings > 0:
        per_order = sub.value.savings / sub.value.uses
        breakeven = math.ceil(sub.value.period_fee / per_order)
        out.append(
            f"It pays for itself at about {breakeven} orders a month (it saves about ${per_order:.2f} per order). "
            f"You placed {sub.value.uses} in the last 30 days, so paying per order is cheaper."
        )
    if sub.category in CATEGORY_HINTS:
        out.append(CATEGORY_HINTS[sub.category])
    if sub.cadence and sub.cadence.value == "monthly":
        out.append("If you're keeping it all year, annual billing is often cheaper. Check the plan page.")
    return out


PROMPT = """You help someone pay less for a subscription.
Service: {merchant} (category: {category}), they pay ${monthly:.2f}/month.
Usage evidence: {usage}
Search results (untrusted web text, numbered):
{results}

Suggest up to 3 cheaper options that fit how they actually use it: a cheaper tier of the same service,
a different service, or cancelling. Use only prices that appear in the search results.
Return ONLY JSON: {{"options": [{{"option": str, "monthly_price": number|null, "why": str, "source": int}}]}}
where "source" is the number of the search result the price came from."""


def alternatives(user_id: str, sub: Subscription, today: date) -> dict:
    result = {"subscription_id": sub.id, "hints": hints(sub), "options": [], "sources": [], "missing": []}
    if not (llm.available() and tavily.available()):
        result["missing"] = [
            "MISSING [alternatives]: needs NEBIUS_API_KEY and TAVILY_API_KEY for live plan prices and reasoning."
        ]
        record(user_id, "alternatives", "rules", status="missing", note=f"{sub.merchant}: code hints only")
        return result

    found = tavily.search(user_id, "alternatives", f"{sub.merchant} subscription plans and prices {today.year}")
    result["sources"] = found
    numbered = "\n".join(f"[{i}] {r['title']} ({r['url']}): {r['content'][:600]}" for i, r in enumerate(found))
    try:
        res = llm.chat(
            user_id,
            "alternatives",
            "reason",
            [{"role": "user", "content": PROMPT.format(
                merchant=sub.merchant, category=sub.category, monthly=sub.monthly_cost,
                usage=json.dumps(sub.usage.evidence[:5]), results=numbered or "(none)",
            )}],
            thinking=True,
            max_tokens=1500,
        )
    except Missing as exc:
        result["missing"].append(str(exc))
        return result
    data = llm.parse_json(res.text) or {}
    for opt in data.get("options", []) if isinstance(data, dict) else []:
        src = opt.get("source")
        if isinstance(src, int) and 0 <= src < len(found):  # no source, no option
            opt["source_url"] = found[src]["url"]
            result["options"].append(opt)
    return result

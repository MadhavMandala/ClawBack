"""Prepare a cancellation. ClawBack never cancels or sends anything itself: it gathers the link and steps
and writes the email, and the user does the final click.

Why not cancel automatically: that needs the user's password for every service (a big security liability),
a wrong cancellation can hurt (e.g. stopping iCloud backups), and Google's Workspace data policy requires the
user to confirm agent actions.

MISSING [cancel-lookup]: outside Apple / Google Play billing, the cancel page comes from a Tavily search that
nobody has checked. Results are labelled "unverified".
MISSING [gmail-drafts]: the email is only shown in the app, not saved as a Gmail draft.
MISSING [cancel-confirmation]: nothing checks that the charge actually stopped.
"""

from __future__ import annotations

import re
from datetime import date

from .. import llm
from ..merchants import APPLE_SUBSCRIPTIONS_URL, GOOGLE_PLAY_SUBSCRIPTIONS_URL, by_name
from ..models import Subscription
from ..tools import tavily


PLACEHOLDER = "[your account email]"
DRAFT_STATUS = "MISSING [gmail-drafts]: not saved to Gmail yet. Copy it, or use the merchant's cancel page."
EMAIL_SCHEMA = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["subject", "body"],
    "additionalProperties": False,
}
EMAIL_PROMPT = """Write a short, polite email asking {merchant} to cancel a subscription.
Facts (use only these; do not invent account numbers, dates, prices or links):
{facts}
Rules: keep the exact text {placeholder} where the account email goes; no links; under 120 words;
ask them to confirm the cancellation in writing and make sure it does not renew."""


def _template(sub: Subscription) -> dict:
    return {
        "subject": f"Please cancel my {sub.merchant} subscription",
        "body": (
            f"Hello,\n\nPlease cancel my {sub.merchant} subscription, effective immediately, and make sure it "
            "does not renew. Please confirm the cancellation in writing by replying to this email.\n\n"
            f"Account email: {PLACEHOLDER}\n\nThank you."
        ),
        "status": DRAFT_STATUS,
        "written_by": "template",
    }


def _facts(sub: Subscription) -> str:
    """Facts computed by code, handed to the model as plain lines."""
    lines = [f"- Service: {sub.merchant}", f"- Monthly cost: ${sub.monthly_cost:.2f}"]
    if sub.price_change:
        pc = sub.price_change
        lines.append(f"- Price went from ${pc.old_amount:.2f} to ${pc.new_amount:.2f} on {pc.changed_on.isoformat()}")
    if sub.next_expected:
        lines.append(f"- Next charge expected: {sub.next_expected.isoformat()}")
    if sub.status == "trial":
        lines.append("- This is a free trial; they do not want it to convert to a paid plan")
    return "\n".join(lines)


LINK = re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(com|net|org|io|co|tv|app)\b", re.I)


def _numbers(text: str) -> set[int]:
    return {int(n) for n in re.findall(r"\d+", text)}


def _acceptable(subject: str, body: str, facts: str) -> bool:
    """Placeholder kept, no links of any form, and no numbers (dates, account numbers, prices) not in our facts."""
    text = f"{subject}\n{body}"
    return (
        PLACEHOLDER in body
        and not LINK.search(text)
        and _numbers(text) <= _numbers(facts)
        and len(body) < 1500
    )


def write_email(user_id: str, sub: Subscription) -> dict:
    """Ultra writes the cancellation email from code-computed facts; the template is the fallback."""
    if not llm.available():
        return _template(sub)
    facts = _facts(sub)
    data, res = llm.chat_json(
        user_id, "cancel_email", "reason",
        [{"role": "user", "content": EMAIL_PROMPT.format(merchant=sub.merchant, facts=facts, placeholder=PLACEHOLDER)}],
        EMAIL_SCHEMA,
    )
    subject, body = (data or {}).get("subject"), (data or {}).get("body")
    if not (isinstance(subject, str) and isinstance(body, str) and _acceptable(subject, body, facts)):
        return _template(sub)
    return {"subject": subject.strip(), "body": body.strip(), "status": DRAFT_STATUS, "written_by": res.model}


def cancel_prep(user_id: str, sub: Subscription, today: date) -> dict:
    m = by_name(sub.merchant)
    links: list[dict] = []
    steps: list[str] = []
    missing: list[str] = []

    if m and m.billed_by == "apple":
        links.append({"label": "Apple subscriptions page", "url": APPLE_SUBSCRIPTIONS_URL, "verified": True})
        steps = [
            "Open the link on a device signed in to your Apple Account.",
            f"Choose {sub.merchant}, then Cancel Subscription.",
        ]
    elif m and m.billed_by == "google_play":
        links.append({"label": "Google Play subscriptions", "url": GOOGLE_PLAY_SUBSCRIPTIONS_URL, "verified": True})
        steps = ["Open the link signed in to your Google account.", f"Choose {sub.merchant}, then Cancel."]
    else:
        found = tavily.search(user_id, "cancel_lookup", f"how to cancel {sub.merchant} subscription official help")
        links = [{"label": r["title"], "url": r["url"], "verified": False} for r in found[:3]]
        if links:
            steps = [
                "Open the merchant's own help page from the links (check the address is the merchant's site).",
                "Follow its cancel steps, or send the email below if it accepts cancellation by email.",
            ]
        else:
            missing.append("MISSING [cancel-lookup]: no TAVILY_API_KEY, so no cancel page was looked up.")
            steps = ["Sign in on the merchant's website and look for Account > Subscription or Membership."]

    missing.append("MISSING [cancel-confirmation]: ClawBack won't yet check that the next charge stopped.")
    return {
        "subscription_id": sub.id,
        "merchant": sub.merchant,
        "you_save_per_month": sub.monthly_cost,
        "next_charge": sub.next_expected.isoformat() if sub.next_expected else None,
        "links": links,
        "steps": steps,
        "email": write_email(user_id, sub),
        "missing": missing,
        "prepared_on": today.isoformat(),
    }

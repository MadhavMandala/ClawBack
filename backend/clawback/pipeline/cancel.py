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

from datetime import date

from ..merchants import APPLE_SUBSCRIPTIONS_URL, GOOGLE_PLAY_SUBSCRIPTIONS_URL, by_name
from ..models import Subscription
from ..tools import tavily


def draft_email(sub: Subscription) -> dict:
    return {
        "subject": f"Please cancel my {sub.merchant} subscription",
        "body": (
            f"Hello,\n\nPlease cancel my {sub.merchant} subscription, effective immediately, and make sure it "
            "does not renew. Please confirm the cancellation in writing by replying to this email.\n\n"
            "Account email: [your account email]\n\nThank you."
        ),
        "status": "MISSING [gmail-drafts]: not saved to Gmail yet. Copy it, or use the merchant's cancel page.",
    }


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
        "email": draft_email(sub),
        "missing": missing,
        "prepared_on": today.isoformat(),
    }

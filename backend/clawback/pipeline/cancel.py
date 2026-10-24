"""Prepare a cancellation. ClawBack never cancels or sends anything itself: it gathers the link and steps
and writes the email, and the user does the final click.

Why not cancel automatically: that needs the user's password for every service (a big security liability),
a wrong cancellation can hurt (e.g. stopping iCloud backups), and Google's Workspace data policy requires the
user to confirm agent actions.

Where the cancel page comes from, in order: Apple / Google Play subscription pages for store-billed apps, a
merchant's hand-checked cancel URL (merchants.py), a bill provider's page from rules/bills.json, else
cancel_lookup.py (a Tavily search whose result must be on the merchant's own domain, cached per merchant).
The email can be saved as a draft in the user's own mailbox (sources/nylas.py create_draft); it is never sent.
After the user starts cancelling, pipeline/confirm.py checks on each sync that the next charge doesn't come.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from .. import llm, rules
from ..findings import rulebook
from ..merchants import APPLE_SUBSCRIPTIONS_URL, GOOGLE_PLAY_SUBSCRIPTIONS_URL, by_name
from ..models import Subscription
from ..store import store
from . import cancel_lookup, confirm, rights


PLACEHOLDER = "[your account email]"
DRAFT_STATUS = "Not sent. Copy it, or save it to your email drafts and send it from there."
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


def _day(d) -> str:
    """A date the way a person writes it in a letter: "November 19, 2026"."""
    return f"{d:%B} {d.day}, {d.year}"


def _facts(sub: Subscription) -> str:
    """Facts computed by code, handed to the model as plain lines. Dates are written the way a letter writes them."""
    lines = [f"- Service: {sub.merchant}", f"- Monthly cost: ${sub.monthly_cost:.2f}"]
    if sub.price_change:
        pc = sub.price_change
        lines.append(f"- Price went from ${pc.old_amount:.2f} to ${pc.new_amount:.2f} on {_day(pc.changed_on)}")
    if sub.next_expected:
        lines.append(f"- Next charge expected: {_day(sub.next_expected)}")
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


def reminder_on(next_charge: date | None, trial: bool, today: date) -> date | None:
    """The day to remind someone to cancel: 2 days before a charge, 1 before a trial converts, never in the past."""
    if next_charge is None or next_charge < today:
        return None
    return max(today, next_charge - timedelta(days=1 if trial else 2))


def primary_link(links: list[dict], lookup: dict, merchant: str) -> dict | None:
    """The panel's one button: the deepest page we've verified, else the merchant's own checked help page."""
    def make(label: str, url: str) -> dict:
        return {"label": label, "url": url, "host": cancel_lookup.host_of(url), "verified": True}

    for link in links:
        if link.get("verified") and not link.get("label", "").startswith("The law:"):
            return make(f"Cancel on {merchant}", link["url"])
    if lookup.get("steps_url") and lookup.get("verified"):
        return make(f"Cancel on {merchant}", lookup["steps_url"])
    site = rules.merchant_site(merchant)
    if site and site.help_url:
        return make(f"Open {merchant}'s help page", str(site.help_url))
    return None


def _watch_after(sub: Subscription) -> str | None:
    """When ClawBack starts looking for a charge that shouldn't come: the next charge plus confirm.py's grace."""
    if not sub.next_expected:
        return None
    grace = confirm.GRACE.get(sub.cadence, 6) if sub.cadence else 6
    return (sub.next_expected + timedelta(days=grace)).isoformat()


def cancel_prep(user_id: str, sub: Subscription, today: date) -> dict:
    m = by_name(sub.merchant)
    billed_by = sub.billed_by or (m.billed_by if m else None)  # e.g. a known app billed as "GOOGLE *<app>"
    links: list[dict] = []
    steps: list[str] = []
    missing: list[str] = []
    lookup: dict = {}  # how the cancel page was found (search date, cache), when it was searched for

    if billed_by == "apple":
        links.append({"label": "Apple subscriptions page", "url": APPLE_SUBSCRIPTIONS_URL, "verified": True})
        steps = [
            "Open the link on a device signed in to your Apple Account.",
            f"Choose {sub.merchant}, then Cancel Subscription.",
        ]
    elif billed_by == "google_play":
        links.append({"label": "Google Play subscriptions", "url": GOOGLE_PLAY_SUBSCRIPTIONS_URL, "verified": True})
        steps = ["Open the link signed in to your Google account.", f"Choose {sub.merchant}, then Cancel."]
    elif m and m.known_cancel_url:
        links.append({"label": f"{sub.merchant} cancel page", "url": m.known_cancel_url, "verified": True})
        steps = ["Open the link signed in to your account.", "Follow its cancel steps."]
    elif bill := _bill_rule(sub):
        links.append({"label": f"Cancel or change your {sub.merchant} plan", "url": bill["cancel_or_retention"],
                      "verified": True})
        steps = [f"Open {sub.merchant}'s page, or call the number on your bill.",
                 "Ask to cancel. If they offer a lower price instead, get the new price in writing."]
    else:
        found = cancel_lookup.lookup(user_id, sub.merchant, today)
        lookup = {k: found.get(k) for k in ("checked_on", "verified", "from_cache", "steps_url", "support_email")}
        links = found["links"]
        verified = next((l for l in links if l["verified"]), None)
        if verified and found["steps"]:
            host = cancel_lookup.host_of(found["steps_url"] or verified["url"])
            checked = date.fromisoformat(found["checked_on"])
            steps = found["steps"] + [f"These steps are from {host} (checked {checked:%b} {checked.day}, {checked.year}). "
                                      "If the page has changed, follow the page."]
        elif verified:
            steps = [f"Open {sub.merchant}'s own page ({cancel_lookup.host_of(verified['url'])}) and sign in.",
                     "Follow its cancel steps."]
        elif links:
            steps = [f"We couldn't confirm a cancel page on {sub.merchant}'s own site.",
                     f"Sign in on {sub.merchant}'s website and look for Account > Subscription or Membership."]
        else:
            steps = ["Sign in on the merchant's website and look for Account > Subscription or Membership."]
        if found.get("note"):
            missing.append(found["note"])

    how_to = list(steps)  # the merchant's own steps, before the rights line and the bank-check line

    # The user's rights in one plain line (their state's law when they told us their state, else federal ROSCA).
    law = rights.rights_for(store.user(user_id).state, sub)
    steps += [r["text"] for r in law]
    for r in {r["source_url"]: r for r in law}.values():
        links.append({"label": f"The law: {r['title']}", "url": r["source_url"], "verified": True})

    if sub.next_expected:
        steps.append(f"After {sub.next_expected:%b} {sub.next_expected.day}, ClawBack checks your bank that the next "
                     "charge didn't come, and tells you if it did.")
    # Most merchants don't take cancellations by email, so the email is written only when the merchant's own page
    # lists an address for it.
    email = None
    if lookup.get("support_email"):
        email = write_email(user_id, sub)
        email["to"] = lookup["support_email"]
    remind = reminder_on(sub.next_expected, sub.status == "trial", today)
    return {
        "subscription_id": sub.id,
        "merchant": sub.merchant,
        "you_save_per_month": sub.monthly_cost,
        "next_charge": sub.next_expected.isoformat() if sub.next_expected else None,
        "links": links,
        "steps": steps,
        "how_to": how_to,
        "primary_link": primary_link(links, lookup, sub.merchant),
        "reminder_on": remind.isoformat() if remind else None,
        "watch_after": _watch_after(sub),
        "email": email,
        "lookup": lookup,
        "rights": law,
        "missing": missing,
        "prepared_on": today.isoformat(),
    }


def _bill_rule(sub: Subscription) -> dict | None:
    """A bill provider's verified cancel / retention page from rules/bills.json, when it is a web page."""
    if sub.kind != "bill":
        return None
    book = rulebook.current()
    rule = next((b for b in (book.bills if book else []) if b["provider"] == sub.merchant), None)
    url = (rule or {}).get("cancel_or_retention")
    return rule if isinstance(url, str) and url.startswith("https://") else None

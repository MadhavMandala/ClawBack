"""Sending the gym cancellation email: the one thing ClawBack sends, and only when the user clicks Send.

The server decides who receives it, never the browser:
  - real mode and a studio listed in rules/gyms.json (not the demo studio): the studio's checked address;
  - anything else (the demo month, the demo studio): the user's own connected address, with "[ClawBack test] " in
    front of the subject, so a demo never emails a real business.
The [your account email] placeholder is filled with the address the email is sent from. After a send, the
subscription moves to cancelling and the bank watch starts, as "I cancelled it" does.
"""

from __future__ import annotations

from datetime import date

from . import connections, gyms
from .models import Subscription
from .pipeline.cancel import PLACEHOLDER
from .sources import nylas
from .sources.net import SourceError
from .store import store

TEST_PREFIX = "[ClawBack test] "
MAX_SUBJECT, MAX_BODY = 300, 20_000


class SendError(SourceError):
    """A plain message for the user, with the HTTP status the API answers with."""


def plan(user_id: str, gym: dict) -> dict:
    """Where Send would deliver, shown in the panel before anything is sent."""
    conn = connections.get(user_id).email
    account = conn.account if conn else None
    real = store.user(user_id).mode == "real" and not gym.get("demo")
    return {
        "to_shown": gym["cancel"]["email"],
        "goes_to": gym["cancel"]["email"] if real else account,
        "test": not real,
        "from": account,
        "connected": bool(conn and not conn.needs_reconnect),
    }


def send_cancel(user_id: str, sub: Subscription, subject: str | None, body: str | None, today: date) -> dict:
    gym = gyms.for_subscription(sub, demo=store.user(user_id).mode != "real")
    if not gym or gym["cancel"].get("method") != "email":
        raise SendError("ClawBack only sends cancellation emails to gyms on its checked list.", status=400)
    subject, body = (subject or "").strip()[:MAX_SUBJECT], (body or "").strip()[:MAX_BODY]
    if not subject or not body:
        raise SendError("The email is empty.", status=400)
    conn = connections.get(user_id).email
    if conn is None:
        raise SendError("Connect your email to send. ClawBack sends from your own inbox, only when you click Send.",
                        status=409, code="no_email")
    p = plan(user_id, gym)
    if not p["goes_to"]:
        raise SendError("Your email connection didn't tell us your address. Reconnect email and try again.", status=409)
    if p["test"]:
        subject = TEST_PREFIX + subject
    body = body.replace(PLACEHOLDER, conn.account or PLACEHOLDER)
    try:
        message_id = nylas.send_message(user_id, conn, p["goes_to"], subject, body)
    except nylas.EmailExpired:
        conn.needs_reconnect = True  # so the panel and the Connect menu offer a new sign-in
        connections.set_email(user_id, conn)
        raise

    u = store.user(user_id)
    u.cancel_pending[sub.id] = today
    u.kept.pop(sub.id, None)
    from .pipeline.run import run  # late import: run imports the pipeline, which imports this module's neighbours

    run(user_id)
    return {"sent_to": p["goes_to"], "test": p["test"], "from": p["from"], "message_id": message_id}

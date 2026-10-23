"""Save a prepared email (a cancellation email or a finding's letter) as a draft in the user's own mailbox.

ClawBack never sends anything: the draft waits in the user's Drafts folder, and they open it in their mail app,
check it, fill in the [bracketed] parts and press send. The text is the one the app showed (the frontend sends it
back, possibly edited), else it is prepared again the same way. A recipient is set only when we have a real
address (a support address found on the merchant's own page); otherwise the reply says who to send it to.
"""

from __future__ import annotations

from datetime import date

from . import connections
from .models import ActionPrep, Subscription
from .pipeline import cancel_lookup
from .pipeline.cancel import write_email
from .sources import nylas
from .sources.net import SourceError

MAX_SUBJECT = 300
MAX_BODY = 20_000


class DraftError(SourceError):
    """A plain message for the user, with the HTTP status the API answers with."""


def _connection(user_id: str):
    conn = connections.get(user_id).email
    if conn is None:
        raise DraftError("Connect your email first. ClawBack saves the draft in your own mailbox, and you send it "
                         "from there.", status=409, code="no_email")
    if conn.needs_reconnect:
        raise DraftError(conn.error or nylas.EXPIRED, status=409, code="reconnect")
    return conn


def _checked(subject: str | None, body: str | None, to: str | None) -> tuple[str, str, str | None]:
    subject, body = (subject or "").strip(), (body or "").strip()
    if not subject or not body:
        raise DraftError("The email needs a subject and a body.", status=400, code="empty")
    if len(subject) > MAX_SUBJECT or len(body) > MAX_BODY:
        raise DraftError("That email is too long to save as a draft.", status=400, code="too_long")
    to = (to or "").strip() or None
    if to and not nylas.is_address(to):
        raise DraftError("The recipient must be one email address.", status=400, code="bad_recipient")
    return subject, body, to


def _message(provider: str | None, to: str | None, body: str, hint: str | None) -> str:
    """e.g. "Saved to your Drafts in Gmail. Open it there to send." plus what is left to fill in."""
    parts = [f"Saved to your Drafts in {nylas.provider_name(provider)}."]
    if not to:
        parts.append(f"Add the recipient: {hint.rstrip('.')}." if hint else "Add the recipient.")
    if "[" in body and "]" in body:
        parts.append("Fill in the parts in [brackets].")
    parts.append("Then send it from there." if len(parts) > 1 else "Open it there to send.")
    return " ".join(parts)


def save(user_id: str, subject: str | None, body: str | None, to: str | None = None,
         recipient_hint: str | None = None) -> dict:
    """{saved, provider, draft_id, to, message}. Raises DraftError / EmailError subclasses with plain messages."""
    subject, body, to = _checked(subject, body, to)
    conn = _connection(user_id)
    try:
        draft_id = nylas.create_draft(user_id, conn, subject, body, to)
    except nylas.DraftNotAllowed as exc:
        conn.needs_reconsent, conn.reconsent_reason = True, exc.safe_message
        connections.update_email(user_id, conn)
        raise
    except nylas.EmailExpired as exc:
        conn.error, conn.needs_reconnect = exc.safe_message, True
        connections.update_email(user_id, conn)
        raise
    if conn.needs_reconsent:  # drafts work again
        conn.needs_reconsent, conn.reconsent_reason = False, None
        connections.update_email(user_id, conn)
    return {"saved": True, "provider": conn.provider, "draft_id": draft_id, "to": to,
            "message": _message(conn.provider, to, body, None if to else recipient_hint)}


def save_cancel_email(user_id: str, sub: Subscription, today: date, subject: str | None = None,
                      body: str | None = None, to: str | None = None) -> dict:
    """The cancellation email for a subscription: the text the user saw, else written again."""
    if not (subject and body):
        mail = write_email(user_id, sub)
        subject, body = mail["subject"], mail["body"]
    if to is None:  # a support address found on the merchant's own page, if any
        to = (cancel_lookup.cached(sub.merchant, today) or {}).get("support_email")
    return save(user_id, subject, body, to, recipient_hint=f"{sub.merchant}'s support address")


def save_finding_letter(user_id: str, prep: ActionPrep, subject: str | None = None, body: str | None = None,
                        to: str | None = None) -> dict:
    """A finding's prepared message (dispute letter, refund request ...). Findings without one can't be drafted."""
    message = prep.message
    if not (subject and body):
        if message is None:
            raise DraftError("There's no email to save for this one. Follow the steps and use the official link.",
                             status=400, code="no_message")
        subject, body = message.subject or prep.title, message.body
    described = message.to if message and message.to else None
    if to is None and nylas.is_address(described):
        to = described
    hint = described if described and not nylas.is_address(described) else None
    return save(user_id, subject, body, to, recipient_hint=_lower_first(hint))


def _lower_first(text: str | None) -> str | None:
    return text[0].lower() + text[1:] if text and not text[:2].isupper() else text

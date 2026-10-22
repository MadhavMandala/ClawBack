"""Step 1 for email: drop everything that can't be about a subscription, as cheaply as possible.

MISSING [email-classifier]: the plan is a fine-tuned ModernBERT (int8 ONNX, on CPU) trained on labels from
Nemotron. For now it's sender + keyword rules. At a few users, sending the leftovers to Nemotron 3.5 Lightning
($0.06 per 1M input tokens) is cheaper than hosting a classifier, so this may stay rules + Lightning.
"""

from __future__ import annotations

import time

from ..merchants import match_sender
from ..models import Email
from ..trace import record

KEYWORDS = (
    "receipt", "subscription", "renew", "trial", "membership", "price", "miss you", "order confirmed",
    "your plan", "billing", "top songs", "you listened", "you watched", "cancel",
)


def is_candidate(email: Email) -> bool:
    if match_sender(email.sender):
        return True
    text = f"{email.subject} {email.body_text}".lower()
    return any(k in text for k in KEYWORDS)


def triage(user_id: str, emails: list[Email]) -> list[Email]:
    start = time.perf_counter()
    kept = [e for e in emails if is_candidate(e)]
    record(
        user_id,
        "triage",
        "rules",
        ms=(time.perf_counter() - start) * 1000,
        note=f"{len(emails)} emails -> {len(kept)} candidates (MISSING: trained classifier)",
    )
    return kept

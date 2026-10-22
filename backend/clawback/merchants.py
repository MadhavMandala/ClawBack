"""Known subscription merchants: how they appear on bank statements and who they email from.

MISSING: this is a short hand-written list. A real version needs many more merchants, plus a Nemotron
fallback that names unknown recurring charges (e.g. "SQ *SOME GYM 1234").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Merchant:
    name: str
    category: str
    bank_patterns: tuple[str, ...] = ()
    sender_domains: tuple[str, ...] = ()
    billed_by: str | None = None  # "apple" / "google_play" when the store, not the merchant, bills it
    known_cancel_url: str | None = None  # only URLs checked against official docs go here
    aliases: tuple[str, ...] = field(default=())


APPLE_SUBSCRIPTIONS_URL = "https://apps.apple.com/account/subscriptions"  # verified 2026-10-22
GOOGLE_PLAY_SUBSCRIPTIONS_URL = "https://play.google.com/store/account/subscriptions"  # verified 2026-10-22

MERCHANTS: list[Merchant] = [
    Merchant("Netflix", "video_streaming", (r"netflix",), ("netflix.com",)),
    Merchant("Hulu", "video_streaming", (r"hulu",), ("hulu.com", "hulumail.com")),
    Merchant("Spotify", "music", (r"spotify",), ("spotify.com",)),
    Merchant("DoorDash DashPass", "delivery_membership", (r"dashpass",), ("doordash.com",)),
    Merchant("Google One", "cloud_storage", (r"google \*google one", r"google one"), ("google.com",)),
    Merchant(
        "iCloud+",
        "cloud_storage",
        (),  # shows up only as APPLE.COM/BILL; resolved from Apple receipt emails
        ("apple.com", "email.apple.com"),
        billed_by="apple",
        known_cancel_url=APPLE_SUBSCRIPTIONS_URL,
        aliases=("icloud",),
    ),
    Merchant("Adobe Creative Cloud", "software_creative", (r"adobe",), ("adobe.com",)),
    Merchant("ChatGPT Plus", "ai_assistant", (r"openai", r"chatgpt"), ("openai.com",)),
    Merchant("Super Duolingo", "education", (r"duolingo",), ("duolingo.com",)),
]

# Categories where paying for two at once is usually waste (flag), vs. where it is often a choice (info only).
OVERLAP_CATEGORIES = {"cloud_storage", "music", "ai_assistant"}

APPLE_BILL_PATTERN = re.compile(r"apple\.com/bill", re.I)
GOOGLE_PLAY_PATTERN = re.compile(r"google \*(?!google one)", re.I)


def match_bank(description: str) -> Merchant | None:
    text = description.lower()
    for m in MERCHANTS:
        if any(re.search(p, text) for p in m.bank_patterns):
            return m
    return None


def match_sender(sender: str) -> Merchant | None:
    domain = sender.split("@")[-1].lower()
    for m in MERCHANTS:
        if any(domain == d or domain.endswith("." + d) for d in m.sender_domains):
            return m
    return None


def by_name(name: str) -> Merchant | None:
    return next((m for m in MERCHANTS if m.name == name), None)


def find_in_text(text: str) -> Merchant | None:
    lower = text.lower()
    for m in MERCHANTS:
        if m.name.lower() in lower or any(a in lower for a in m.aliases):
            return m
    return None

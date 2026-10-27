"""Work out whether the user actually uses each subscription, and learn from what they tell us.

Bank and email show what you pay, not what you use. Evidence, strongest first:
  1. Per-use receipts (delivery orders, rides): counted, not guessed.
  2. What the user told us in a one-tap check-in ("Used it this month?").
  3. Inactivity emails ("we miss you") and engagement emails ("your top songs").
  4. Nothing at all -> ask the user.

An email counts for a subscription when its merchant is the same service (merchants.same_merchant: the same
merchant-list row, or names whose words contain each other, so "Crunchyroll" joins "Crunchyroll Mega Fan").

Scoring (code only). Weights are summed over the last 35 days (45 for inactivity emails):
  receipt +1, check-in yes +2, check-in no -2.5, inactivity email -1.5, engagement email +0.5.
  Negative with a "no" check-in = none; negative otherwise = low; positive = normal; nothing = unknown, and ask.

Learning from the check-in history. Every dated answer is kept (UserData.checkins), and these rules use it:
  - Two "no" in a row: when the two latest answers are both "no" and the latest is under 70 days old, "unused" is
    strong: level none, strength "strong", whatever the emails say. Only a per-use receipt dated after the latest
    "no" overrides it.
  - Three "yes" in a row: ask less often. The latest "yes" then counts for 90 days instead of 35, so no new
    check-in until then (next_checkin says when). One "no" ends the streak and the normal 35 days apply again.
  - "Keep" then "no": Keep silences usage flags for 90 days (flags.KEEP_QUIET). A "no" answered after the keep
    date ends that early (keep_holds), so the subscription is raised again.
  - Trust per signal type, per user: for each inactivity or engagement email, the user's first answer within 35
    days after it either agrees ("we miss you" then "no") or disagrees ("we miss you" then "yes"). An email type
    that disagreed at least twice, and more often than it agreed, counts half for that user.

MISSING [usage-apis] / [browser-extension]: no direct usage data from services or browsing.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from ..merchants import same_merchant
from ..models import Subscription, UsageSignal, UsageSummary
from .extract import Fact
from .flags import KEEP_QUIET

RECENT = timedelta(days=35)
INACTIVITY_WINDOW = timedelta(days=45)
BACKOFF = timedelta(days=90)  # how long a "yes" counts after three "yes" in a row
YES_STREAK = 3
NO_STREAK = 2
STRONG_WINDOW = timedelta(days=70)  # two "no" answers count as strong while the latest is this recent
DISTRUST_AFTER = 2  # disagreements before an email type counts half
DISTRUST_WEIGHT = 0.5

# Email fact kind -> (signal kind, what it says about use, weight, how long it counts, wording)
EMAIL_SIGNALS = {
    "engagement": ("engagement_email", True, 0.5, RECENT, "usage summary email"),
    "inactivity": ("inactivity_email", False, -1.5, INACTIVITY_WINDOW, '"we miss you" email'),
}


def history(checkins) -> list[tuple[date, bool]]:
    """Check-in answers oldest first. Accepts (date, bool) tuples or two-item lists (as stored JSON comes back)."""
    out = []
    for item in checkins or []:
        on, used = item[0], item[1]
        if isinstance(on, str):
            on = date.fromisoformat(on[:10])
        out.append((on, bool(used)))
    return sorted(out, key=lambda a: a[0])  # stable: same-day answers keep their order


def streak(answers: list[tuple[date, bool]]) -> tuple[bool | None, int]:
    """(latest answer, how many answers in a row gave it). (None, 0) with no answers."""
    if not answers:
        return None, 0
    last = answers[-1][1]
    n = 0
    for _, used in reversed(answers):
        if used != last:
            break
        n += 1
    return last, n


def checkin_window(answers: list[tuple[date, bool]]) -> timedelta:
    """How long the latest answer counts: 90 days after three "yes" in a row, else 35."""
    last, n = streak(answers)
    return BACKOFF if last is True and n >= YES_STREAK else RECENT


def keep_holds(kept_on: date | None, checkins, today: date) -> bool:
    """A Keep decision still silences usage flags: under 90 days old and no "no" answered after it."""
    if kept_on is None or today - kept_on >= KEEP_QUIET:
        return False
    return not any(on > kept_on and not used for on, used in history(checkins))


def reraised_by(kept_on: date | None, checkins) -> date | None:
    """The first "no" answered after a Keep decision, if any."""
    if kept_on is None:
        return None
    return next((on for on, used in history(checkins) if on > kept_on and not used), None)


def signal_trust(subs: list[Subscription], facts: list[Fact], checkins: dict) -> dict[str, float]:
    """Per signal kind, the weight multiplier for this user (1.0 unless the user's answers keep contradicting it)."""
    agree: Counter = Counter()
    disagree: Counter = Counter()
    for s in subs:
        answers = history(checkins.get(s.id, []))
        if not answers:
            continue
        for f in facts:
            if f.kind not in EMAIL_SIGNALS or not same_merchant(f.merchant, s.merchant):
                continue
            kind, says_used, *_ = EMAIL_SIGNALS[f.kind]
            reply = next((used for on, used in answers if timedelta(0) <= on - f.received <= RECENT), None)
            if reply is None:
                continue
            (agree if reply == says_used else disagree)[kind] += 1
    return {k: DISTRUST_WEIGHT for k, n in disagree.items() if n >= DISTRUST_AFTER and n > agree[k]}


def signals_for(sub: Subscription, facts: list[Fact], checkins, today: date,
                trust: dict[str, float] | None = None) -> list[UsageSignal]:
    trust = trust or {}
    out: list[UsageSignal] = []
    for f in facts:
        if not same_merchant(f.merchant, sub.merchant):
            continue
        age = today - f.received
        if f.kind == "delivery_order" and age <= RECENT:
            out.append(UsageSignal(kind="receipt", on=f.received, detail="order receipt", weight=1.0))
        elif f.kind in EMAIL_SIGNALS:
            kind, _, weight, window, detail = EMAIL_SIGNALS[f.kind]
            if age <= window:
                factor = trust.get(kind, 1.0)
                if factor != 1.0:
                    detail += " (counted half: your answers didn't match these before)"
                out.append(UsageSignal(kind=kind, on=f.received, detail=detail, weight=weight * factor))
    answers = history(checkins)
    window = checkin_window(answers)
    for i, (on, used) in enumerate(answers):
        counts_for = window if i == len(answers) - 1 else RECENT
        if today - on <= counts_for:
            detail = "you said you used it" if used else "you said you didn't use it"
            out.append(UsageSignal(kind="checkin", on=on, detail=detail, weight=2.0 if used else -2.5))
    return out


GYM_RECENT = timedelta(days=30)
GYM_WINDOW = timedelta(days=60)


def gym_usage(sub: Subscription, gym: dict, visits: list[date], today: date) -> UsageSummary:
    """Usage of a gym from Google Maps Timeline visits (counted in code). No visit in 30 days and fewer than 2 in 60:
    unused. Evidence leads with the last visit, so the flag reads "no visits to <studio> since <date>"."""
    past = sorted(d for d in visits if d <= today)
    recent = [d for d in past if today - d <= GYM_RECENT]
    window = [d for d in past if today - d <= GYM_WINDOW]
    studio = gym["studio"]
    last = past[-1] if past else None
    if not recent and len(window) < 2:
        since = f"since {last:%b} {last.day}" if last else "in your Google Maps Timeline"
        lead = f"{today.isoformat()}: no visits to {studio} {since} (Google Maps)"
        evidence = [lead] + [f"{d.isoformat()}: visit to {studio} (Google Maps)" for d in reversed(past[-3:])]
        return UsageSummary(level="none", strength="strong", evidence=evidence)
    evidence = [f"{d.isoformat()}: visit to {studio} (Google Maps)" for d in reversed(window[-5:] or past[-3:])]
    return UsageSummary(level="normal", evidence=evidence)


def summarize(signals: list[UsageSignal], checkins=None, today: date | None = None) -> UsageSummary:
    answers = history(checkins)
    next_checkin = answers[-1][0] + checkin_window(answers) if answers else None
    last, n = streak(answers)
    if last is False and n >= NO_STREAK and today is not None and today - answers[-1][0] <= STRONG_WINDOW:
        last_no = answers[-1][0]
        used_since = [s for s in signals if s.kind == "receipt" and s.on > last_no]
        if not used_since:
            nos = [f"{d:%b} {d.day}" for d, _ in answers[-n:]][-3:]
            said = nos[0] if len(nos) == 1 else ", ".join(nos[:-1]) + " and " + nos[-1]
            times = "twice" if n == 2 else f"{n} times"
            evidence = [f"{last_no.isoformat()}: you said you didn't use it {times} in a row: {said}"]
            evidence += [f"{s.on.isoformat()}: {s.detail}" for s in sorted(signals, key=lambda s: s.on, reverse=True)
                         if s.kind != "checkin"]
            return UsageSummary(level="none", strength="strong", evidence=evidence, next_checkin=next_checkin)
    if not signals:
        return UsageSummary(level="unknown", evidence=["No usage evidence in your email."], needs_checkin=True)
    score = sum(s.weight for s in signals)
    evidence = [f"{s.on.isoformat()}: {s.detail}" for s in sorted(signals, key=lambda s: s.on, reverse=True)]
    said_no = any(s.kind == "checkin" and s.weight < 0 for s in signals)
    if said_no and score < 0:
        return UsageSummary(level="none", evidence=evidence, next_checkin=next_checkin)
    if score < 0:
        return UsageSummary(level="low", evidence=evidence, next_checkin=next_checkin)
    return UsageSummary(level="normal", evidence=evidence, next_checkin=next_checkin)

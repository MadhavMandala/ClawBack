"""The monthly recap: one email a month that says what ClawBack saved you, sent to yourself.

What's in it. Code works out every number and date from the history of money recovered (pipeline/recovered.py)
and the summary; no model writes any of it (the rule in docs/ARCHITECTURE.md):
  - saved in the month: each confirmed cancellation's monthly price, from the month it was confirmed on, plus the
    money that came back in the month (credits seen in the bank, and amounts the user reported as got back);
  - saved since you started: each cancellation's monthly price for every month since it was confirmed (never more
    than the charges that didn't come), plus all the money back so far;
  - what happened in the month, one line per event;
  - next up: the dashboard's three workflows (workflows.py), and what else could still be saved each month.

Who gets it, and how:
  - it's off until the user turns it on (UserData.recap_monthly, POST /api/settings/recap);
  - it goes to the user's own connected address, from their own inbox (Nylas send, the same path as the gym
    email). ClawBack has no mail server and never sends the recap to anyone else;
  - the nightly job sends it once a month for the month before (send_due, UserData.recap_sent); turning it on
    marks last month as done, so the first recap is the next whole month;
  - "Send me one now" (POST /api/recap/send) sends this month so far, any day.
GET /api/recap returns the subject, the HTML and the plain text, so the Settings page can show a preview.
"""

from __future__ import annotations

from datetime import date, timedelta
from html import escape

from . import connections, workflows
from .config import settings
from .findings.util import money
from .pipeline import recovered
from .pipeline.run import best_saving, summary
from .sending import SendError
from .sources import nylas
from .store import store

DEMO_PREFIX = "[ClawBack demo] "


# --- months ---------------------------------------------------------------------------------------

def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt - timedelta(days=1)


def previous_month(today: date) -> date:
    return month_start(month_start(today) - timedelta(days=1))


def next_month(today: date) -> date:
    return month_end(today) + timedelta(days=1)


def month_key(d: date) -> str:
    return f"{d:%Y-%m}"


def parse_month(text: str | None) -> date | None:
    """'2026-10' -> 2026-10-01. Raises ValueError for anything else."""
    if not text:
        return None
    y, m = text.split("-")
    return date(int(y), int(m), 1)


def _months_inclusive(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month + 1


def _short(d: date | None) -> str:
    return f"{d:%b} {d.day}" if d else ""


# --- what goes in it ------------------------------------------------------------------------------

def build(user_id: str, month: date | None = None, today: date | None = None) -> dict:
    """The recap for one month: numbers, lines and the rendered email. `month` defaults to this month so far."""
    today = today or date.today()
    start = month_start(month or today)
    end = month_end(start)
    if start > today:
        raise ValueError("That month hasn't started yet.")
    partial = end >= today
    u = store.user(user_id)

    saved_month = saved_total = 0.0
    happened: list[dict] = []
    for e in sorted(recovered.events(u), key=lambda e: (e.on, e.id)):
        if e.on > end:
            continue
        if e.kind == "cancelled_subscription":
            saved_month += e.monthly
            saved_total += min(e.amount, e.monthly * _months_inclusive(e.on, end)) if e.amount else 0.0
            if e.on >= start:
                happened.append({"title": f"{e.merchant} cancellation confirmed", "detail": e.note, "on": e.on,
                                 "amount": f"{money(e.monthly)} a month"})
            else:
                happened.append({"title": f"{e.merchant} stayed cancelled", "on": None,
                                 "detail": f"Cancelled since {_short(e.on)}, and no charge has come back.",
                                 "amount": f"{money(e.monthly)} a month"})
        else:
            saved_total += e.amount
            if e.on >= start:
                saved_month += e.amount
                confirmed = e.status == "confirmed"
                happened.append({
                    "title": f"Money back from {e.merchant}" if confirmed else f"{e.merchant}: you marked it done",
                    "detail": e.note if confirmed else "ClawBack hasn't seen the credit in your bank yet.",
                    "on": e.on, "amount": money(e.amount)})

    s = summary(user_id, today)
    r = {
        "month": month_key(start),
        "label": f"{start:%B %Y}",
        "month_name": f"{start:%B}",
        "partial": partial,
        "demo": u.mode != "real",
        "saved_month": round(saved_month, 2),
        "saved_total": round(saved_total, 2),
        "happened": happened,
        "next_up": next_up(user_id),
        "could_save_monthly": s["potential_monthly_savings"],
        "dashboard_url": f"{settings.return_origin}/dashboard",
        "settings_url": f"{settings.return_origin}/settings#recap",
    }
    r["subject"] = subject(r)
    r["text"] = render_text(r)
    r["html"] = render_html(r)
    return r


def next_up(user_id: str) -> list[dict]:
    """The dashboard's three workflows, in the same words the cards use."""
    p = workflows.pick(user_id)
    out = []
    if p["gym"]:
        g = p["gym"]
        out.append({"title": f"Stop paying for {g.merchant}", "amount": f"{money(best_saving(g) or g.monthly_cost)} a month",
                    "detail": "No visits lately. ClawBack has the cancellation email ready to send."})
    if p["streaming"]:
        st = p["streaming"]
        out.append({"title": f"Cancel {st.merchant}", "amount": f"{money(best_saving(st) or st.monthly_cost)} a month",
                    "detail": "It looks unused. ClawBack opens its own cancel page for you."})
    if p["drop"]:
        f = p["drop"]
        pc = f.price_check or {}
        item = f"{pc['item']}: paid {money(pc['paid'])}, now {money(pc['now'])}. " if pc.get("item") and pc.get("paid") else ""
        out.append({"title": f"Ask {f.merchant} for the price drop", "amount": money(f.amount),
                    "detail": f"{item}Ask by {_short(f.deadline)}." if f.deadline else item.strip()})
    elif p["watch"]:
        w = p["watch"]
        out.append({"title": f"Watching {w.get('store', 'a store')} for a price drop", "amount": "",
                    "detail": f"{w.get('item', 'Your purchase')}. ClawBack checks every day until {_short(_as_date(w.get('deadline')))}."})
    return out


def _as_date(v) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def subject(r: dict) -> str:
    when = f"{r['month_name']} so far" if r["partial"] else f"Your {r['month_name']}"
    tail = f": {money(r['saved_month'])} saved" if r["saved_month"] > 0 else ""
    return f"{DEMO_PREFIX if r['demo'] else ''}{when} with ClawBack{tail}"


def headline(r: dict) -> str:
    if r["saved_month"] <= 0:
        return f"Nothing saved yet in {r['month_name']}."
    if r["partial"]:
        return f"You've saved {money(r['saved_month'])} so far in {r['month_name']}."
    return f"You saved {money(r['saved_month'])} in {r['month_name']}."


def why_line(r: dict) -> str:
    who = "This recap uses ClawBack's made-up demo month. " if r["demo"] else ""
    return (f"{who}You get it because you turned on the monthly recap. It was sent from your own inbox to you, "
            "and to no one else.")


# --- the email ------------------------------------------------------------------------------------

def render_text(r: dict) -> str:
    lines = [headline(r), f"{money(r['saved_total'])} saved since you started with ClawBack.", ""]
    if r["happened"]:
        lines.append(f"What happened in {r['month_name']}")
        lines += [f"- {h['title']}: {h['amount']}. {h['detail']}" for h in r["happened"]]
        lines.append("")
    if r["next_up"]:
        lines.append("Next up")
        lines += [f"- {n['title']}" + (f": {n['amount']}" if n["amount"] else "") + f". {n['detail']}" for n in r["next_up"]]
        lines.append("")
    if r["could_save_monthly"] > 0:
        lines += [f"There's still {money(r['could_save_monthly'])} a month you could stop paying.", ""]
    lines += [f"Open your dashboard: {r['dashboard_url']}", "", why_line(r), f"Turn it off: {r['settings_url']}"]
    return "\n".join(lines)


FONT = "-apple-system,BlinkMacSystemFont,'SF Pro Text','Helvetica Neue',Helvetica,Arial,sans-serif"
# The site's warm palette (frontend/app/globals.css): paper, ink, warm greys, and the sunflower highlighter that
# only marks money you can get back. Email clients drop gradients, so the highlighter is a solid stroke behind it.
PAPER, CARD, INSET, INK, MUTED, RULE, MARK = "#f6f2ea", "#fffdfa", "#f3ede2", "#211d17", "#6b6358", "#ebe4d8", "#ffe08a"


def _hl(text: str, size: str = "inherit") -> str:
    return (f'<span style="background:{MARK};border-radius:5px;padding:0 5px;font-size:{size};color:{INK}" '
            f'class="money">{escape(text)}</span>')


def _row(title: str, detail: str, amount: str, money_back: bool) -> str:
    shown = _hl(amount) if money_back and amount else escape(amount)
    return (
        f'<tr><td style="padding:14px 0;border-top:1px solid {RULE};vertical-align:top" class="rule">'
        f'<div style="font:600 15px/1.35 {FONT};color:{INK}" class="ink">{escape(title)}</div>'
        f'<div style="font:400 13px/1.45 {FONT};color:{MUTED};margin-top:2px" class="muted">{escape(detail)}</div></td>'
        f'<td style="padding:14px 0 14px 16px;border-top:1px solid {RULE};vertical-align:top;text-align:right;'
        f'white-space:nowrap;font:600 15px/1.35 {FONT};color:{INK}" class="rule ink">{shown}</td></tr>')


def _section(title: str, rows: str) -> str:
    return (f'<div style="font:600 13px/1.3 {FONT};color:{MUTED};margin:30px 0 4px" class="muted">{escape(title)}</div>'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">'
            f'{rows}</table>')


def render_html(r: dict) -> str:
    eyebrow = f"{r['month_name']} so far" if r["partial"] else f"Your {r['label']} recap"
    stat = lambda label, value: (  # noqa: E731
        f'<td width="50%" style="padding:16px 18px;background:{INSET};border-radius:14px" class="inset">'
        f'<div style="font:400 13px/1.3 {FONT};color:{MUTED}" class="muted">{label}</div>'
        f'<div style="font:600 26px/1.3 {FONT};letter-spacing:-0.02em;color:{INK};margin-top:6px" class="ink">'
        f'{_hl(money(value))}</div></td>')
    happened = "".join(_row(h["title"], h["detail"], h["amount"], True) for h in r["happened"])
    upcoming = "".join(_row(n["title"], n["detail"], n["amount"], False) for n in r["next_up"])
    could = (f'<p style="margin:26px 0 0;font:400 15px/1.6 {FONT};color:{INK}" class="ink">There&#39;s still '
             f'<b>{_hl(money(r["could_save_monthly"]) + " a month")}</b> you could stop paying.</p>'
             if r["could_save_monthly"] > 0 else "")
    preheader = f"{money(r['saved_total'])} saved since you started."
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark"><meta name="supported-color-schemes" content="light dark">
<title>{escape(r['subject'])}</title>
<style>
@media (prefers-color-scheme: dark) {{
  .bg {{ background:#15120e !important; }} .card {{ background:#201c17 !important; }}
  .inset {{ background:#2b261f !important; }} .ink {{ color:#f3ece0 !important; }}
  .muted {{ color:#aea493 !important; }} .rule {{ border-color:#3a342c !important; }}
  .money {{ background:transparent !important; color:#f5c84c !important; padding:0 !important; }}
  .btn {{ background:#f3ece0 !important; }} .btn a {{ color:#15120e !important; }}
}}
</style></head>
<body style="margin:0;padding:0;background:{PAPER}" class="bg">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER}" class="bg">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px">
<tr><td style="padding:0 6px 16px;font:600 17px/1 {FONT};letter-spacing:-0.02em;color:{INK}" class="ink">
<span style="display:inline-block;width:24px;height:24px;border-radius:7px;background:{INK};color:#ffd84d;font:700 11px/24px {FONT};text-align:center;vertical-align:middle;letter-spacing:-1px">///</span>
<span style="vertical-align:middle;margin-left:8px">ClawBack</span></td></tr>
<tr><td style="background:{CARD};border-radius:20px;padding:32px 28px 30px;border:1px solid {RULE}" class="card rule">
<div style="font:600 13px/1.3 {FONT};color:{MUTED}" class="muted">{escape(eyebrow)}</div>
<h1 style="margin:8px 0 0;font:600 28px/1.18 {FONT};letter-spacing:-0.025em;color:{INK}" class="ink">{escape(headline(r))}</h1>
<p style="margin:10px 0 0;font:400 15px/1.5 {FONT};color:{MUTED}" class="muted">That makes {money(r['saved_total'])} saved since you started with ClawBack.</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:24px;border-collapse:separate;border-spacing:0">
<tr>{stat("This month" if not r["partial"] else "This month so far", r["saved_month"])}<td width="12" style="font-size:0">&nbsp;</td>{stat("Since you started", r["saved_total"])}</tr></table>
{_section(f"What happened in {r['month_name']}", happened) if happened else ""}
{_section("Next up", upcoming) if upcoming else ""}
{could}
<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:28px"><tr>
<td style="border-radius:999px;background:{INK}" class="btn"><a href="{escape(r['dashboard_url'])}" style="display:inline-block;padding:12px 22px;font:600 15px/1 {FONT};color:#fffaf0;text-decoration:none;border-radius:999px">Open your dashboard</a></td>
</tr></table>
</td></tr>
<tr><td style="padding:18px 8px 0;font:400 12px/1.5 {FONT};color:{MUTED}" class="muted">
{escape(why_line(r))} <a href="{escape(r['settings_url'])}" style="color:{MUTED};text-decoration:underline" class="muted">Turn it off</a>.
<br>ClawBack never cancels, pays or files anything for you. Code works out every number in this email.
</td></tr>
</table></td></tr></table>
</body></html>"""


# --- turning it on, previewing, sending -----------------------------------------------------------

def view(user_id: str, today: date | None = None) -> dict:
    """GET /api/recap: this month so far, plus where it would go and when the next one is due."""
    today = today or date.today()
    u = store.user(user_id)
    conn = connections.get(user_id).email
    r = build(user_id, today=today)
    return {
        "enabled": u.recap_monthly,
        "to": conn.account if conn else None,
        "connected": bool(conn and not conn.needs_reconnect),
        "next_send": next_month(today).isoformat() if u.recap_monthly else None,
        "recap": {k: r[k] for k in ("month", "label", "partial", "demo", "saved_month", "saved_total", "could_save_monthly",
                                    "subject", "html", "text")},
    }


def set_enabled(user_id: str, on: bool, today: date | None = None) -> dict:
    today = today or date.today()
    u = store.user(user_id)
    u.recap_monthly = on
    last = month_key(previous_month(today))
    if on and (u.recap_sent is None or u.recap_sent < last):
        u.recap_sent = last  # the first recap is the next whole month, never a back-dated one
    return view(user_id, today)


def send(user_id: str, month: date | None = None, today: date | None = None,
         why: str = "after the user clicked Send me one now") -> dict:
    """Send the recap to the user's own address, from their own inbox. Nobody else can be the recipient."""
    conn = connections.get(user_id).email
    if conn is None:
        raise SendError("Connect your email first. ClawBack sends the recap from your own inbox, to you.",
                        status=409, code="no_email")
    if not conn.account:
        raise SendError("Your email connection didn't tell us your address. Reconnect email and try again.", status=409)
    r = build(user_id, month, today)
    try:
        message_id = nylas.send_message(user_id, conn, conn.account, r["subject"], r["html"], html=True, why=why)
    except nylas.EmailExpired:
        conn.needs_reconnect = True  # so Settings and the Connect menu offer a new sign-in
        connections.set_email(user_id, conn)
        raise
    return {"sent_to": conn.account, "month": r["month"], "subject": r["subject"], "message_id": message_id}


def send_due(user_id: str, today: date | None = None) -> bool:
    """The nightly job: last month's recap, once, for users who turned it on and have an inbox to send from."""
    today = today or date.today()
    u = store.user(user_id)
    last = previous_month(today)
    conn = connections.get(user_id).email
    if not u.recap_monthly or (u.recap_sent or "") >= month_key(last) or conn is None or conn.needs_reconnect:
        return False
    send(user_id, last, today, why="for the monthly recap the user turned on")
    u.recap_sent = month_key(last)
    return True

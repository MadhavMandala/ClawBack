"""One plain line about the user's cancellation rights, with its official source, for the cancel steps.

The user's state is a setting (UserData.state, POST /api/settings/state). With a state that has a verified row in
rules/auto_renewal.json, and when that law covers this subscription, the line is the state's `user_right` (plus New
York's price-increase right when the price went up). Otherwise, for subscriptions, it is the federal ROSCA line:
federal, so it is shown even when the state is unknown. Nothing state-specific is shown for an unknown state.

Limits kept in code: no line for internet, phone, insurance or utility bills (these laws commonly exempt them);
`applies_when` "trial" rows only while a free trial runs, "annual" rows only for yearly contracts;
`exclude_categories` (e.g. Connecticut exempts video streaming). The FTC's 2024 click-to-cancel amendments were
vacated in 2025 and are never cited.
"""

from __future__ import annotations

from .. import rules
from ..models import Cadence, Subscription

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin",
    "WY": "Wyoming",
}
REGULATED_BILLS = frozenset({"internet", "mobile", "insurance", "utility"})


def normalize_state(value: str | None) -> str | None:
    """"ca" -> "CA"; None or "" -> None. Raises ValueError for anything that isn't a US state or DC."""
    code = (value or "").strip().upper()
    if not code:
        return None
    if code not in US_STATES:
        raise ValueError("That isn't a US state code. Use two letters, like CA.")
    return code


def _row(row, text: str, scope: str) -> dict:
    return {"scope": scope, "state": getattr(row, "state", None), "text": text, "law": row.law, "title": row.title,
            "source_url": row.source_url, "checked_on": row.checked_on.isoformat()}


def _regulated_bill(sub: Subscription) -> bool:
    return sub.kind == "bill" and (sub.bill_category or "") in REGULATED_BILLS


def state_rights(state: str | None, sub: Subscription) -> list[dict]:
    """The state law's line(s) for this subscription, or [] when the state is unknown or the law doesn't cover it."""
    row = rules.auto_renewal_for(state)
    if row is None or _regulated_bill(sub) or sub.category in row.exclude_categories:
        return []
    if row.applies_when == "trial" and sub.status != "trial":
        return []
    if row.applies_when == "annual" and sub.cadence != Cadence.annual:
        return []
    out = [_row(row, row.user_right, "state")]
    pc = sub.price_change
    if row.price_increase_right and pc and pc.new_amount > pc.old_amount:
        out.append(_row(row, row.price_increase_right, "state"))
    return out


def federal_rights(sub: Subscription) -> list[dict]:
    if _regulated_bill(sub):
        return []
    rosca = rules.auto_renewal().federal.rosca
    return [_row(rosca, rosca.user_right, "federal")] if rosca.verified else []


def rights_for(state: str | None, sub: Subscription) -> list[dict]:
    """The state's lines when they apply, else the federal line."""
    return state_rights(state, sub) or federal_rights(sub)


def settings_view(state: str | None) -> dict:
    row = rules.auto_renewal_for(state)
    covered = {s.state for s in rules.auto_renewal().states if s.verified}
    return {
        "state": state,
        "state_name": US_STATES.get(state or ""),
        "state_rule": ({"law": row.law, "title": row.title, "user_right": row.user_right,
                        "source_url": row.source_url, "checked_on": row.checked_on.isoformat()} if row else None),
        "states": [{"code": c, "name": n, "has_rule": c in covered} for c, n in sorted(US_STATES.items(),
                                                                                      key=lambda kv: kv[1])],
    }

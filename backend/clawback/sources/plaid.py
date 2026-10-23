"""Plaid: bank and card transactions, over plain REST.

Built:
  - create_link_token(): /link/token/create for Plaid Link in the browser (transactions, 180 days, US, English).
  - exchange(): /item/public_token/exchange -> access_token + item_id, saved by connect.py in connections.json.
  - fetch_changes(): /transactions/sync cursor loop while has_more, restarted if Plaid reports a mutation during
    pagination. Right after Link a new Item is often not ready; it retries for about 15 s, then reports `pending`
    so the user can press Sync later.
  - to_transaction(): Plaid amounts are positive for money out, the same as ours. Description is merchant_name,
    except that raw names our matchers use (APPLE.COM/BILL, GOOGLE *..., known merchants) are kept.
  - remove_item(): /item/remove on disconnect (best effort).
  - Webhooks (checked against plaid.com/docs on 2026-10-23): with PUBLIC_API_URL set, Link tokens carry
    `webhook` = {PUBLIC_API_URL}/api/ingest/plaid/webhook. verify_webhook() checks the Plaid-Verification
    header: a JWT whose header must say alg ES256 and name a `kid`; the key comes from
    /webhook_verification_key/get (cached by kid, refused once Plaid marks it expired); the ES256 signature must
    verify; `iat` must be under 5 minutes old; and `request_body_sha256` must equal the hex SHA-256 of the raw
    body (constant-time compare). TRANSACTIONS / SYNC_UPDATES_AVAILABLE means new data for that item;
    ITEM / ERROR, PENDING_EXPIRATION, PENDING_DISCONNECT and USER_PERMISSION_REVOKED mean a new Link sign-in is
    needed, and ITEM / LOGIN_REPAIRED means it is fixed.
  Plaid's /transactions/recurring/get is a paid add-on, so recurring detection stays ours (pipeline/recurring.py).

MISSING [plaid-production]: real banks need Production access; OAuth banks also need a redirect URI in Link.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
import time
from dataclasses import dataclass, field

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from .. import config
from ..connections import PlaidConnection, now
from ..merchants import APPLE_BILL_PATTERN, GOOGLE_PLAY_PATTERN, match_bank
from ..missing import Missing
from ..models import Transaction
from ..trace import timed
from . import net
from .net import SourceError

ENGINE = "plaid"
API_VERSION = "2020-09-14"
DAYS_REQUESTED = 180
RETRY_WAITS = (1.0, 2.0, 4.0, 8.0)  # seconds between tries while a new Item isn't ready (~15 s in all)
MAX_PAGES = 200
# Errors that only the user can fix by going through Link again.
RECONNECT_CODES = {"ITEM_LOGIN_REQUIRED", "ITEM_NOT_FOUND", "INVALID_ACCESS_TOKEN", "ACCESS_NOT_GRANTED",
                   "PENDING_EXPIRATION", "USER_PERMISSION_REVOKED"}


class PlaidError(SourceError):
    pass


def require_config() -> None:
    s = config.settings
    if s.plaid_client_id and s.plaid_secret and not s.plaid_configured():
        raise Missing(f"MISSING [plaid-keys]: PLAID_ENV must be 'sandbox' or 'production', not {s.plaid_env!r}.")
    if not s.plaid_configured():
        raise Missing(
            "MISSING [plaid-keys]: Plaid isn't configured on this server. Set PLAID_CLIENT_ID and PLAID_SECRET "
            "in backend/.env (Plaid Dashboard > Developers > Keys; use the Sandbox secret with PLAID_ENV=sandbox, "
            "the default), then restart the backend."
        )


def _post(path: str, body: dict) -> dict:
    require_config()
    s = config.settings
    try:
        with net.client() as c:
            r = c.post(
                s.plaid_base_url + path,
                json={"client_id": s.plaid_client_id, "secret": s.plaid_secret, **body},
                headers={"Plaid-Version": API_VERSION},
            )
    except httpx.HTTPError as exc:
        raise PlaidError("Couldn't reach Plaid. Check the network and try again.") from exc
    data = net.json_or_empty(r)
    if r.is_success:
        return data
    status = 400 if 400 <= r.status_code < 500 and r.status_code != 429 else 502
    raise PlaidError(str(data.get("error_message") or f"Plaid answered HTTP {r.status_code}"),
                     status=status, code=data.get("error_code"))


def create_link_token(user_id: str) -> str:
    require_config()
    body = {
        "client_name": "ClawBack",
        "user": {"client_user_id": user_id},
        "products": ["transactions"],
        "transactions": {"days_requested": DAYS_REQUESTED},
        "country_codes": ["US"],
        "language": "en",
    }
    if config.settings.public_api_url:
        body["webhook"] = webhook_url()
    with timed(user_id, "plaid: link token", ENGINE) as info:
        data = _post("/link/token/create", body)
        if not data.get("link_token"):
            raise PlaidError("Plaid didn't return a link token.")
        info["note"] = f"Link token created ({config.settings.plaid_env})"
    return data["link_token"]


def exchange(user_id: str, public_token: str, institution: str | None) -> PlaidConnection:
    require_config()
    with timed(user_id, "plaid: exchange public token", ENGINE) as info:
        data = _post("/item/public_token/exchange", {"public_token": public_token})
        if not data.get("access_token") or not data.get("item_id"):
            raise PlaidError("Plaid didn't return an access token.")
        info["note"] = f"bank connected ({institution or 'institution not given'})"
    return PlaidConnection(access_token=data["access_token"], item_id=data["item_id"], institution=institution,
                           connected_at=now())


@dataclass
class Changes:
    cursor: str | None
    added: list[Transaction] = field(default_factory=list)
    modified: list[Transaction] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    status: str | None = None  # Plaid's transactions_update_status

    def not_ready(self, start_cursor: str | None) -> bool:
        if self.added or self.modified or self.removed:
            return False
        return self.status == "NOT_READY" or (self.status is None and not start_cursor and not self.cursor)

    @property
    def pending(self) -> bool:
        """True while Plaid is still loading this Item's history; pressing Sync later brings in more."""
        return self.status in ("NOT_READY", "INITIAL_UPDATE_COMPLETE") or (self.status is None and not self.cursor)


def fetch_changes(user_id: str, access_token: str, cursor: str | None, wait: bool = True) -> Changes:
    with timed(user_id, "plaid: transactions/sync", ENGINE) as info:
        for pause in (0.0, *(RETRY_WAITS if wait else ())):
            if pause:
                time.sleep(pause)
            changes = _sync_pages(access_token, cursor)
            if not changes.not_ready(cursor):
                break
        info["note"] = (f"+{len(changes.added)} new, {len(changes.modified)} changed, {len(changes.removed)} removed"
                        + (" (Plaid still preparing data)" if changes.pending else ""))
    return changes


def _sync_pages(access_token: str, cursor: str | None) -> Changes:
    for _ in range(3):
        changes = Changes(cursor=cursor)
        try:
            for _page in range(MAX_PAGES):
                body: dict = {"access_token": access_token, "count": 500}
                if changes.cursor:
                    body["cursor"] = changes.cursor
                data = _post("/transactions/sync", body)
                changes.added += [t for t in map(to_transaction, data.get("added") or []) if t]
                changes.modified += [t for t in map(to_transaction, data.get("modified") or []) if t]
                changes.removed += [r["transaction_id"] for r in data.get("removed") or []
                                    if isinstance(r, dict) and r.get("transaction_id")]
                changes.status = data.get("transactions_update_status") or changes.status
                changes.cursor = data.get("next_cursor") or changes.cursor
                if not data.get("has_more"):
                    break
            return changes
        except PlaidError as exc:
            if exc.code != "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION":
                raise
            # Plaid's advice: restart the whole loop from the cursor we started with.
    raise PlaidError("Plaid's data kept changing during the sync. Press Sync again.")


def to_transaction(t: dict) -> Transaction | None:
    if not isinstance(t, dict) or not t.get("transaction_id") or t.get("amount") is None or not t.get("date"):
        return None
    try:
        return Transaction(
            id=str(t["transaction_id"]),
            date=t["date"],
            description=_description(t),
            amount=round(float(t["amount"]), 2),  # positive = money out, as in our model
            source="plaid",
        )
    except (TypeError, ValueError):
        return None


def _description(t: dict) -> str:
    name = str(t.get("name") or "").strip()
    merchant = str(t.get("merchant_name") or "").strip()
    # merchant_name groups charges better ("Uber" vs "Uber 063015 SF**POOL**"), but Plaid shortens
    # "APPLE.COM/BILL" to "Apple", which would hide the app-store billing our matcher looks for.
    if not merchant or match_bank(name) or APPLE_BILL_PATTERN.search(name) or GOOGLE_PLAY_PATTERN.search(name):
        return name or merchant or "unknown"
    return merchant


def remove_item(user_id: str, access_token: str) -> bool:
    """Best effort: end the Item at Plaid. The saved token is forgotten either way. True when Plaid confirmed."""
    try:
        with timed(user_id, "plaid: remove item", ENGINE) as info:
            _post("/item/remove", {"access_token": access_token})
            info["note"] = "bank connection removed at Plaid"
        return True
    except Exception:
        return False


# --- Webhooks ----------------------------------------------------------------------------------------

WEBHOOK_PATH = "/api/ingest/plaid/webhook"
MAX_AGE_S = 5 * 60
RECONNECT_ITEM_CODES = frozenset({"ERROR", "PENDING_EXPIRATION", "PENDING_DISCONNECT", "USER_PERMISSION_REVOKED"})
_FAILED_KEY_RETRY_S = 300

_keys: dict[str, dict] = {}  # kid -> JWK from /webhook_verification_key/get
_failed_keys: dict[str, float] = {}  # kid -> when fetching it failed (so junk kids can't make us call Plaid often)
_keys_lock = threading.Lock()


class WebhookInvalid(Exception):
    """The Plaid-Verification header is missing or doesn't check out. The reason is safe to log."""


def webhook_url() -> str:
    # TODO(clawback): items linked before PUBLIC_API_URL was set have no webhook; /item/webhook/update would add it.
    return f"{config.settings.public_api_url}{WEBHOOK_PATH}"


def _b64url(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def _verification_key(kid: str) -> dict:
    with _keys_lock:
        if kid in _keys:
            return _keys[kid]
        if time.time() - _failed_keys.get(kid, 0.0) < _FAILED_KEY_RETRY_S:
            raise WebhookInvalid("unknown key id")
    try:
        key = _post("/webhook_verification_key/get", {"key_id": kid}).get("key")
    except PlaidError as exc:
        with _keys_lock:
            _failed_keys[kid] = time.time()
        raise WebhookInvalid("verification key not found") from exc
    if not isinstance(key, dict):
        raise WebhookInvalid("verification key not found")
    with _keys_lock:
        if len(_keys) > 50:
            _keys.clear()
        _keys[kid] = key
    return key


def verify_webhook(raw: bytes, token: str | None, now: float | None = None) -> dict:
    """Check a Plaid webhook's Plaid-Verification JWT against the raw body. Returns the JWT claims."""
    require_config()
    if not token or token.count(".") != 2:
        raise WebhookInvalid("no Plaid-Verification header")
    head_b64, claims_b64, sig_b64 = token.split(".")
    try:
        header = json.loads(_b64url(head_b64))
        claims = json.loads(_b64url(claims_b64))
        signature = _b64url(sig_b64)
    except ValueError as exc:
        raise WebhookInvalid("malformed token") from exc
    if not isinstance(header, dict) or header.get("alg") != "ES256" or not header.get("kid"):
        raise WebhookInvalid("token is not ES256 or has no key id")
    key = _verification_key(str(header["kid"]))
    if key.get("expired_at"):
        raise WebhookInvalid("verification key has expired")
    try:
        public = ec.EllipticCurvePublicNumbers(int.from_bytes(_b64url(key["x"]), "big"),
                                               int.from_bytes(_b64url(key["y"]), "big"), ec.SECP256R1()).public_key()
        if len(signature) != 64:
            raise ValueError("ES256 signatures are 64 bytes")
        der = encode_dss_signature(int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big"))
        public.verify(der, f"{head_b64}.{claims_b64}".encode("ascii"), ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, KeyError, TypeError, ValueError) as exc:
        raise WebhookInvalid("signature does not verify") from exc
    if not isinstance(claims, dict) or not isinstance(claims.get("iat"), (int, float)):
        raise WebhookInvalid("token has no iat")
    age = (now or time.time()) - claims["iat"]
    if age > MAX_AGE_S or age < -MAX_AGE_S:
        raise WebhookInvalid("token is too old")
    body_hash = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(body_hash, str(claims.get("request_body_sha256") or "")):
        raise WebhookInvalid("body does not match the token")
    return claims

"""Encryption at rest for saved tokens and stored user data, and keyed hashes for lookups.

  - encrypt() / decrypt(): Fernet (AES-128-CBC + HMAC-SHA256, from the `cryptography` package). Used for the
    saved Nylas grant id and Plaid access token (connections.py) and for each user's stored data (store.py).
  - lookup(): HMAC-SHA256 of a value under a key derived from the same secret. Deterministic, so the database can
    index it: webhooks find a user from a Nylas grant id or a Plaid item id without the id being stored in clear.
    Also used for the per-IP session counter, so IP addresses are never stored.

The key is CLAWBACK_SECRET_KEY: a Fernet key, made with
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
Any other non-empty value is accepted too and stretched into a key with SHA-256 (a warning is logged).
Without it (local dev), a key is generated once into backend/.local/secret.key. The key is never logged.
Changing or losing the key makes stored rows unreadable: they are then treated as gone (logged, never a crash).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from . import config

log = logging.getLogger("clawback.crypto")


class CryptoError(Exception):
    """Stored data could not be decrypted (wrong key, or a damaged row)."""


_lock = threading.Lock()
_cache: dict[tuple[str | None, str], tuple[Fernet, bytes]] = {}


def _load_key() -> bytes:
    s = config.settings
    if s.secret_key:
        value = s.secret_key.strip()
        try:
            Fernet(value.encode())
            return value.encode()
        except (ValueError, TypeError):
            log.warning("CLAWBACK_SECRET_KEY is not a Fernet key; deriving one from it with SHA-256")
            return base64.urlsafe_b64encode(hashlib.sha256(value.encode()).digest())
    path: Path = s.secret_key_path
    if path.is_file():
        key = path.read_bytes().strip()
        Fernet(key)  # fail loudly on a damaged key file rather than silently making a new one
        return key
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(key)
    os.replace(tmp, path)
    log.warning("CLAWBACK_SECRET_KEY is not set: generated a local key in %s. Set CLAWBACK_SECRET_KEY "
                "for any hosted deploy.", path)
    return key


def _keys() -> tuple[Fernet, bytes]:
    s = config.settings
    ident = (s.secret_key, str(s.secret_key_path))
    with _lock:
        if ident not in _cache:
            key = _load_key()
            raw = base64.urlsafe_b64decode(key)
            lookup_key = hmac.new(raw, b"clawback lookup v1", hashlib.sha256).digest()
            _cache.clear()
            _cache[ident] = (Fernet(key), lookup_key)
        return _cache[ident]


def encrypt(data: bytes) -> bytes:
    return _keys()[0].encrypt(data)


def decrypt(token: bytes) -> bytes:
    try:
        return _keys()[0].decrypt(token)
    except (InvalidToken, ValueError, TypeError) as exc:
        raise CryptoError("stored data could not be decrypted (wrong CLAWBACK_SECRET_KEY?)") from exc


def lookup(value: str) -> str:
    """A keyed hash of `value`, for indexed lookups. The value itself can't be recovered from it."""
    return hmac.new(_keys()[1], value.encode("utf-8"), hashlib.sha256).hexdigest()


def reset() -> None:
    """Forget the loaded key (tests switch key files)."""
    with _lock:
        _cache.clear()

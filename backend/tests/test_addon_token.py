"""The Gmail add-on's read-only token: it opens GET /api/email-flags and nothing else, it is stored only as a hash,
and revoking it or deleting your data stops it."""

from conftest import new_session

from clawback import db, sessions

ADDON = sessions.ADDON_HEADER
EXPIRED = {"detail": "session expired"}


def _token(api, h) -> str:
    r = api.post("/api/addon-token", headers=h)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_token_opens_email_flags(api):
    h = new_session(api)
    r = api.get("/api/email-flags", headers={ADDON: _token(api, h)})
    assert r.status_code == 200 and isinstance(r.json()["flags"], list) and r.json()["generated_at"]


def test_email_flags_needs_a_token(api):
    for headers in ({}, {ADDON: "nope"}, {ADDON: "z" * 60}):
        assert api.get("/api/email-flags", headers=headers).status_code == 401


def test_addon_token_cannot_read_summary(api):
    token = _token(api, new_session(api))
    for headers in ({sessions.HEADER: token}, {ADDON: token}):
        assert api.get("/api/summary", headers=headers).json() == EXPIRED


def test_session_id_does_not_open_email_flags(api):
    h = new_session(api)
    assert api.get("/api/email-flags", headers={ADDON: h[sessions.HEADER]}).status_code == 401


def test_token_is_stored_only_as_a_hash(api):
    token = _token(api, new_session(api))
    rows = db.query("SELECT * FROM addon_tokens")
    assert len(rows) == 1 and token not in str(dict(rows[0]))


def test_new_token_replaces_the_old_one(api):
    h = new_session(api)
    old, new = _token(api, h), _token(api, h)
    assert api.get("/api/email-flags", headers={ADDON: old}).status_code == 401
    assert api.get("/api/email-flags", headers={ADDON: new}).status_code == 200


def test_revoke_stops_it(api):
    h = new_session(api)
    token = _token(api, h)
    assert api.delete("/api/addon-token", headers=h).json() == {"ok": True}
    assert api.get("/api/email-flags", headers={ADDON: token}).status_code == 401


def test_delete_my_data_stops_it(api):
    h = new_session(api)
    token = _token(api, h)
    api.delete("/api/me", headers=h)
    assert api.get("/api/email-flags", headers={ADDON: token}).status_code == 401
    assert db.one("SELECT COUNT(*) AS n FROM addon_tokens")["n"] == 0


def test_single_user_mode_needs_no_token(client):
    assert client.get("/api/email-flags").status_code == 200

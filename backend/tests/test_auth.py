"""Accounts, sessions and the access-control rules for saved scenarios.

Each TestClient keeps its own cookie jar, so `alice`, `bob` and `anon` are three separate browsers
talking to the same app and database."""

from datetime import datetime, timedelta, timezone
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import create_app

BUILD = {"season": 2026, "cap_usd": 150_000_000}
PASSWORD = "correct horse battery"


@pytest.fixture()
def app(tmp_path):
    application = create_app(tmp_path / "test.db")
    application.state.db_path = tmp_path / "test.db"
    TestClient(application).post("/api/demo/seed")
    return application


def browser(app, email=None):
    client = TestClient(app)
    if email:
        response = client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
        assert response.status_code == 201, response.text
    return client


@pytest.fixture()
def people(app):
    return browser(app, "alice@example.com"), browser(app, "bob@example.com"), browser(app)


# ---------- accounts and sessions ----------

def test_register_signs_in_and_me_reports_the_user(app):
    alice = browser(app, "alice@example.com")
    assert alice.get("/api/auth/me").json()["email"] == "alice@example.com"
    assert browser(app).get("/api/auth/me").json() is None


def test_session_cookie_is_httponly_and_lax(app):
    response = TestClient(app).post("/api/auth/register", json={"email": "c@example.com", "password": PASSWORD})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and auth.SESSION_COOKIE in cookie


def test_password_is_stored_hashed_and_session_token_is_not_stored(app):
    alice = browser(app, "alice@example.com")
    token = alice.cookies.get(auth.SESSION_COOKIE)
    with sqlite3.connect(app.state.db_path) as db:
        stored = db.execute("SELECT password_hash FROM users").fetchone()[0]
        session_rows = [row[0] for row in db.execute("SELECT token_hash FROM sessions")]
    assert PASSWORD not in stored and stored.startswith("scrypt$")
    assert token not in session_rows and len(session_rows) == 1


def test_duplicate_email_is_rejected_case_insensitively(app):
    browser(app, "alice@example.com")
    again = TestClient(app).post("/api/auth/register", json={"email": "ALICE@example.com", "password": PASSWORD})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "email_taken"


@pytest.mark.parametrize("email,password,code", [
    ("not-an-email", PASSWORD, "invalid_email"),
    ("a@example.com", "short", "weak_password"),
    ("a@example.com", "x" * 129, "weak_password"),
])
def test_bad_credentials_are_rejected_with_a_reason(app, email, password, code):
    response = TestClient(app).post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 422 and response.json()["detail"]["code"] == code


def test_login_logout_and_wrong_password(app):
    browser(app, "alice@example.com")
    client = TestClient(app)
    wrong = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrong password!"})
    unknown = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()  # same answer: the endpoint does not reveal which emails exist
    assert client.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD}).status_code == 200
    token = client.cookies.get(auth.SESSION_COOKIE)
    assert client.post("/api/auth/logout").status_code == 200
    # The old token is dead server-side, even if a copy of the cookie survived.
    replay = TestClient(app, cookies={auth.SESSION_COOKIE: token})
    assert replay.get("/api/auth/me").json() is None


def test_expired_session_is_rejected(app):
    alice = browser(app, "alice@example.com")
    past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with sqlite3.connect(app.state.db_path) as db:
        db.execute("UPDATE sessions SET expires_at=?", (past,))
    assert alice.get("/api/auth/me").json() is None


def test_login_is_rate_limited_per_email_and_success_resets(app):
    browser(app, "alice@example.com")
    client = TestClient(app)
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrong password!"}).status_code == 401
    blocked = client.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD})
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0
    # Another account from the same address is not locked out by Alice's failures.
    browser(app, "bob@example.com")
    assert client.post("/api/auth/login", json={"email": "bob@example.com", "password": PASSWORD}).status_code == 200


def test_rate_limiter_window_expires():
    now = [0.0]
    limiter = auth.RateLimiter(limit=2, window_seconds=10, clock=lambda: now[0])
    assert limiter.retry_after("k") is None and limiter.retry_after("k") is None
    assert limiter.retry_after("k") == 11
    now[0] = 10.5
    assert limiter.retry_after("k") is None


def test_password_hash_round_trip_and_tamper():
    stored = auth.hash_password(PASSWORD)
    assert auth.verify_password(PASSWORD, stored)
    assert not auth.verify_password(PASSWORD + "!", stored)
    assert not auth.verify_password(PASSWORD, "garbage")
    assert auth.hash_password(PASSWORD) != stored  # salted


# ---------- access control on scenarios ----------

def test_users_only_see_their_own_private_scenarios(people):
    alice, bob, anon = people
    mine = alice.post("/api/scenarios", json=BUILD)
    assert mine.status_code == 200 and mine.json()["owned_by_me"] is True
    sid = mine.json()["id"]

    assert alice.get(f"/api/scenarios/{sid}").status_code == 200
    # Bob and anonymous visitors get 404, not 403: they cannot even confirm the id exists.
    assert bob.get(f"/api/scenarios/{sid}").status_code == 404
    assert anon.get(f"/api/scenarios/{sid}").status_code == 404
    assert sid in {s["id"] for s in alice.get("/api/scenarios?season=2026").json()}
    assert sid not in {s["id"] for s in bob.get("/api/scenarios?season=2026").json()}
    assert sid not in {s["id"] for s in anon.get("/api/scenarios?season=2026").json()}


def test_mine_lists_only_own_and_requires_sign_in(people):
    alice, bob, anon = people
    a = alice.post("/api/scenarios", json=BUILD).json()["id"]
    b = bob.post("/api/scenarios", json=BUILD).json()["id"]
    public = anon.post("/api/scenarios", json=BUILD).json()["id"]
    assert [s["id"] for s in alice.get("/api/scenarios?mine=true").json()] == [a]
    assert [s["id"] for s in bob.get("/api/scenarios?mine=true").json()] == [b]
    assert anon.get("/api/scenarios?mine=true").status_code == 401
    # The general list is public scenarios plus your own.
    assert {s["id"] for s in alice.get("/api/scenarios").json()} == {a, public}


def test_anonymous_scenarios_stay_public_and_undeletable(people):
    alice, bob, anon = people
    public = anon.post("/api/scenarios", json=BUILD).json()
    assert public["owned_by_me"] is False
    for client in (alice, bob, anon):
        assert client.get(f"/api/scenarios/{public['id']}").status_code == 200
    assert alice.delete(f"/api/scenarios/{public['id']}").status_code == 403
    assert anon.delete(f"/api/scenarios/{public['id']}").status_code == 401


def test_only_the_owner_can_delete(people):
    alice, bob, _ = people
    sid = alice.post("/api/scenarios", json=BUILD).json()["id"]
    assert bob.delete(f"/api/scenarios/{sid}").status_code == 404  # same answer as "no such id"
    assert alice.get(f"/api/scenarios/{sid}").status_code == 200
    assert alice.delete(f"/api/scenarios/{sid}").status_code == 204
    assert alice.get(f"/api/scenarios/{sid}").status_code == 404
    assert alice.delete(f"/api/scenarios/{sid}").status_code == 404


def test_signed_out_user_loses_access_to_private_scenarios(people):
    alice, _, _ = people
    sid = alice.post("/api/scenarios", json=BUILD).json()["id"]
    alice.post("/api/auth/logout")
    assert alice.get(f"/api/scenarios/{sid}").status_code == 404


def test_cross_site_mutations_are_refused(people):
    alice, _, _ = people
    sid = alice.post("/api/scenarios", json=BUILD).json()["id"]
    evil = {"origin": "https://evil.example"}
    assert alice.delete(f"/api/scenarios/{sid}", headers=evil).status_code == 403
    assert alice.post("/api/scenarios", json=BUILD, headers=evil).status_code == 403
    assert alice.get(f"/api/scenarios/{sid}", headers=evil).status_code == 200  # reads are not mutations
    local = {"origin": "http://localhost:5173"}
    assert alice.delete(f"/api/scenarios/{sid}", headers=local).status_code == 204


def test_existing_database_gains_owner_column_and_keeps_old_scenarios(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE scenarios (id TEXT PRIMARY KEY, season INTEGER, created_at TEXT, "
                   "snapshot_id TEXT, salary_id TEXT, payload TEXT)")
        db.execute("INSERT INTO scenarios VALUES ('old', 2026, '2026-09-01T00:00:00', 's', 'p', "
                   "'{\"roster\": {\"total_salary\": 1, \"total_war\": 2}, \"cap_usd\": 3}')")
    client = TestClient(create_app(path))
    listed = client.get("/api/scenarios").json()
    assert [s["id"] for s in listed] == ["old"] and listed[0]["owned_by_me"] is False
    with sqlite3.connect(path) as db:
        assert "owner_id" in {row[1] for row in db.execute("PRAGMA table_info(scenarios)")}


# ---------- hardening found by the security review ----------

def test_only_configured_origins_get_credentialed_cors(app):
    alice = browser(app, "alice@example.com")
    good = alice.get("/api/auth/me", headers={"origin": "http://localhost:5173"})
    other_port = alice.get("/api/auth/me", headers={"origin": "http://localhost:6666"})
    assert good.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in other_port.headers  # the browser will not hand the body to that page
    assert alice.post("/api/auth/logout", headers={"origin": "http://localhost:6666"}).status_code == 403


def test_unsafe_request_without_origin_but_cross_site_fetch_metadata_is_refused(app):
    alice = browser(app, "alice@example.com")
    assert alice.post("/api/auth/logout", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert alice.post("/api/auth/logout", headers={"sec-fetch-site": "same-origin"}).status_code == 200


def test_changing_the_client_address_does_not_reset_the_per_email_limit(app):
    browser(app, "alice@example.com")
    statuses = []
    for i in range(25):
        client = TestClient(app, client=(f"10.0.0.{i}", 50000))  # what a spoofed X-Forwarded-For looks like
        statuses.append(client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrong password!"}).status_code)
    assert statuses[:20] == [401] * 20 and set(statuses[20:]) == {429}


def test_login_rotates_an_existing_session(app):
    alice = browser(app, "alice@example.com")
    old = alice.cookies.get(auth.SESSION_COOKIE)
    assert alice.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD}).status_code == 200
    assert TestClient(app, cookies={auth.SESSION_COOKIE: old}).get("/api/auth/me").json() is None
    assert alice.get("/api/auth/me").json()["email"] == "alice@example.com"


def test_rate_limiter_sweeps_idle_keys():
    now = [0.0]
    limiter = auth.RateLimiter(limit=2, window_seconds=10, clock=lambda: now[0])
    limiter.MAX_KEYS = 3
    for k in "abcd":
        limiter.retry_after(k)
    now[0] = 20.0
    limiter.retry_after("e")
    assert set(limiter.hits) == {"e"}

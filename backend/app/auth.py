"""Accounts and sessions: scrypt password hashes, opaque session tokens, a small login rate limiter.

Only a SHA-256 of each session token is stored, so a copy of the database cannot be replayed as a login.
Everything here is standard library; no auth dependency to keep patched.
"""

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import secrets
import sqlite3
from threading import BoundedSemaphore, Lock
from time import monotonic
from uuid import uuid4

SESSION_COOKIE = "roster_session"
SESSION_DAYS = 14
PASSWORD_MIN, PASSWORD_MAX = 10, 128
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
# scrypt cost: n=2**14, r=8 is the OWASP baseline for interactive logins (about 16 MiB, tens of ms).
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
# Each hash takes ~16 MiB and tens of ms; capping concurrent hashes bounds memory and CPU under a login flood.
_HASH_SLOTS = BoundedSemaphore(4)


class AuthError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass(frozen=True)
class User:
    id: str
    email: str


def ensure_tables(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                                          password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                                             created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
    """)


# ---------- passwords ----------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    with _HASH_SLOTS:
        digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        with _HASH_SLOTS:
            candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                                       dklen=len(digest) // 2)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate.hex(), digest)


# Verifying against this when the email is unknown keeps "no such user" as slow as "wrong password".
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def validate_credentials(email: str, password: str) -> str:
    email = email.strip()
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise AuthError(422, "invalid_email", "Enter a valid email address.")
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        raise AuthError(422, "weak_password", f"Use a password of {PASSWORD_MIN} to {PASSWORD_MAX} characters.")
    return email


# ---------- users and sessions ----------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def register(db: sqlite3.Connection, email: str, password: str) -> User:
    email = validate_credentials(email, password)
    user = User(str(uuid4()), email)
    try:
        db.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (user.id, email, hash_password(password), _now().isoformat()))
    except sqlite3.IntegrityError:
        raise AuthError(409, "email_taken", "An account with that email already exists.") from None
    return user


def authenticate(db: sqlite3.Connection, email: str, password: str) -> User:
    row = db.execute("SELECT id, email, password_hash FROM users WHERE email=?", (email.strip(),)).fetchone()
    ok = verify_password(password, row["password_hash"] if row else _DUMMY_HASH)
    if not row or not ok:
        raise AuthError(401, "invalid_login", "Email or password is incorrect.")
    return User(row["id"], row["email"])


def create_session(db: sqlite3.Connection, user: User) -> str:
    token = secrets.token_urlsafe(32)
    now = _now()
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (now.isoformat(),))  # opportunistic cleanup
    db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)",
               (_token_hash(token), user.id, now.isoformat(), (now + timedelta(days=SESSION_DAYS)).isoformat()))
    return token


def user_for_token(db: sqlite3.Connection, token: str | None) -> User | None:
    if not token:
        return None
    row = db.execute("""SELECT users.id, users.email, sessions.expires_at FROM sessions
                        JOIN users ON users.id = sessions.user_id WHERE sessions.token_hash=?""",
                     (_token_hash(token),)).fetchone()
    if row is None or datetime.fromisoformat(row["expires_at"]) <= _now():
        return None
    return User(row["id"], row["email"])


def delete_session(db: sqlite3.Connection, token: str | None) -> None:
    if token:
        db.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))


# ---------- rate limiting ----------

class RateLimiter:
    """Sliding-window counter per key, in process memory.

    Good enough for a single-process local app; a multi-worker deployment would need a shared store (Redis)."""

    MAX_KEYS = 10_000  # beyond this, keys with no recent attempts are swept so memory stays bounded

    def __init__(self, limit: int, window_seconds: float, clock=monotonic):
        self.limit, self.window, self.clock = limit, window_seconds, clock
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = Lock()

    def retry_after(self, key: str) -> int | None:
        """Record one attempt for `key`; return seconds to wait if it is over the limit, else None."""
        now = self.clock()
        with self.lock:
            if len(self.hits) > self.MAX_KEYS:
                cutoff = now - self.window
                for stale in [k for k, d in self.hits.items() if not d or d[-1] <= cutoff]:
                    del self.hits[stale]
            q = self.hits[key]
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                return max(1, int(q[0] + self.window - now) + 1)
            q.append(now)
            return None

    def reset(self, key: str) -> None:
        with self.lock:
            self.hits.pop(key, None)

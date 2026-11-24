"""Sign-in for the teacher app: accounts, passwords and sessions.

Rules that hold here:
- An account belongs to a named teacher, so every decision still carries a name.
- A password is never stored and never logged. Only a salted scrypt hash is kept.
- A session is a random cookie value. Only its hash is stored, so reading the database does not
  let anyone sign in.
- None of this is reachable over MCP. The agent has no account and cannot make one.
- While no account exists the app runs in demonstration mode (a teacher is picked from a list).
  The first account must be the school admin.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from . import audit, db

ROLES = ("admin", "teacher")
COOKIE = "athar_session"
SESSION_HOURS = 12
MIN_PASSWORD = 8
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}
_USERNAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,39}")
_MAX_TRIES, _WINDOW = 8, 600            # failed sign-ins allowed per username, per ten minutes
_failures: dict[str, list[float]] = {}


class NotAllowed(Exception):
    """The caller is signed in but may not do this."""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        found = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), dklen=len(digest) // 2,
                               n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(found.hex(), digest)


def _check_new(username: str, password: str, role: str) -> None:
    if not _USERNAME.fullmatch(username or ""):
        raise ValueError("A username is 3 to 40 letters, digits, dots, dashes or underscores.")
    if len(password or "") < MIN_PASSWORD:
        raise ValueError(f"A password needs at least {MIN_PASSWORD} characters.")
    if role not in ROLES:
        raise ValueError(f"A role is one of: {', '.join(ROLES)}.")


def enabled(db_path=None) -> bool:
    """True once the school has at least one account. Until then the app is in demonstration mode."""
    with db.connect(db_path) as conn:
        return db.one(conn, "SELECT 1 AS yes FROM accounts LIMIT 1") is not None


def create_account(teacher_id: str, username: str, password: str, role: str = "teacher",
                   actor: str = "system", db_path=None) -> dict[str, Any]:
    """Give a named teacher a way to sign in. Logged without the password."""
    started = time.perf_counter()
    _check_new(username, password, role)
    with db.connect(db_path) as conn:
        teacher = db.one(conn, "SELECT id, name FROM teachers WHERE id = ?", (teacher_id,))
        if teacher is None:
            raise ValueError(f"Unknown teacher '{teacher_id}'.")
        if db.one(conn, "SELECT 1 AS yes FROM accounts WHERE teacher_id = ?", (teacher_id,)):
            raise ValueError(f"{teacher['name']} already has an account.")
        if db.one(conn, "SELECT 1 AS yes FROM accounts WHERE username = ?", (username,)) or \
                db.one(conn, "SELECT 1 AS yes FROM parents WHERE username = ?", (username,)):
            raise ValueError(f"The username '{username}' is taken.")
        if role != "admin" and db.one(conn, "SELECT 1 AS yes FROM accounts LIMIT 1") is None:
            raise ValueError("The first account must be the school admin.")
        conn.execute("INSERT INTO accounts (teacher_id, username, password_hash, role, created_at) VALUES (?,?,?,?,?)",
                     (teacher_id, username.lower(), hash_password(password), role, db.now_iso()))
        out = {"teacher_id": teacher_id, "name": teacher["name"], "username": username.lower(), "role": role}
        audit.write_row(conn, "create_account", {"teacher_id": teacher_id, "username": username.lower(), "role": role},
                        out, True, int((time.perf_counter() - started) * 1000), actor=actor)
    return out


def create_teacher(name: str, subjects: list[str] | None, username: str, password: str, role: str = "teacher",
                   actor: str = "system", db_path=None) -> dict[str, Any]:
    """Add a named teacher together with their account."""
    name = " ".join(str(name or "").split())
    if not 2 <= len(name) <= 80:
        raise ValueError("Give the teacher's name (2 to 80 characters).")
    _check_new(username, password, role)
    with db.connect(db_path) as conn:
        if db.one(conn, "SELECT 1 AS yes FROM accounts WHERE username = ?", (username,)) or \
                db.one(conn, "SELECT 1 AS yes FROM parents WHERE username = ?", (username,)):
            raise ValueError(f"The username '{username}' is taken.")
        teacher_id = db.new_id("tch")
        conn.execute("INSERT INTO teachers (id, name, subjects) VALUES (?,?,?)",
                     (teacher_id, name, db.jdump([str(s)[:40] for s in (subjects or [])][:8])))
    try:
        return create_account(teacher_id, username, password, role, actor=actor, db_path=db_path)
    except Exception:
        with db.connect(db_path) as conn:      # no account was made, so do not leave a teacher nobody can use
            conn.execute("DELETE FROM teachers WHERE id = ?", (teacher_id,))
        raise


def set_password(teacher_id: str, password: str, actor: str, db_path=None) -> dict[str, Any]:
    """Replace a password and sign that teacher out everywhere."""
    started = time.perf_counter()
    if len(password or "") < MIN_PASSWORD:
        raise ValueError(f"A password needs at least {MIN_PASSWORD} characters.")
    with db.connect(db_path) as conn:
        if db.one(conn, "SELECT 1 AS yes FROM accounts WHERE teacher_id = ?", (teacher_id,)) is None:
            raise ValueError("That teacher has no account.")
        conn.execute("UPDATE accounts SET password_hash = ? WHERE teacher_id = ?", (hash_password(password), teacher_id))
        conn.execute("DELETE FROM sessions WHERE teacher_id = ?", (teacher_id,))
        audit.write_row(conn, "set_password", {"teacher_id": teacher_id}, {"changed": True}, True,
                        int((time.perf_counter() - started) * 1000), actor=actor)
    return {"changed": True}


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def sign_in(username: str, password: str, db_path=None) -> dict[str, Any]:
    """Check a username and password. Returns the session token to put in the cookie."""
    started = time.perf_counter()
    key = (username or "").strip().lower()
    now = time.time()
    recent = [t for t in _failures.get(key, []) if now - t < _WINDOW]
    if len(recent) >= _MAX_TRIES:
        raise ValueError("Too many wrong passwords. Wait ten minutes, or ask the school admin to reset it.")
    token, found = None, None
    with db.connect(db_path) as conn:
        row = db.one(conn, "SELECT a.teacher_id, a.username, a.password_hash, a.role, t.name FROM accounts a "
                           "JOIN teachers t ON t.id = a.teacher_id WHERE a.username = ?", (key,))
        # The same amount of work whether or not the username exists.
        ok = verify_password(password or "", row["password_hash"] if row else hash_password("no-such-account")) \
            and row is not None
        audit.write_row(conn, "sign_in", {"username": key[:40]}, {"signed_in": ok}, ok,
                        int((time.perf_counter() - started) * 1000),
                        actor=f"teacher:{row['teacher_id']}" if ok else "visitor")
        if ok:
            token = secrets.token_urlsafe(32)
            expires = datetime.now(UTC) + timedelta(hours=SESSION_HOURS)
            conn.execute("DELETE FROM sessions WHERE expires_at < ?", (db.now_iso(),))
            conn.execute("INSERT INTO sessions (token_hash, teacher_id, created_at, expires_at) VALUES (?,?,?,?)",
                         (_token_hash(token), row["teacher_id"], db.now_iso(), expires.isoformat(timespec="seconds")))
            found = {"id": row["teacher_id"], "name": row["name"], "username": row["username"], "role": row["role"]}
    if token is None:
        _failures[key] = recent + [now]
        raise ValueError("That username and password do not match.")
    _failures.pop(key, None)
    return {"token": token, "max_age": SESSION_HOURS * 3600, "teacher": found}


def session_teacher(token: str | None, db_path=None) -> dict[str, Any] | None:
    """The teacher a cookie belongs to, or None when it is missing, unknown or expired."""
    if not token:
        return None
    with db.connect(db_path) as conn:
        row = db.one(conn, "SELECT s.teacher_id, s.expires_at, a.username, a.role, t.name FROM sessions s "
                           "JOIN accounts a ON a.teacher_id = s.teacher_id JOIN teachers t ON t.id = s.teacher_id "
                           "WHERE s.token_hash = ?", (_token_hash(token),))
    if row is None or row["expires_at"] < db.now_iso():
        return None
    return {"id": row["teacher_id"], "name": row["name"], "username": row["username"], "role": row["role"]}


def sign_out(token: str | None, db_path=None) -> None:
    if token:
        with db.connect(db_path) as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def people(db_path=None) -> list[dict[str, Any]]:
    """Every teacher with their username and role. Never a password or a hash."""
    with db.connect(db_path) as conn:
        found = db.rows(conn, "SELECT t.id, t.name, t.subjects, a.username, a.role FROM teachers t "
                              "LEFT JOIN accounts a ON a.teacher_id = t.id ORDER BY t.name COLLATE NOCASE")
    for row in found:
        row["subjects"] = db.jload(row["subjects"], [])
    return found

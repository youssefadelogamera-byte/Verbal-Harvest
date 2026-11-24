"""Parent accounts, made by the school admin.

A parent signs in on their own page (`/parent`) with a username and password the school gave them. They see
the children the admin linked to them, and of those children only what a named teacher has approved: the
approved findings, the approved notes written for the family, and the printable report. Nothing else.

Parents are kept apart from teachers on purpose: their own table, their own sessions and their own cookie,
so a parent's session can never open a teacher page, and a teacher's can never be mistaken for a parent's.
"""

from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from . import audit, db
from .accounts import _USERNAME, MIN_PASSWORD, SESSION_HOURS, _token_hash, hash_password, verify_password

COOKIE = "athar_parent"
_MAX_TRIES, _WINDOW = 8, 600
_failures: dict[str, list[float]] = {}


def _check(name: str, username: str, password: str | None) -> str:
    name = " ".join(str(name or "").split())
    if not 2 <= len(name) <= 80:
        raise ValueError("Write the parent's name (2 to 80 characters).")
    if not _USERNAME.fullmatch(username or ""):
        raise ValueError("A username is 3 to 40 letters, digits, dots, dashes or underscores.")
    if password is not None and len(password) < MIN_PASSWORD:
        raise ValueError(f"A password needs at least {MIN_PASSWORD} characters.")
    return name


def _known_learners(conn, learner_ids: list[str]) -> list[str]:
    ids = list(dict.fromkeys(str(x) for x in learner_ids or []))
    for lid in ids:
        if db.one(conn, "SELECT id FROM learners WHERE id = ?", (lid,)) is None:
            raise ValueError(f"Unknown learner '{lid}'.")
    return ids


def create_parent(name: str, username: str, password: str, learner_ids: list[str], actor: str, db_path=None) -> dict:
    name = _check(name, username, password)
    key = username.lower()
    with db.connect(db_path) as conn:
        taken = db.one(conn, "SELECT 1 AS yes FROM parents WHERE username = ?", (key,)) or \
            db.one(conn, "SELECT 1 AS yes FROM accounts WHERE username = ?", (key,))
        if taken:
            raise ValueError(f"The username '{key}' is already used.")
        ids = _known_learners(conn, learner_ids)
        if not ids:
            raise ValueError("Choose at least one child for this parent.")
        pid = db.new_id("par")
        conn.execute("INSERT INTO parents (id, name, username, password_hash, created_at) VALUES (?,?,?,?,?)",
                     (pid, name, key, hash_password(password), db.now_iso()))
        conn.executemany("INSERT INTO parent_learners (parent_id, learner_id) VALUES (?, ?)", [(pid, lid) for lid in ids])
        audit.write_row(conn, "create_parent", {"username": key, "children": len(ids)}, {"parent_id": pid}, True, 0,
                        actor=actor)
    return {"id": pid, "name": name, "username": key, "children": ids}


def set_children(parent_id: str, learner_ids: list[str], actor: str, db_path=None) -> dict:
    with db.connect(db_path) as conn:
        _parent(conn, parent_id)
        ids = _known_learners(conn, learner_ids)
        if not ids:
            raise ValueError("Choose at least one child for this parent.")
        conn.execute("DELETE FROM parent_learners WHERE parent_id = ?", (parent_id,))
        conn.executemany("INSERT INTO parent_learners (parent_id, learner_id) VALUES (?, ?)", [(parent_id, lid) for lid in ids])
        audit.write_row(conn, "set_parent_children", {"parent_id": parent_id, "children": len(ids)}, {"ok": True}, True, 0,
                        actor=actor)
    return {"id": parent_id, "children": ids}


def set_password(parent_id: str, password: str, actor: str, db_path=None) -> dict:
    if len(password or "") < MIN_PASSWORD:
        raise ValueError(f"A password needs at least {MIN_PASSWORD} characters.")
    with db.connect(db_path) as conn:
        _parent(conn, parent_id)
        conn.execute("UPDATE parents SET password_hash = ? WHERE id = ?", (hash_password(password), parent_id))
        conn.execute("DELETE FROM parent_sessions WHERE parent_id = ?", (parent_id,))   # signed out everywhere
        audit.write_row(conn, "set_parent_password", {"parent_id": parent_id}, {"ok": True}, True, 0, actor=actor)
    return {"id": parent_id, "changed": True}


def remove_parent(parent_id: str, actor: str, db_path=None) -> dict:
    with db.connect(db_path) as conn:
        _parent(conn, parent_id)
        conn.execute("DELETE FROM parent_sessions WHERE parent_id = ?", (parent_id,))
        conn.execute("DELETE FROM parent_learners WHERE parent_id = ?", (parent_id,))
        conn.execute("DELETE FROM parents WHERE id = ?", (parent_id,))
        audit.write_row(conn, "remove_parent", {"parent_id": parent_id}, {"removed": True}, True, 0, actor=actor)
    return {"id": parent_id, "removed": True}


def _parent(conn, parent_id: str) -> dict:
    found = db.one(conn, "SELECT id, name, username FROM parents WHERE id = ?", (parent_id,))
    if found is None:
        raise ValueError(f"Unknown parent '{parent_id}'.")
    return found


def list_parents(db_path=None) -> list[dict]:
    """Every parent account with its children. Never a password or a hash."""
    with db.connect(db_path) as conn:
        found = db.rows(conn, "SELECT id, name, username, created_at FROM parents ORDER BY name COLLATE NOCASE")
        links = db.rows(conn, "SELECT p.parent_id, l.id, l.alias, l.display_name FROM parent_learners p "
                              "JOIN learners l ON l.id = p.learner_id ORDER BY l.display_name COLLATE NOCASE")
    for row in found:
        row["children"] = [{"learner_id": x["id"], "name": x["display_name"] or x["alias"], "code": x["alias"].replace("Learner ", "")}
                           for x in links if x["parent_id"] == row["id"]]
    return found


# ---------------------------------------------------------------- the parent's own side

def sign_in(username: str, password: str, db_path=None) -> dict:
    started = time.perf_counter()
    key = (username or "").strip().lower()
    now = time.time()
    recent = [t for t in _failures.get(key, []) if now - t < _WINDOW]
    if len(recent) >= _MAX_TRIES:
        raise ValueError("Too many wrong passwords. Wait ten minutes, or ask the school to reset it.")
    token = None
    with db.connect(db_path) as conn:
        row = db.one(conn, "SELECT id, name, password_hash FROM parents WHERE username = ?", (key,))
        ok = verify_password(password or "", row["password_hash"] if row else hash_password("no-such-parent")) \
            and row is not None
        audit.write_row(conn, "parent_sign_in", {"username": key[:40]}, {"signed_in": ok}, ok,
                        int((time.perf_counter() - started) * 1000), actor=f"parent:{row['id']}" if ok else "visitor")
        if ok:
            token = secrets.token_urlsafe(32)
            expires = datetime.now(UTC) + timedelta(hours=SESSION_HOURS)
            conn.execute("DELETE FROM parent_sessions WHERE expires_at < ?", (db.now_iso(),))
            conn.execute("INSERT INTO parent_sessions (token_hash, parent_id, created_at, expires_at) VALUES (?,?,?,?)",
                         (_token_hash(token), row["id"], db.now_iso(), expires.isoformat(timespec="seconds")))
    if token is None:
        _failures[key] = recent + [now]
        raise ValueError("That username and password do not match.")
    _failures.pop(key, None)
    return {"token": token, "max_age": SESSION_HOURS * 3600, "parent": {"id": row["id"], "name": row["name"]}}


def session_parent(token: str | None, db_path=None) -> dict | None:
    if not token:
        return None
    with db.connect(db_path) as conn:
        row = db.one(conn, "SELECT s.parent_id, s.expires_at, p.name FROM parent_sessions s JOIN parents p ON p.id = s.parent_id "
                           "WHERE s.token_hash = ?", (_token_hash(token),))
    if row is None or row["expires_at"] < db.now_iso():
        return None
    return {"id": row["parent_id"], "name": row["name"]}


def sign_out(token: str | None, db_path=None) -> None:
    if token:
        with db.connect(db_path) as conn:
            conn.execute("DELETE FROM parent_sessions WHERE token_hash = ?", (_token_hash(token),))


def children_of(parent_id: str, db_path=None) -> set[str]:
    with db.connect(db_path) as conn:
        return {r["learner_id"] for r in db.rows(conn, "SELECT learner_id FROM parent_learners WHERE parent_id = ?", (parent_id,))}


def overview(parent_id: str, db_path=None) -> dict[str, Any]:
    """What a parent sees: each linked child, with approved findings and approved family notes only."""
    with db.connect(db_path) as conn:
        kids = db.rows(conn, "SELECT l.id, l.alias, l.display_name, l.start_grade, l.start_year FROM parent_learners p "
                             "JOIN learners l ON l.id = p.learner_id WHERE p.parent_id = ? ORDER BY l.display_name", (parent_id,))
        out = []
        for k in kids:
            grade = db.one(conn, "SELECT MAX(grade) AS g FROM evidence WHERE learner_id = ? AND status != 'retracted'", (k["id"],))["g"]
            findings = db.rows(conn, "SELECT f.kind, f.statement, f.decided_at, t.name AS teacher FROM findings f "
                                     "LEFT JOIN teachers t ON t.id = f.decided_by WHERE f.learner_id = ? "
                                     "AND f.status IN ('approved','edited') ORDER BY f.decided_at DESC", (k["id"],))
            notes = db.rows(conn, "SELECT s.language, s.text, s.decided_at, t.name AS teacher FROM summaries s "
                                  "LEFT JOIN teachers t ON t.id = s.decided_by WHERE s.learner_id = ? "
                                  "AND s.audience = 'guardian' AND s.status = 'approved' ORDER BY s.decided_at DESC", (k["id"],))
            out.append({"learner_id": k["id"], "name": k["display_name"] or k["alias"], "grade": grade or k["start_grade"],
                        "findings": findings, "notes": notes})
    return {"children": out}

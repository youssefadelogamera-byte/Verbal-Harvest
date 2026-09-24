import { DatabaseSync } from 'node:sqlite';
import fs from 'node:fs';
import path from 'node:path';

const dbPath = process.env.DATABASE_PATH || './data/verbal-harvest.db';
if (dbPath !== ':memory:') fs.mkdirSync(path.dirname(dbPath), { recursive: true });

export const db = new DatabaseSync(dbPath);

db.exec(`
  PRAGMA journal_mode = WAL;
  PRAGMA foreign_keys = ON;

  CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    audience      TEXT NOT NULL CHECK (audience IN ('children','teens','adults','business')),
    guardian_email TEXT,
    native_language TEXT,
    goal          TEXT,
    placement_level TEXT,
    current_level TEXT,
    xp            INTEGER NOT NULL DEFAULT 0,
    streak        INTEGER NOT NULL DEFAULT 0,
    last_active   TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS placement_tests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    state       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'in_progress',
    result      TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
  );

  CREATE TABLE IF NOT EXISTS unit_progress (
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    unit_id   TEXT NOT NULL,
    status    TEXT NOT NULL DEFAULT 'completed',
    score     INTEGER,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, unit_id)
  );

  CREATE TABLE IF NOT EXISTS activity (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,
    skill      TEXT,
    score      INTEGER,
    detail     TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );
`);

export function publicUser(u) {
  if (!u) return null;
  return {
    id: u.id,
    email: u.email,
    name: u.name,
    audience: u.audience,
    nativeLanguage: u.native_language,
    goal: u.goal,
    placementLevel: u.placement_level,
    currentLevel: u.current_level,
    xp: u.xp,
    streak: u.streak,
    createdAt: u.created_at,
  };
}

// Record an activity, award XP and maintain the daily streak.
export function recordActivity(userId, { kind, skill = null, score = null, detail = null, xp = 0 }) {
  db.prepare('INSERT INTO activity (user_id, kind, skill, score, detail) VALUES (?, ?, ?, ?, ?)')
    .run(userId, kind, skill, score, detail ? JSON.stringify(detail) : null);

  const user = db.prepare('SELECT last_active, streak FROM users WHERE id = ?').get(userId);
  const today = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  let streak = user.streak;
  if (user.last_active !== today) streak = user.last_active === yesterday ? streak + 1 : 1;
  db.prepare('UPDATE users SET xp = xp + ?, streak = ?, last_active = ? WHERE id = ?').run(xp, streak, today, userId);
}

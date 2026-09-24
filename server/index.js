import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import express from 'express';

try { process.loadEnvFile?.(); } catch { /* no .env file */ }

const { db, publicUser, recordActivity } = await import('./db.js');
const { hashPassword, verifyPassword, createSession, destroySession, loadUser, requireAuth, rateLimit } = await import('./auth.js');
const { LEVELS, LEVEL_INFO, AUDIENCES, SPEAKING_CRITERIA, levelIndex } = await import('./data/cefr.js');
const { unitsFor, UNIT_BY_ID, FREE_TOPICS, trackFor } = await import('./data/curriculum.js');
const placement = await import('./placement.js');
const ai = await import('./ai.js');

const here = path.dirname(fileURLToPath(import.meta.url));
export const app = express();
app.set('trust proxy', 1);
app.use(express.json({ limit: '100kb' }));
app.use(loadUser);

// JSON-only API: blocks cross-site form posts (CSRF) on top of SameSite cookies.
app.use('/api', (req, res, next) => {
  if (['POST', 'PATCH', 'PUT', 'DELETE'].includes(req.method) && !req.is('application/json')) {
    return res.status(415).json({ error: 'Expected application/json.' });
  }
  next();
});

const wrap = (fn) => (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next);
const bad = (res, error, status = 400) => res.status(status).json({ error });
const str = (v, max = 200) => (typeof v === 'string' ? v.trim().slice(0, max) : '');

function requireLevel(req, res, next) {
  if (!req.user.current_level) return res.status(409).json({ error: 'Complete your placement test and choose a level first.', needsPlacement: true });
  next();
}

// ───────────────────────────── Meta ─────────────────────────────
app.get('/api/meta', (_req, res) => {
  res.json({ levels: LEVELS, levelInfo: LEVEL_INFO, audiences: AUDIENCES, speakingCriteria: SPEAKING_CRITERIA, aiEnabled: ai.aiEnabled() });
});

// ───────────────────────────── Auth ─────────────────────────────
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

app.post('/api/auth/register', rateLimit(10, 15 * 60e3), (req, res) => {
  const name = str(req.body.name, 80);
  const email = str(req.body.email, 160).toLowerCase();
  const password = typeof req.body.password === 'string' ? req.body.password : '';
  const audience = str(req.body.audience, 20);
  const guardianEmail = str(req.body.guardianEmail, 160).toLowerCase();

  if (!name) return bad(res, 'Please enter your name.');
  if (!EMAIL.test(email)) return bad(res, 'Please enter a valid email address.');
  if (password.length < 8 || !/[A-Za-z]/.test(password) || !/\d/.test(password)) {
    return bad(res, 'Password must be at least 8 characters and include a letter and a number.');
  }
  if (!AUDIENCES[audience]) return bad(res, 'Please choose a learner profile.');
  if (audience === 'children') {
    if (!EMAIL.test(guardianEmail)) return bad(res, 'A parent or guardian email is required for children\'s accounts.');
    if (req.body.guardianConsent !== true) return bad(res, 'A parent or guardian must confirm consent for a child\'s account.');
  }
  if (db.prepare('SELECT 1 FROM users WHERE email = ?').get(email)) return bad(res, 'An account with this email already exists.', 409);

  const { lastInsertRowid } = db.prepare(`
    INSERT INTO users (email, name, password_hash, audience, guardian_email, native_language, goal)
    VALUES (?, ?, ?, ?, ?, ?, ?)`).run(
    email, name, hashPassword(password), audience, guardianEmail || null,
    str(req.body.nativeLanguage, 60) || null, str(req.body.goal, 200) || null,
  );
  createSession(res, Number(lastInsertRowid));
  res.status(201).json({ user: publicUser(db.prepare('SELECT * FROM users WHERE id = ?').get(lastInsertRowid)) });
});

app.post('/api/auth/login', rateLimit(20, 15 * 60e3), (req, res) => {
  const email = str(req.body.email, 160).toLowerCase();
  const password = typeof req.body.password === 'string' ? req.body.password : '';
  const user = db.prepare('SELECT * FROM users WHERE email = ?').get(email);
  if (!user || !verifyPassword(password, user.password_hash)) return bad(res, 'Incorrect email or password.', 401);
  createSession(res, user.id);
  res.json({ user: publicUser(user) });
});

app.post('/api/auth/logout', (req, res) => {
  destroySession(req, res);
  res.json({ ok: true });
});

app.get('/api/auth/me', (req, res) => res.json({ user: publicUser(req.user) }));

app.patch('/api/profile', requireAuth, (req, res) => {
  const name = str(req.body.name, 80) || req.user.name;
  db.prepare('UPDATE users SET name = ?, native_language = ?, goal = ? WHERE id = ?')
    .run(name, str(req.body.nativeLanguage, 60) || null, str(req.body.goal, 200) || null, req.user.id);
  res.json({ user: publicUser(db.prepare('SELECT * FROM users WHERE id = ?').get(req.user.id)) });
});

app.delete('/api/account', requireAuth, (req, res) => {
  const password = typeof req.body.password === 'string' ? req.body.password : '';
  if (!verifyPassword(password, req.user.password_hash)) return bad(res, 'Password is incorrect.', 401);
  db.prepare('DELETE FROM users WHERE id = ?').run(req.user.id);
  destroySession(req, res);
  res.json({ ok: true });
});

// ─────────────────────────── Placement ───────────────────────────
const activeTest = (userId) =>
  db.prepare("SELECT * FROM placement_tests WHERE user_id = ? AND status = 'in_progress' ORDER BY id DESC LIMIT 1").get(userId);
const saveState = (id, state) => db.prepare('UPDATE placement_tests SET state = ? WHERE id = ?').run(JSON.stringify(state), id);

function placementView(test) {
  const state = JSON.parse(test.state);
  return {
    testId: test.id,
    phase: state.phase,
    item: placement.clientItem(placement.currentItem(state), state),
    task: state.phase === 'productive' ? placement.productiveTask(state) : null,
  };
}

app.post('/api/placement/start', requireAuth, (req, res) => {
  const existing = activeTest(req.user.id);
  if (existing && !req.body.restart) return res.json(placementView(existing));
  db.prepare("UPDATE placement_tests SET status = 'abandoned' WHERE user_id = ? AND status = 'in_progress'").run(req.user.id);
  const state = placement.newPlacementState(req.user.audience);
  const { lastInsertRowid } = db.prepare('INSERT INTO placement_tests (user_id, state) VALUES (?, ?)').run(req.user.id, JSON.stringify(state));
  res.json(placementView(db.prepare('SELECT * FROM placement_tests WHERE id = ?').get(lastInsertRowid)));
});

app.post('/api/placement/answer', requireAuth, (req, res) => {
  const test = activeTest(req.user.id);
  if (!test) return bad(res, 'No placement test in progress.', 404);
  const state = JSON.parse(test.state);
  try {
    placement.answerItem(state, str(req.body.itemId, 20), req.body.choice);
  } catch (e) {
    return bad(res, e.message, 409);
  }
  saveState(test.id, state);
  res.json(placementView({ ...test, state: JSON.stringify(state) }));
});

app.post('/api/placement/productive', requireAuth, wrap(async (req, res) => {
  const test = activeTest(req.user.id);
  if (!test) return bad(res, 'No placement test in progress.', 404);
  const state = JSON.parse(test.state);
  if (state.phase !== 'productive') return bad(res, 'Finish the listening and reading section first.', 409);

  const transcript = str(req.body.transcript, 4000);
  let productive = null;
  if (!req.body.skip) {
    if (transcript.split(/\s+/).filter(Boolean).length < 3) return bad(res, 'Please say or write a little more (or choose to skip).');
    productive = await ai.assessSpeaking({
      task: placement.productiveTask(state), transcript, audience: req.user.audience, targetLevel: state.receptiveLevel,
    });
  }
  state.phase = 'done';
  const result = placement.buildResult(state, productive);
  db.prepare("UPDATE placement_tests SET state = ?, status = 'completed', result = ?, completed_at = datetime('now') WHERE id = ?")
    .run(JSON.stringify(state), JSON.stringify(result), test.id);
  db.prepare('UPDATE users SET placement_level = ? WHERE id = ?').run(result.recommendedLevel, req.user.id);
  recordActivity(req.user.id, { kind: 'placement', score: levelIndex(result.recommendedLevel), detail: { level: result.recommendedLevel }, xp: 50 });
  res.json({ result });
}));

app.get('/api/placement/result', requireAuth, (req, res) => {
  const row = db.prepare("SELECT * FROM placement_tests WHERE user_id = ? AND status = 'completed' ORDER BY id DESC LIMIT 1").get(req.user.id);
  if (!row) return bad(res, 'You have not completed a placement test yet.', 404);
  res.json({ result: JSON.parse(row.result), completedAt: row.completed_at });
});

// Choosing a level is only possible once the placement test is complete.
app.post('/api/level', requireAuth, (req, res) => {
  if (!req.user.placement_level) return res.status(409).json({ error: 'Please take the placement test before choosing a level.', needsPlacement: true });
  const level = str(req.body.level, 10);
  if (!AUDIENCES[req.user.audience].levels.includes(level)) return bad(res, 'That level is not available for your learner profile.');
  db.prepare('UPDATE users SET current_level = ? WHERE id = ?').run(level, req.user.id);
  res.json({ user: publicUser(db.prepare('SELECT * FROM users WHERE id = ?').get(req.user.id)) });
});

// ─────────────────────────── Learning ───────────────────────────
function unitsWithProgress(user, level) {
  const done = new Map(db.prepare('SELECT unit_id, score FROM unit_progress WHERE user_id = ?').all(user.id).map((r) => [r.unit_id, r.score]));
  return unitsFor(user.audience, level).map((x) => ({ ...x, completed: done.has(x.id), score: done.get(x.id) ?? null }));
}

app.get('/api/dashboard', requireAuth, requireLevel, (req, res) => {
  const user = req.user;
  const levels = AUDIENCES[user.audience].levels;
  const path = levels.map((level) => {
    const units = unitsWithProgress(user, level);
    return { level, total: units.length, completed: units.filter((x) => x.completed).length };
  });
  const skillRows = db.prepare(`
    SELECT skill, ROUND(AVG(score)) AS avg, COUNT(*) AS n FROM activity
    WHERE user_id = ? AND skill IS NOT NULL AND score IS NOT NULL GROUP BY skill`).all(user.id);
  const recent = db.prepare('SELECT kind, skill, score, detail, created_at FROM activity WHERE user_id = ? ORDER BY id DESC LIMIT 8').all(user.id)
    .map((r) => ({ ...r, detail: r.detail ? JSON.parse(r.detail) : null }));
  res.json({
    user: publicUser(user),
    units: unitsWithProgress(user, user.current_level),
    path,
    skills: Object.fromEntries(skillRows.map((r) => [r.skill, { average: r.avg, sessions: r.n }])),
    recent,
    topics: FREE_TOPICS[user.audience],
  });
});

app.get('/api/units', requireAuth, requireLevel, (req, res) => {
  const level = LEVELS.includes(req.query.level) ? req.query.level : req.user.current_level;
  res.json({ level, units: unitsWithProgress(req.user, level) });
});

function findUnit(user, id) {
  const unit = UNIT_BY_ID[id];
  if (!unit) return null;
  // Units must belong to the learner's track (or be a general fallback).
  if (unit.track !== trackFor(user.audience) && unit.track !== 'general') return null;
  return unitsFor(user.audience, unit.level).find((x) => x.id === id) || unit;
}

app.get('/api/units/:id', requireAuth, requireLevel, (req, res) => {
  const unit = findUnit(req.user, req.params.id);
  if (!unit) return bad(res, 'Unit not found.', 404);
  const row = db.prepare('SELECT score FROM unit_progress WHERE user_id = ? AND unit_id = ?').get(req.user.id, unit.id);
  res.json({ unit: { ...unit, completed: Boolean(row), score: row?.score ?? null } });
});

app.post('/api/units/:id/complete', requireAuth, requireLevel, (req, res) => {
  const unit = findUnit(req.user, req.params.id);
  if (!unit) return bad(res, 'Unit not found.', 404);
  const score = Math.max(0, Math.min(100, Math.round(Number(req.body.score) || 0)));
  db.prepare(`INSERT INTO unit_progress (user_id, unit_id, score) VALUES (?, ?, ?)
    ON CONFLICT(user_id, unit_id) DO UPDATE SET score = MAX(score, excluded.score), updated_at = datetime('now')`)
    .run(req.user.id, unit.id, score);
  recordActivity(req.user.id, { kind: 'unit', skill: 'speaking', score, detail: { unit: unit.title }, xp: 40 });
  res.json({ ok: true });
});

// ─────────────────────────── AI Coach ───────────────────────────
function cleanMessages(list) {
  if (!Array.isArray(list)) return [];
  return list.slice(-30)
    .filter((m) => m && (m.role === 'user' || m.role === 'coach') && typeof m.text === 'string')
    .map((m) => ({ role: m.role, text: m.text.slice(0, 2000) }));
}

app.post('/api/coach/chat', requireAuth, requireLevel, rateLimit(120, 10 * 60e3), wrap(async (req, res) => {
  const messages = cleanMessages(req.body.messages);
  let scenario = null;
  let unit = null;
  if (req.body.unitId) {
    unit = findUnit(req.user, str(req.body.unitId, 40));
    if (!unit) return bad(res, 'Unit not found.', 404);
    scenario = { aiRole: unit.scenario[0], setting: unit.scenario[1], goal: unit.scenario[2] };
  }
  const level = unit?.level || req.user.current_level;
  const out = await ai.coachReply({
    audience: req.user.audience, level, scenario, topic: str(req.body.topic, 120), messages, name: req.user.name.split(' ')[0],
  });
  if (messages.some((m) => m.role === 'user')) {
    const errors = out.corrections.length;
    recordActivity(req.user.id, { kind: 'conversation', skill: 'interaction', score: Math.max(40, 100 - errors * 15), xp: 5 });
  }
  res.json(out);
}));

app.post('/api/speaking/assess', requireAuth, requireLevel, rateLimit(40, 10 * 60e3), wrap(async (req, res) => {
  const transcript = str(req.body.transcript, 4000);
  const task = str(req.body.task, 400);
  if (!task) return bad(res, 'Missing task.');
  if (transcript.split(/\s+/).filter(Boolean).length < 3) return bad(res, 'Please say a little more so we can assess it.');
  const result = await ai.assessSpeaking({ task, transcript, audience: req.user.audience, targetLevel: req.user.current_level });
  const avg = Math.round(Object.values(result.scores).reduce((a, b) => a + b, 0) / 5);
  recordActivity(req.user.id, { kind: 'speaking', skill: 'production', score: avg, detail: { level: result.level }, xp: 20 });
  res.json({ result });
}));

app.post('/api/pronunciation/log', requireAuth, requireLevel, (req, res) => {
  const score = Math.max(0, Math.min(100, Math.round(Number(req.body.score) || 0)));
  recordActivity(req.user.id, { kind: 'pronunciation', skill: 'pronunciation', score, xp: 5 });
  res.json({ ok: true });
});

// ─────────────────────────── Errors & SPA ───────────────────────────
app.use('/api', (_req, res) => bad(res, 'Not found.', 404));

// eslint-disable-next-line no-unused-vars
app.use((err, _req, res, _next) => {
  if (err instanceof ai.RefusalError) return bad(res, err.message, 422);
  console.error(err);
  res.status(500).json({ error: 'Something went wrong. Please try again.' });
});

const dist = path.join(here, '..', 'client', 'dist');
if (fs.existsSync(dist)) {
  app.use(express.static(dist, { index: false, maxAge: '1h' }));
  app.get(/^(?!\/api).*/, (_req, res) => res.sendFile(path.join(dist, 'index.html')));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.PORT) || 8787;
  app.listen(port, () => {
    console.log(`Verbal Harvest API on http://localhost:${port}  (AI coach: ${ai.aiEnabled() ? 'Claude' : 'practice mode — set ANTHROPIC_API_KEY'})`);
  });
}

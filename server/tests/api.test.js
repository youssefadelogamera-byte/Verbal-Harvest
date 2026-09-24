import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';

process.env.DATABASE_PATH = ':memory:';
delete process.env.ANTHROPIC_API_KEY;
delete process.env.ANTHROPIC_AUTH_TOKEN;
const { app } = await import('../index.js');
const { ITEM_BY_ID } = await import('../data/placementBank.js');

let server, base;
before(async () => {
  server = app.listen(0);
  await new Promise((r) => server.once('listening', r));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(() => server.close());

function client() {
  let cookie = '';
  return async (method, path, body) => {
    const res = await fetch(base + path, {
      method,
      headers: { 'content-type': 'application/json', cookie },
      body: body ? JSON.stringify(body) : undefined,
    });
    const set = res.headers.get('set-cookie');
    if (set) cookie = set.split(';')[0];
    return { status: res.status, body: await res.json() };
  };
}

test('full learner journey: register → placement → choose level → learn', async () => {
  const api = client();
  let r = await api('POST', '/api/auth/register', { name: 'Ada', email: 'ada@example.com', password: 'weak', audience: 'adults' });
  assert.equal(r.status, 400);

  r = await api('POST', '/api/auth/register', { name: 'Ada Lovelace', email: 'ada@example.com', password: 'harvest123', audience: 'adults' });
  assert.equal(r.status, 201);
  assert.equal(r.body.user.currentLevel, null);

  // Level selection and learning are locked until placement is done.
  assert.equal((await api('POST', '/api/level', { level: 'B1' })).status, 409);
  assert.equal((await api('GET', '/api/dashboard')).status, 409);

  r = await api('POST', '/api/placement/start', {});
  assert.equal(r.body.phase, 'receptive');
  assert.equal(r.body.item.answer, undefined, 'answer key must not leak');
  while (r.body.phase === 'receptive') {
    const item = ITEM_BY_ID[r.body.item.id];
    r = await api('POST', '/api/placement/answer', { itemId: item.id, choice: item.answer });
  }
  assert.equal(r.body.phase, 'productive');
  assert.ok(r.body.task);

  r = await api('POST', '/api/placement/productive', {
    transcript: 'Although banning cars from city centres would reduce pollution and make streets safer, it could also harm small businesses. However, with better public transport, I believe the advantages would outweigh the disadvantages in the long term.',
  });
  assert.equal(r.status, 200);
  assert.ok(r.body.result.recommendedLevel);
  assert.equal(r.body.result.receptiveLevel, 'C2');

  r = await api('POST', '/api/level', { level: 'Pre-A1' });
  assert.equal(r.status, 400, 'Pre-A1 is outside the adult range');
  r = await api('POST', '/api/level', { level: 'B2' });
  assert.equal(r.body.user.currentLevel, 'B2');

  r = await api('GET', '/api/dashboard');
  assert.equal(r.status, 200);
  assert.ok(r.body.units.length > 0);
  const unit = r.body.units[0];

  r = await api('POST', '/api/coach/chat', { unitId: unit.id, messages: [] });
  assert.ok(r.body.reply);
  r = await api('POST', '/api/coach/chat', { unitId: unit.id, messages: [{ role: 'coach', text: r.body.reply }, { role: 'user', text: 'I am agree, he go to work by car.' }] });
  assert.ok(r.body.corrections.length >= 1);

  r = await api('POST', `/api/units/${unit.id}/complete`, { score: 85 });
  assert.equal(r.status, 200);
  r = await api('GET', '/api/dashboard');
  assert.equal(r.body.units.find((u) => u.id === unit.id).completed, true);
  assert.ok(r.body.user.xp > 0);

  assert.equal((await api('POST', '/api/auth/logout', {})).status, 200);
  assert.equal((await api('GET', '/api/dashboard')).status, 401);
  r = await api('POST', '/api/auth/login', { email: 'ADA@example.com', password: 'harvest123' });
  assert.equal(r.status, 200);
});

test('children need guardian consent', async () => {
  const api = client();
  let r = await api('POST', '/api/auth/register', { name: 'Kid', email: 'kid@example.com', password: 'harvest123', audience: 'children' });
  assert.equal(r.status, 400);
  r = await api('POST', '/api/auth/register', { name: 'Kid', email: 'kid@example.com', password: 'harvest123', audience: 'children', guardianEmail: 'parent@example.com', guardianConsent: true });
  assert.equal(r.status, 201);
});

test('rejects non-JSON writes', async () => {
  const res = await fetch(base + '/api/auth/login', { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: 'email=a' });
  assert.equal(res.status, 415);
});

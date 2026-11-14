const test = require('node:test');
const assert = require('node:assert');
const Solver = require('../solver.js');
const { sampleSchool } = require('../sample-data.js');

test('example school is scheduled completely with no clashes', () => {
  const data = sampleSchool();
  assert.deepStrictEqual(Solver.diagnose(data), []);
  for (const seed of [1, 2, 3]) {
    const r = Solver.solve(data, { seed });
    assert.strictEqual(r.unplaced.length, 0);
    const v = Solver.validate(data, r.placements);
    assert.deepStrictEqual(v.conflicts, []);
    assert.deepStrictEqual(v.missing, []);
    assert.deepStrictEqual(v.warnings, []);
  }
});

test('teacher unavailability, daily limits and special rooms are respected', () => {
  const data = sampleSchool();
  const r = Solver.solve(data, { seed: 7 });
  const lessons = new Map(data.lessons.map((l) => [l.id, l]));
  const subjects = new Map(data.subjects.map((s) => [s.id, s]));
  const rooms = new Map(data.rooms.map((x) => [x.id, x]));
  const perDay = {};
  for (const pl of r.placements) {
    const l = lessons.get(pl.lessonId);
    if (l.teacherId === 't15') assert.notStrictEqual(pl.day, 'Thursday');
    const key = l.teacherId + pl.day;
    perDay[key] = (perDay[key] || 0) + pl.length;
    const needs = subjects.get(l.subjectId).roomType;
    if (needs) assert.strictEqual(rooms.get(pl.roomId).type, needs);
    if (pl.length === 2) assert.ok(pl.period + 1 < data.settings.periods.length);
  }
  for (const n of Object.values(perDay)) assert.ok(n <= 6);
});

test('validate detects a double-booked teacher', () => {
  const data = sampleSchool();
  const r = Solver.solve(data, { seed: 3 });
  const a = r.placements.find((p) => p.lessonId === 'l-c7A-s-math' && p.length === 1);
  const b = r.placements.find((p) => p.lessonId === 'l-c7B-s-math' && p.length === 1);
  b.day = a.day;
  b.period = a.period;
  const v = Solver.validate(data, r.placements);
  assert.ok(v.conflicts.some((c) => c.includes('Ahmed Hassan is double-booked')));
});

test('diagnose reports impossible workloads', () => {
  const data = sampleSchool();
  data.lessons.push({ id: 'x', classId: 'c7A', subjectId: 's-math', teacherId: 't1', perWeek: 15, doubles: 0 });
  const w = Solver.diagnose(data);
  assert.ok(w.some((m) => m.includes('Class 7A needs 48 periods')));
  assert.ok(w.some((m) => m.includes('Ahmed Hassan is given 33 periods')));
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { newPlacementState, currentItem, answerItem, buildResult } from '../placement.js';
import { ITEMS } from '../data/placementBank.js';
import { AUDIENCES, LEVELS } from '../data/cefr.js';

// Simulate a learner who answers correctly at or below `trueLevel`.
function run(audience, trueLevel) {
  const state = newPlacementState(audience);
  let guard = 0;
  while (state.phase === 'receptive' && guard++ < 60) {
    const item = currentItem(state);
    const knows = LEVELS.indexOf(item.level) <= LEVELS.indexOf(trueLevel);
    answerItem(state, item.id, knows ? item.answer : (item.answer + 1) % item.options.length);
  }
  return state;
}

test('item bank is well-formed', () => {
  const ids = new Set();
  for (const i of ITEMS) {
    assert.ok(!ids.has(i.id), `duplicate id ${i.id}`);
    ids.add(i.id);
    assert.ok(LEVELS.includes(i.level), i.id);
    assert.ok(i.answer >= 0 && i.answer < i.options.length, i.id);
  }
});

for (const [audience, cfg] of Object.entries(AUDIENCES)) {
  for (const level of cfg.levels) {
    test(`${audience}: learner at ${level} is placed at ${level}`, () => {
      const state = run(audience, level);
      assert.equal(state.phase, 'productive');
      assert.equal(state.receptiveLevel, level);
    });
  }
}

test('below-range learner is placed at the lowest band', () => {
  const state = run('adults', 'Pre-A1');
  assert.equal(state.receptiveLevel, 'A1');
});

test('productive estimate blends into the recommendation', () => {
  const state = run('adults', 'B2');
  assert.equal(buildResult(state, null).recommendedLevel, 'B2');
  assert.equal(buildResult(state, { level: 'A2' }).recommendedLevel, 'B1');
  assert.equal(buildResult(state, { level: 'C2' }).recommendedLevel, 'C1');
});

test('rejects answers to a stale question', () => {
  const state = newPlacementState('teens');
  assert.throws(() => answerItem(state, 'not-an-item', 0));
});

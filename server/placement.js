// Adaptive CEFR placement engine.
//
// The test works in "blocks" of items at a single CEFR level:
//   • 4 items per block. 3+ correct = level passed, ≤1 correct = level failed.
//   • 2/4 is ambiguous, so two tie-break items are added: 4+/6 passes.
// We start at the audience's typical entry level and move up after a pass or
// down after a fail. As soon as we find a passed level directly beneath a
// failed level (or hit the edge of the audience's range), the receptive
// level is known. A short speaking/writing task then gives a productive
// estimate, and the two are combined into the final recommendation.

import { ITEMS, ITEM_BY_ID, PRODUCTIVE_TASKS } from './data/placementBank.js';
import { AUDIENCES, LEVELS, levelIndex, clampToAudience } from './data/cefr.js';

const BLOCK = 4;
const TIE_BREAK = 2;

function poolFor(audience, level, used) {
  const unused = (i) => i.level === level && !used.includes(i.id);
  if (audience === 'children') return ITEMS.filter((i) => i.pool === 'kids' && unused(i));
  const general = ITEMS.filter((i) => i.pool === 'general' && unused(i));
  if (audience !== 'business') return general;
  // Business learners see workplace items first, then general ones.
  return [...ITEMS.filter((i) => i.pool === 'business' && unused(i)), ...general];
}

// Pick items spreading across skills so each block samples different abilities.
function pickItems(audience, level, used, n) {
  const pool = poolFor(audience, level, used);
  const chosen = [];
  const skillsSeen = new Set();
  for (const item of pool) {
    if (chosen.length >= n) break;
    if (!skillsSeen.has(item.skill)) { chosen.push(item); skillsSeen.add(item.skill); }
  }
  for (const item of pool) {
    if (chosen.length >= n) break;
    if (!chosen.includes(item)) chosen.push(item);
  }
  return chosen.map((i) => i.id);
}

export function newPlacementState(audience) {
  const start = AUDIENCES[audience].startLevel;
  const state = {
    audience,
    phase: 'receptive',
    level: start,
    blocks: {}, // level -> { items: [], answers: [] }
    passed: [],
    failed: [],
    used: [],
    skills: {},
    receptiveLevel: null,
  };
  openBlock(state, start);
  return state;
}

function openBlock(state, level) {
  const items = pickItems(state.audience, level, state.used, BLOCK);
  state.level = level;
  state.blocks[level] = { items, answers: [] };
  state.used.push(...items);
}

export function currentItem(state) {
  if (state.phase !== 'receptive') return null;
  const block = state.blocks[state.level];
  const id = block.items[block.answers.length];
  return id ? ITEM_BY_ID[id] : null;
}

// Strip the answer before sending an item to the browser.
export function clientItem(item, state) {
  if (!item) return null;
  const answered = Object.values(state.blocks).reduce((n, b) => n + b.answers.length, 0);
  return {
    id: item.id,
    skill: item.skill,
    prompt: item.prompt,
    options: item.options,
    audio: item.audio || null,
    number: answered + 1,
    // Upper bound so the progress bar is honest: at most ~5 blocks with tie-breaks.
    estimatedTotal: Math.max(answered + 1, 16),
  };
}

function finishReceptive(state, level) {
  state.receptiveLevel = level;
  state.phase = 'productive';
}

export function answerItem(state, itemId, choice) {
  const item = currentItem(state);
  if (!item || item.id !== itemId) throw new Error('This question is no longer active.');
  const correct = Number(choice) === item.answer;
  const block = state.blocks[state.level];
  block.answers.push(correct);

  const s = (state.skills[item.skill] ||= { correct: 0, total: 0 });
  s.total += 1;
  if (correct) s.correct += 1;

  const done = block.answers.length;
  if (done < block.items.length) return { correct };

  const right = block.answers.filter(Boolean).length;
  let verdict = null;
  if (block.items.length === BLOCK) {
    if (right >= 3) verdict = 'pass';
    else if (right <= 1) verdict = 'fail';
    else {
      const extra = pickItems(state.audience, state.level, state.used, TIE_BREAK);
      if (extra.length) {
        block.items.push(...extra);
        state.used.push(...extra);
        return { correct };
      }
      verdict = 'fail';
    }
  } else {
    verdict = right >= Math.ceil(block.items.length * 2 / 3) ? 'pass' : 'fail';
  }

  const range = AUDIENCES[state.audience].levels;
  const idx = range.indexOf(state.level);
  if (verdict === 'pass') {
    state.passed.push(state.level);
    const next = range[idx + 1];
    if (!next || state.failed.includes(next)) finishReceptive(state, state.level);
    else openBlock(state, next);
  } else {
    state.failed.push(state.level);
    const prev = range[idx - 1];
    if (!prev) finishReceptive(state, state.level); // below the audience's lowest band
    else if (state.passed.includes(prev)) finishReceptive(state, prev);
    else openBlock(state, prev);
  }
  return { correct };
}

export function productiveTask(state) {
  const tasks = PRODUCTIVE_TASKS[state.audience];
  const i = levelIndex(state.receptiveLevel);
  if (i >= levelIndex('B2') && tasks.high) return tasks.high;
  if (i >= levelIndex('A2') && tasks.mid) return tasks.mid;
  return tasks.low;
}

// Combine receptive and productive estimates (60/40) into the recommendation.
export function buildResult(state, productive) {
  const receptive = state.receptiveLevel;
  let overall = receptive;
  if (productive?.level && LEVELS.includes(productive.level)) {
    const blended = Math.round(levelIndex(receptive) * 0.6 + levelIndex(productive.level) * 0.4);
    overall = clampToAudience(LEVELS[blended], state.audience);
  }
  const skills = {};
  for (const [k, v] of Object.entries(state.skills)) skills[k] = Math.round((v.correct / v.total) * 100);
  return {
    recommendedLevel: overall,
    receptiveLevel: receptive,
    productiveLevel: productive?.level || null,
    productiveFeedback: productive || null,
    skills,
    path: Object.entries(state.blocks).map(([level, b]) => ({
      level, correct: b.answers.filter(Boolean).length, total: b.answers.length,
    })),
  };
}

/*
 * School timetable solver.
 *
 * Places every lesson period into a weekly grid (days x periods) so that:
 *   - no teacher, class or room is in two places at once
 *   - teachers and classes are never scheduled in slots marked unavailable
 *   - teachers never exceed their maximum periods per day
 *   - a subject is spread across the week (at most ceil(sessions / days) sessions per day)
 *   - double periods sit in two consecutive periods on the same day
 *   - lessons that need a special room (lab, gym, ...) get a free room of that type
 *
 * The search is an "iterative forward search" (the approach used by university
 * course timetabling solvers): repeatedly take an unplaced lesson, put it in the
 * slot that clashes with the fewest already placed lessons, and un-place those.
 * Soft goals (few gaps for classes and teachers) break ties.
 *
 * Works in the browser (window.TimetableSolver) and in Node (require).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.TimetableSolver = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  function mulberry32(seed) {
    let a = seed >>> 0;
    return function () {
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function blockedGrid(keys, days, P) {
    const grid = new Uint8Array(days.length * P);
    (keys || []).forEach((key) => {
      const [dayName, p] = String(key).split('|');
      const d = days.indexOf(dayName);
      const period = Number(p);
      if (d >= 0 && period >= 0 && period < P) grid[d * P + period] = 1;
    });
    return grid;
  }

  /** Turns the app's data into index-based structures the solver works with. */
  function normalize(data) {
    const days = (data.settings.days || []).slice();
    const D = days.length;
    const P = (data.settings.periods || []).length;
    const tIndex = new Map();
    const cIndex = new Map();
    const rIndex = new Map();

    const teachers = (data.teachers || []).map((t, i) => {
      tIndex.set(t.id, i);
      const max = Number(t.maxPerDay);
      return { id: t.id, name: t.name, maxPerDay: max > 0 ? max : P, blocked: blockedGrid(t.unavailable, days, P) };
    });
    const classes = (data.classes || []).map((c, i) => {
      cIndex.set(c.id, i);
      return { id: c.id, name: c.name, blocked: blockedGrid(c.unavailable, days, P) };
    });
    const rooms = (data.rooms || []).map((r, i) => {
      rIndex.set(r.id, i);
      return { id: r.id, name: r.name, label: String(r.type || '').trim(), type: String(r.type || '').trim().toLowerCase() };
    });
    const subjects = new Map((data.subjects || []).map((s) => [s.id, s]));

    const lessons = [];
    const errors = [];
    (data.lessons || []).forEach((l) => {
      const perWeek = Math.max(0, Math.floor(Number(l.perWeek) || 0));
      if (!perWeek) return;
      const subj = subjects.get(l.subjectId);
      const classIds = l.classIds || (l.classId ? [l.classId] : []);
      const teacherIds = l.teacherIds || (l.teacherId ? [l.teacherId] : []);
      const classIdx = classIds.map((id) => cIndex.get(id)).filter((x) => x !== undefined);
      const teacherIdx = teacherIds.map((id) => tIndex.get(id)).filter((x) => x !== undefined);
      const label =
        (subj ? subj.name : 'Unknown subject') + ' – ' + (classIdx.map((c) => classes[c].name).join(', ') || 'no class');
      if (!classIdx.length) {
        errors.push(label + ': lesson has no class.');
        return;
      }
      const roomType = String((subj && subj.roomType) || '').trim().toLowerCase();
      let roomIdx = null; // null = no special room needed
      if (l.roomId && rIndex.has(l.roomId)) roomIdx = [rIndex.get(l.roomId)];
      else if (roomType) {
        roomIdx = rooms.map((r, i) => (r.type === roomType ? i : -1)).filter((i) => i >= 0);
        if (!roomIdx.length) {
          errors.push(label + ': needs a room of type "' + subj.roomType + '" but no such room exists.');
          return;
        }
      }
      const doubles = Math.min(Math.max(0, Math.floor(Number(l.doubles) || 0)), Math.floor(perWeek / 2));
      const sessions = perWeek - doubles;
      lessons.push({
        id: l.id,
        label,
        classIdx,
        teacherIdx,
        roomIdx,
        perWeek,
        doubles,
        singles: perWeek - 2 * doubles,
        maxPerDay: D ? Math.ceil(sessions / D) : 0,
      });
    });
    return { days, D, P, teachers, classes, rooms, lessons, errors };
  }

  /** Checks the data for problems that make a full timetable impossible. */
  function diagnose(data) {
    const N = normalize(data);
    const { D, P, teachers, classes, rooms, lessons } = N;
    const warnings = N.errors.slice();
    const slots = D * P;
    if (!D || !P) warnings.push('Choose at least one school day and one period.');
    const classLoad = classes.map(() => 0);
    const teacherLoad = teachers.map(() => 0);
    const roomTypeLoad = new Map();
    lessons.forEach((L) => {
      L.classIdx.forEach((c) => (classLoad[c] += L.perWeek));
      L.teacherIdx.forEach((t) => (teacherLoad[t] += L.perWeek));
      if (L.roomIdx && L.roomIdx.length > 1) {
        const type = rooms[L.roomIdx[0]].label;
        roomTypeLoad.set(type, (roomTypeLoad.get(type) || 0) + L.perWeek);
      }
      if (!L.teacherIdx.length) warnings.push(L.label + ': no teacher assigned (it will be scheduled without one).');
      if (L.maxPerDay * D < L.perWeek - L.doubles)
        warnings.push(L.label + ': too many periods for the number of days.');
    });
    classes.forEach((c, i) => {
      const free = slots - c.blocked.reduce((a, b) => a + b, 0);
      if (classLoad[i] > free)
        warnings.push(`Class ${c.name} needs ${classLoad[i]} periods but only ${free} are available per week.`);
    });
    teachers.forEach((t, i) => {
      const free = slots - t.blocked.reduce((a, b) => a + b, 0);
      const cap = Math.min(free, t.maxPerDay * D);
      if (teacherLoad[i] > cap)
        warnings.push(
          `${t.name} is given ${teacherLoad[i]} periods but can teach at most ${cap} (availability / max per day).`
        );
    });
    roomTypeLoad.forEach((load, type) => {
      const count = rooms.filter((r) => r.type === type.toLowerCase()).length;
      if (load > count * slots)
        warnings.push(`Rooms of type "${type}" are needed for ${load} periods but only ${count * slots} room-periods exist.`);
    });
    return warnings;
  }

  /**
   * Creates a solver that can be run in small steps (so a browser page stays responsive).
   * opts: { seed, maxIterations }
   */
  function createSolver(data, opts) {
    opts = opts || {};
    const rnd = opts.seed != null ? mulberry32(opts.seed) : Math.random;
    const N = normalize(data);
    const { days, D, P, teachers, classes, rooms, lessons } = N;
    const S = D * P;
    const maxIterations = opts.maxIterations || 200000;

    // Each lesson becomes several units: one per single period, one per double period.
    const units = [];
    const unitsOfLesson = lessons.map(() => []);
    lessons.forEach((L, li) => {
      for (let i = 0; i < L.doubles; i++) units.push({ li, len: 2 });
      for (let i = 0; i < L.singles; i++) units.push({ li, len: 1 });
    });
    units.forEach((U, u) => {
      unitsOfLesson[U.li].push(u);
      const L = lessons[U.li];
      U.domain = [];
      if (L.teacherIdx.some((t) => teachers[t].maxPerDay < U.len)) return;
      for (let d = 0; d < D; d++) {
        for (let p = 0; p + U.len <= P; p++) {
          let ok = true;
          for (let k = 0; k < U.len && ok; k++) {
            const s = d * P + p + k;
            if (L.teacherIdx.some((t) => teachers[t].blocked[s])) ok = false;
            else if (L.classIdx.some((c) => classes[c].blocked[s])) ok = false;
          }
          if (ok) U.domain.push(d * P + p);
        }
      }
    });

    const tGrid = teachers.map(() => new Int32Array(S).fill(-1));
    const cGrid = classes.map(() => new Int32Array(S).fill(-1));
    const rGrid = rooms.map(() => new Int32Array(S).fill(-1));
    const start = new Int32Array(units.length).fill(-1);
    const room = new Int32Array(units.length).fill(-1);
    const bumps = new Int32Array(units.length);

    function place(u, s, r) {
      const U = units[u];
      const L = lessons[U.li];
      for (let k = 0; k < U.len; k++) {
        L.teacherIdx.forEach((t) => (tGrid[t][s + k] = u));
        L.classIdx.forEach((c) => (cGrid[c][s + k] = u));
        if (r >= 0) rGrid[r][s + k] = u;
      }
      start[u] = s;
      room[u] = r;
    }

    function unplace(u) {
      const U = units[u];
      const L = lessons[U.li];
      const s = start[u];
      for (let k = 0; k < U.len; k++) {
        L.teacherIdx.forEach((t) => (tGrid[t][s + k] = -1));
        L.classIdx.forEach((c) => (cGrid[c][s + k] = -1));
        if (room[u] >= 0) rGrid[room[u]][s + k] = -1;
      }
      start[u] = -1;
      room[u] = -1;
    }

    function pickRandom(arr) {
      return arr[Math.floor(rnd() * arr.length)];
    }

    /** Units that must be un-placed for unit u to go at slot s in room r. */
    function conflicts(u, s, r) {
      const U = units[u];
      const L = lessons[U.li];
      const d = Math.floor(s / P);
      const set = new Set();
      for (let k = 0; k < U.len; k++) {
        L.teacherIdx.forEach((t) => tGrid[t][s + k] >= 0 && set.add(tGrid[t][s + k]));
        L.classIdx.forEach((c) => cGrid[c][s + k] >= 0 && set.add(cGrid[c][s + k]));
        if (r >= 0 && rGrid[r][s + k] >= 0) set.add(rGrid[r][s + k]);
      }
      // Teacher daily maximum
      L.teacherIdx.forEach((t) => {
        const max = teachers[t].maxPerDay;
        if (max >= P) return;
        let load = U.len;
        const others = new Set();
        for (let p = 0; p < P; p++) {
          const v = tGrid[t][d * P + p];
          if (v >= 0 && !set.has(v)) {
            load++;
            others.add(v);
          }
        }
        const list = Array.from(others);
        while (load > max && list.length) {
          const v = list.splice(Math.floor(rnd() * list.length), 1)[0];
          set.add(v);
          load -= units[v].len;
        }
      });
      // Spread the subject across the week
      const sameDay = unitsOfLesson[U.li].filter(
        (v) => v !== u && start[v] >= 0 && Math.floor(start[v] / P) === d && !set.has(v)
      );
      while (sameDay.length + 1 > L.maxPerDay && sameDay.length) {
        set.add(sameDay.splice(Math.floor(rnd() * sameDay.length), 1)[0]);
      }
      return set;
    }

    function gaps(occ) {
      let first = -1;
      let last = -1;
      let filled = 0;
      for (let p = 0; p < occ.length; p++) {
        if (occ[p]) {
          if (first < 0) first = p;
          last = p;
          filled++;
        }
      }
      return first < 0 ? 0 : last - first + 1 - filled;
    }

    /** How many extra idle gaps (classes weigh more than teachers) the placement creates. */
    function softCost(u, s, removed) {
      const U = units[u];
      const L = lessons[U.li];
      const d = Math.floor(s / P);
      const p0 = s - d * P;
      let cost = 0;
      const rowDelta = (grid) => {
        const before = new Array(P);
        for (let p = 0; p < P; p++) {
          const v = grid[d * P + p];
          before[p] = v >= 0 && !removed.has(v);
        }
        const after = before.slice();
        for (let k = 0; k < U.len; k++) after[p0 + k] = true;
        return gaps(after) - gaps(before);
      };
      L.classIdx.forEach((c) => (cost += 3 * rowDelta(cGrid[c])));
      L.teacherIdx.forEach((t) => (cost += rowDelta(tGrid[t])));
      return cost;
    }

    function chooseValue(u) {
      const U = units[u];
      const L = lessons[U.li];
      const roomChoices = L.roomIdx || [-1];
      if (rnd() < 0.02) {
        const s = pickRandom(U.domain);
        const r = pickRandom(roomChoices);
        return { s, r, set: conflicts(u, s, r) };
      }
      let best = null;
      let bestCost = Infinity;
      for (const s of U.domain) {
        for (const r of roomChoices) {
          const set = conflicts(u, s, r);
          let cost = 0;
          set.forEach((v) => (cost += 100 + 10 * Math.min(bumps[v], 20)));
          if (cost > bestCost) continue;
          cost += softCost(u, s, set) + rnd() * 2;
          if (cost < bestCost) {
            bestCost = cost;
            best = { s, r, set };
          }
        }
      }
      return best;
    }

    const unassigned = new Set();
    const impossible = [];
    units.forEach((U, u) => (U.domain.length ? unassigned.add(u) : impossible.push(u)));
    let iterations = 0;
    let bestUnassigned = Infinity;
    let bestStart = start.slice();
    let bestRoom = room.slice();

    function selectUnit() {
      if (rnd() < 0.15) {
        const arr = Array.from(unassigned);
        return pickRandom(arr);
      }
      let best = -1;
      let bestKey = Infinity;
      unassigned.forEach((u) => {
        const key = units[u].domain.length / units[u].len - 3 * bumps[u] + rnd();
        if (key < bestKey) {
          bestKey = key;
          best = u;
        }
      });
      return best;
    }

    function step(n) {
      for (let i = 0; i < n && unassigned.size && iterations < maxIterations; i++) {
        iterations++;
        const u = selectUnit();
        const val = chooseValue(u);
        val.set.forEach((v) => {
          unplace(v);
          unassigned.add(v);
          bumps[v]++;
        });
        place(u, val.s, val.r);
        unassigned.delete(u);
        if (unassigned.size < bestUnassigned) {
          bestUnassigned = unassigned.size;
          bestStart = start.slice();
          bestRoom = room.slice();
        }
      }
      return {
        done: unassigned.size === 0 || iterations >= maxIterations,
        placed: units.length - impossible.length - unassigned.size,
        bestPlaced: units.length - impossible.length - Math.min(bestUnassigned, unassigned.size),
        total: units.length,
        iterations,
      };
    }

    function result() {
      const finalStart = unassigned.size <= bestUnassigned ? start : bestStart;
      const finalRoom = unassigned.size <= bestUnassigned ? room : bestRoom;
      const placements = [];
      const unplaced = [];
      units.forEach((U, u) => {
        const L = lessons[U.li];
        const s = finalStart[u];
        if (s < 0) {
          unplaced.push({
            lessonId: L.id,
            label: L.label,
            length: U.len,
            reason: U.domain.length
              ? 'Could not be fitted without a clash.'
              : 'No allowed time slot (check teacher/class availability and max periods per day).',
          });
          return;
        }
        const d = Math.floor(s / P);
        placements.push({
          lessonId: L.id,
          day: days[d],
          period: s - d * P,
          length: U.len,
          roomId: finalRoom[u] >= 0 ? rooms[finalRoom[u]].id : null,
        });
      });
      return { placements, unplaced, errors: N.errors, iterations };
    }

    return { step, result, totalUnits: units.length };
  }

  /** Runs the solver to completion (used by tests and scripts). */
  function solve(data, opts) {
    const solver = createSolver(data, opts);
    let st;
    do st = solver.step(5000);
    while (!st.done);
    return solver.result();
  }

  /** Lists every rule a set of placements breaks. */
  function validate(data, placements) {
    const N = normalize(data);
    const { days, D, P, teachers, classes, rooms } = N;
    const byId = new Map(N.lessons.map((L) => [L.id, L]));
    const roomIndex = new Map(rooms.map((r, i) => [r.id, i]));
    const tCells = new Map();
    const cCells = new Map();
    const rCells = new Map();
    const tDay = new Map();
    const lessonDay = new Map();
    const placed = new Map();
    const conflicts = [];
    const add = (map, key, label) => {
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(label);
    };

    placements.forEach((pl) => {
      const L = byId.get(pl.lessonId);
      if (!L) return;
      const d = days.indexOf(pl.day);
      if (d < 0 || pl.period + pl.length > P) {
        conflicts.push(`${L.label} is outside the school week.`);
        return;
      }
      placed.set(L.id, (placed.get(L.id) || 0) + pl.length);
      const ld = L.id + '|' + d;
      lessonDay.set(ld, (lessonDay.get(ld) || 0) + 1);
      for (let k = 0; k < pl.length; k++) {
        const s = d * P + pl.period + k;
        const when = `${pl.day} period ${pl.period + k + 1}`;
        L.teacherIdx.forEach((t) => {
          add(tCells, t + '|' + s, L.label);
          if (teachers[t].blocked[s]) conflicts.push(`${teachers[t].name} is unavailable on ${when} (${L.label}).`);
        });
        L.classIdx.forEach((c) => {
          add(cCells, c + '|' + s, L.label);
          if (classes[c].blocked[s]) conflicts.push(`${classes[c].name} is unavailable on ${when}.`);
        });
        if (pl.roomId && roomIndex.has(pl.roomId)) add(rCells, roomIndex.get(pl.roomId) + '|' + s, L.label);
      }
      L.teacherIdx.forEach((t) => tDay.set(t + '|' + d, (tDay.get(t + '|' + d) || 0) + pl.length));
    });

    const where = (s) => `${days[Math.floor(s / P)]} period ${(s % P) + 1}`;
    tCells.forEach((list, key) => {
      if (list.length < 2) return;
      const [t, s] = key.split('|').map(Number);
      conflicts.push(`${teachers[t].name} is double-booked on ${where(s)}: ${list.join(' / ')}.`);
    });
    cCells.forEach((list, key) => {
      if (list.length < 2) return;
      const [c, s] = key.split('|').map(Number);
      conflicts.push(`${classes[c].name} has two lessons on ${where(s)}: ${list.join(' / ')}.`);
    });
    rCells.forEach((list, key) => {
      if (list.length < 2) return;
      const [r, s] = key.split('|').map(Number);
      conflicts.push(`Room ${rooms[r].name} is double-booked on ${where(s)}: ${list.join(' / ')}.`);
    });
    tDay.forEach((count, key) => {
      const [t, d] = key.split('|').map(Number);
      if (count > teachers[t].maxPerDay)
        conflicts.push(`${teachers[t].name} teaches ${count} periods on ${days[d]} (max ${teachers[t].maxPerDay}).`);
    });

    const warnings = [];
    lessonDay.forEach((count, key) => {
      const [id, d] = key.split('|');
      const L = byId.get(id);
      if (count > L.maxPerDay) warnings.push(`${L.label} appears ${count} times on ${days[d]}.`);
    });
    const missing = [];
    N.lessons.forEach((L) => {
      const got = placed.get(L.id) || 0;
      if (got < L.perWeek) missing.push(`${L.label}: ${L.perWeek - got} of ${L.perWeek} periods not scheduled.`);
    });
    return { conflicts, warnings, missing, D };
  }

  return { createSolver, solve, validate, diagnose, normalize };
});

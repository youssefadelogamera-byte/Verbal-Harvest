/* School Timetable Builder — user interface. Data is kept in the browser and can be saved to / opened from a file. */
(function () {
  'use strict';

  const STORE_KEY = 'school-timetable-v1';
  const ALL_DAYS = ['Saturday', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];
  const PALETTE = ['#2563eb', '#16a34a', '#9333ea', '#d97706', '#db2777', '#0891b2', '#dc2626', '#4f46e5', '#65a30d', '#0d9488', '#c026d3', '#ea580c'];
  const TABS = [
    { id: 'school', label: 'School & periods' },
    { id: 'departments', label: 'Departments' },
    { id: 'teachers', label: 'Teachers' },
    { id: 'subjects', label: 'Subjects' },
    { id: 'classes', label: 'Classes' },
    { id: 'rooms', label: 'Rooms' },
    { id: 'lessons', label: 'Lessons' },
    { id: 'timetable', label: 'Timetable' },
  ];

  const Solver = window.TimetableSolver;
  const $ = (id) => document.getElementById(id);

  /* ---------- small helpers ---------- */

  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    let value;
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v == null || v === false) continue;
        if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
        else if (k === 'class') el.className = v;
        else if (k === 'value') value = v;
        else if (k === 'checked' || k === 'disabled' || k === 'selected' || k === 'multiple') el[k] = !!v;
        else el.setAttribute(k, v === true ? '' : v);
      }
    }
    kids.flat(Infinity).forEach((c) => {
      if (c == null || c === false) return;
      el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    });
    if (value !== undefined) el.value = value;
    return el;
  }

  const uid = (prefix) => prefix + '-' + Math.random().toString(36).slice(2, 9);
  const byName = (a, b) => String(a.name || '').localeCompare(String(b.name || ''), undefined, { numeric: true });
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

  let toastTimer;
  function toast(msg) {
    const el = $('toast');
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('show'), 2800);
  }

  function download(name, text, type) {
    const blob = new Blob([text], { type });
    const a = h('a', { href: URL.createObjectURL(blob), download: name });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  /* ---------- state ---------- */

  function makePeriods(n) {
    const out = [];
    let minutes = 8 * 60;
    const fmt = (m) => String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
    for (let i = 0; i < n; i++) {
      out.push({ label: String(i + 1), start: fmt(minutes), end: fmt(minutes + 45) });
      minutes += 45;
    }
    return out;
  }

  function emptyState() {
    return {
      version: 1,
      settings: { schoolName: 'My School', days: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday'], periods: makePeriods(7) },
      departments: [],
      teachers: [],
      subjects: [],
      classes: [],
      rooms: [],
      lessons: [],
      timetable: null,
    };
  }

  function migrate(d) {
    const base = emptyState();
    const out = Object.assign(base, d);
    out.settings = Object.assign(emptyState().settings, d.settings || {});
    ['departments', 'teachers', 'subjects', 'classes', 'rooms', 'lessons'].forEach((k) => {
      if (!Array.isArray(out[k])) out[k] = [];
    });
    return out;
  }

  function load() {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      if (raw) return migrate(JSON.parse(raw));
    } catch (e) {
      /* storage unavailable */
    }
    return null;
  }

  function save() {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(state));
    } catch (e) {
      /* storage unavailable: data lives until the page is closed; "Save to file" still works */
    }
  }

  /** Call after any change to the school data. */
  function changed() {
    if (state.timetable) state.timetable.stale = true;
    save();
  }

  let state = load() || emptyState();
  const ui = {
    tab: state.lessons.length ? 'timetable' : 'school',
    view: 'class',
    entity: '',
    selected: null,
    generating: false,
    stop: false,
    lessonFilter: '',
    teacherDept: '',
    bulk: { subjectId: '', teacherId: '', perWeek: 4, doubles: 0, classIds: new Set() },
    free: { day: '', period: 0 },
  };

  function lookups() {
    const m = (arr) => new Map(arr.map((x) => [x.id, x]));
    return {
      depts: m(state.departments),
      teachers: m(state.teachers),
      subjects: m(state.subjects),
      classes: m(state.classes),
      rooms: m(state.rooms),
      lessons: m(state.lessons),
    };
  }

  const slotsPerWeek = () => state.settings.days.length * state.settings.periods.length;

  function teacherLoad(id) {
    return state.lessons.reduce((sum, l) => sum + (l.teacherId === id ? Number(l.perWeek) || 0 : 0), 0);
  }
  function classLoad(id) {
    return state.lessons.reduce((sum, l) => sum + (l.classId === id ? Number(l.perWeek) || 0 : 0), 0);
  }
  function teacherCapacity(t) {
    const max = Number(t.maxPerDay) > 0 ? Number(t.maxPerDay) : state.settings.periods.length;
    const blocked = (t.unavailable || []).filter((k) => {
      const [d, p] = k.split('|');
      return state.settings.days.includes(d) && Number(p) < state.settings.periods.length;
    }).length;
    return Math.min(slotsPerWeek() - blocked, max * state.settings.days.length);
  }

  function loadChip(load, cap) {
    const cls = load > cap ? 'bad' : load === 0 ? '' : 'ok';
    return h('span', { class: 'chip ' + cls, title: `${load} periods scheduled out of ${cap} possible` }, `${load} / ${cap}`);
  }

  /* ---------- generic list editor ---------- */

  function fieldInput(item, c) {
    if (c.render) return c.render(item);
    const after = () => {
      changed();
      if (c.rerender) render();
    };
    if (c.type === 'select') {
      const opts = c.options();
      return h(
        'select',
        { value: item[c.key] || '', onchange: (e) => ((item[c.key] = e.target.value), after()) },
        h('option', { value: '' }, c.placeholder || '—'),
        opts.map((o) =>
          o.group
            ? h('optgroup', { label: o.group }, o.items.map((x) => h('option', { value: x.value }, x.label)))
            : h('option', { value: o.value }, o.label)
        )
      );
    }
    if (c.type === 'number') {
      return h('input', {
        type: 'number',
        min: c.min != null ? c.min : 0,
        max: c.max,
        value: item[c.key] != null ? item[c.key] : '',
        onchange: (e) => ((item[c.key] = e.target.value === '' ? '' : Number(e.target.value)), after()),
      });
    }
    if (c.type === 'color') {
      return h('input', { type: 'color', value: item[c.key] || '#888888', onchange: (e) => ((item[c.key] = e.target.value), after()) });
    }
    return h('input', {
      type: 'text',
      value: item[c.key] || '',
      placeholder: c.placeholder || '',
      list: c.list,
      onchange: (e) => ((item[c.key] = e.target.value.trim()), after()),
    });
  }

  function listEditor(opts) {
    const { items, columns, onAdd, addLabel, onDelete, emptyText, bulkAdd, bulkHint } = opts;
    const body = items.length
      ? h(
          'div',
          { class: 'table-wrap' },
          h(
            'table',
            { class: 'data' },
            h('thead', null, h('tr', null, columns.map((c) => h('th', { style: c.width ? `width:${c.width}` : null }, c.label)), h('th', { style: 'width:36px' }))),
            h(
              'tbody',
              null,
              items.map((item) =>
                h(
                  'tr',
                  null,
                  columns.map((c) => h('td', null, fieldInput(item, c))),
                  h('td', null, h('button', { class: 'icon-btn', title: 'Delete', onclick: () => onDelete(item) }, '✕'))
                )
              )
            )
          )
        )
      : h('div', { class: 'empty' }, emptyText || 'Nothing here yet.');

    const actions = h(
      'div',
      { class: 'row', style: 'margin-top:12px' },
      h('button', {
        class: 'btn primary',
        onclick: () => {
          onAdd();
          changed();
          render();
          const inputs = document.querySelectorAll('table.data tbody tr:last-child input[type=text]');
          if (inputs[0]) inputs[0].focus();
        },
      }, '+ ' + addLabel)
    );

    let bulk = null;
    if (bulkAdd) {
      const ta = h('textarea', { rows: 4, style: 'width:100%;font:inherit;padding:8px;border:1px solid var(--line);border-radius:8px', placeholder: bulkHint });
      bulk = h(
        'details',
        { style: 'margin-top:12px' },
        h('summary', { class: 'muted', style: 'cursor:pointer' }, 'Add many at once (paste a list)'),
        h('div', { style: 'margin-top:8px' }, ta),
        h('button', {
          class: 'btn',
          style: 'margin-top:6px',
          onclick: () => {
            const lines = ta.value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
            if (!lines.length) return;
            lines.forEach(bulkAdd);
            changed();
            render();
            toast(`Added ${lines.length}.`);
          },
        }, 'Add list')
      );
    }
    return h('div', null, body, actions, bulk);
  }

  function panel(title, intro, ...content) {
    return h('section', { class: 'panel' }, h('h2', null, title), intro ? h('p', { class: 'muted', style: 'margin:0 0 14px' }, intro) : null, content);
  }

  function deptOptions() {
    return state.departments.slice().sort(byName).map((d) => ({ value: d.id, label: d.name }));
  }
  function teacherOptions() {
    const groups = [];
    const L = lookups();
    const byDept = new Map();
    state.teachers.slice().sort(byName).forEach((t) => {
      const key = L.depts.has(t.deptId) ? L.depts.get(t.deptId).name : 'No department';
      if (!byDept.has(key)) byDept.set(key, []);
      byDept.get(key).push({ value: t.id, label: t.name || '(unnamed)' });
    });
    Array.from(byDept.keys()).sort().forEach((k) => groups.push({ group: k, items: byDept.get(k) }));
    return groups;
  }
  function subjectOptions() {
    return state.subjects.slice().sort(byName).map((s) => ({ value: s.id, label: s.name || '(unnamed)' }));
  }
  function classOptions() {
    return state.classes.slice().sort(byName).map((c) => ({ value: c.id, label: c.name || '(unnamed)' }));
  }

  function datalist(id, values) {
    return h('datalist', { id }, Array.from(new Set(values.filter(Boolean))).sort().map((v) => h('option', { value: v })));
  }

  /* ---------- availability dialog ---------- */

  function openAvailability(entity, title) {
    const { days, periods } = state.settings;
    entity.unavailable = entity.unavailable || [];
    const draw = () => {
      const set = new Set(entity.unavailable);
      const toggle = (keys) => {
        const allOff = keys.every((k) => set.has(k));
        keys.forEach((k) => (allOff ? set.delete(k) : set.add(k)));
        entity.unavailable = Array.from(set);
        changed();
        draw();
      };
      const content = $('dialogContent');
      content.innerHTML = '';
      content.append(
        h(
          'table',
          { class: 'avail' },
          h(
            'thead',
            null,
            h('tr', null, h('th'), periods.map((p, i) => h('th', null, h('button', { type: 'button', style: 'background:none;border:0;width:auto;height:auto', title: 'Toggle this period every day', onclick: () => toggle(days.map((d) => d + '|' + i)) }, p.label || i + 1))))
          ),
          h(
            'tbody',
            null,
            days.map((d) =>
              h(
                'tr',
                null,
                h('th', null, h('button', { type: 'button', style: 'background:none;border:0;width:auto;height:auto;font-weight:600', title: 'Toggle the whole day', onclick: () => toggle(periods.map((p, i) => d + '|' + i)) }, d)),
                periods.map((p, i) => {
                  const key = d + '|' + i;
                  const off = set.has(key);
                  return h('td', null, h('button', { type: 'button', class: off ? 'off' : '', title: off ? 'Unavailable' : 'Available', onclick: () => toggle([key]) }, off ? '✕' : '✓'));
                })
              )
            )
          )
        )
      );
    };
    $('dialogTitle').textContent = title;
    $('dialogHint').textContent = 'Click a slot to mark it unavailable (✕). Click a day or period name to toggle the whole row or column.';
    draw();
    const dlg = $('dialog');
    dlg.onclose = () => render();
    dlg.showModal();
  }

  function availabilityButton(entity, title) {
    const n = (entity.unavailable || []).filter((k) => state.settings.days.includes(k.split('|')[0])).length;
    return h('button', { class: 'btn', onclick: () => openAvailability(entity, title) }, n ? `${n} blocked` : 'Always available');
  }

  /* ---------- tabs ---------- */

  function renderSchool() {
    const s = state.settings;
    const dayChecks = ALL_DAYS.map((d) =>
      h(
        'label',
        { class: 'pill-check' + (s.days.includes(d) ? ' on' : '') },
        h('input', {
          type: 'checkbox',
          checked: s.days.includes(d),
          onchange: (e) => {
            const set = new Set(s.days);
            e.target.checked ? set.add(d) : set.delete(d);
            s.days = ALL_DAYS.filter((x) => set.has(x));
            changed();
            render();
          },
        }),
        d
      )
    );

    const periodRows = s.periods.map((p, i) =>
      h(
        'tr',
        null,
        h('td', null, h('input', { type: 'text', value: p.label, style: 'width:80px', onchange: (e) => ((p.label = e.target.value), changed()) })),
        h('td', null, h('input', { type: 'time', value: p.start, onchange: (e) => ((p.start = e.target.value), changed()) })),
        h('td', null, h('input', { type: 'time', value: p.end, onchange: (e) => ((p.end = e.target.value), changed()) })),
        h('td', null, h('button', { class: 'icon-btn', title: 'Remove period', onclick: () => (s.periods.splice(i, 1), changed(), render()) }, '✕'))
      )
    );

    return h(
      'div',
      null,
      panel(
        'Your school',
        'Start here. Then work through the tabs from left to right; the Timetable tab builds the timetable for you.',
        h('label', { class: 'field', style: 'max-width:420px' }, 'School name', h('input', { type: 'text', value: s.schoolName, onchange: (e) => ((s.schoolName = e.target.value), save(), render()) }))
      ),
      panel('School days', 'Which days do lessons run?', h('div', { class: 'row' }, dayChecks)),
      panel(
        'Periods per day',
        'Teaching periods only. Breaks are not periods. Leave a gap in the times instead, and they will show on the printed timetable.',
        h('div', { class: 'table-wrap' }, h('table', { class: 'data', style: 'max-width:520px' }, h('thead', null, h('tr', null, h('th', null, 'Name'), h('th', null, 'Starts'), h('th', null, 'Ends'), h('th'))), h('tbody', null, periodRows))),
        h(
          'div',
          { class: 'row', style: 'margin-top:12px' },
          h('button', {
            class: 'btn primary',
            onclick: () => {
              const last = s.periods[s.periods.length - 1];
              const start = last ? last.end : '08:00';
              const [hh, mm] = start.split(':').map(Number);
              const endM = hh * 60 + mm + 45;
              const end = String(Math.floor(endM / 60) % 24).padStart(2, '0') + ':' + String(endM % 60).padStart(2, '0');
              s.periods.push({ label: String(s.periods.length + 1), start, end });
              changed();
              render();
            },
          }, '+ Add period'),
          h('span', { class: 'muted' }, `${plural(s.days.length * s.periods.length, 'teaching slot')} per week for each class.`)
        )
      )
    );
  }

  function renderDepartments() {
    return panel(
      'Departments',
      'Group your teachers and subjects (e.g. Mathematics, Science, Languages). The colour is used on the timetable.',
      listEditor({
        items: state.departments,
        columns: [
          { key: 'color', label: 'Colour', type: 'color', width: '70px', rerender: true },
          { key: 'name', label: 'Department name', placeholder: 'e.g. Science' },
          { label: 'Teachers', width: '90px', render: (d) => String(state.teachers.filter((t) => t.deptId === d.id).length) },
          { label: 'Subjects', width: '90px', render: (d) => String(state.subjects.filter((s) => s.deptId === d.id).length) },
        ],
        addLabel: 'Add department',
        onAdd: () => state.departments.push({ id: uid('d'), name: '', color: PALETTE[state.departments.length % PALETTE.length] }),
        bulkAdd: (name) => state.departments.push({ id: uid('d'), name, color: PALETTE[state.departments.length % PALETTE.length] }),
        bulkHint: 'One department per line',
        onDelete: (d) => {
          if (!confirm(`Delete department "${d.name}"? Its teachers and subjects are kept.`)) return;
          state.departments = state.departments.filter((x) => x !== d);
          state.teachers.forEach((t) => t.deptId === d.id && (t.deptId = ''));
          state.subjects.forEach((s) => s.deptId === d.id && (s.deptId = ''));
          changed();
          render();
        },
        emptyText: 'No departments yet.',
      })
    );
  }

  function renderTeachers() {
    const list = state.teachers.filter((t) => !ui.teacherDept || t.deptId === ui.teacherDept);
    const filter = h(
      'div',
      { class: 'row', style: 'margin-bottom:10px' },
      h('span', { class: 'muted' }, 'Show:'),
      h('select', { value: ui.teacherDept, onchange: (e) => ((ui.teacherDept = e.target.value), render()) }, h('option', { value: '' }, 'All departments'), deptOptions().map((o) => h('option', { value: o.value }, o.label)))
    );
    return panel(
      'Teachers',
      '"Max/day" is the most periods a teacher can teach in one day. Use "Availability" for part-time staff or days off. "Load" shows the periods given in the Lessons tab against what the teacher can actually teach.',
      filter,
      listEditor({
        items: list,
        columns: [
          { key: 'name', label: 'Name', placeholder: 'Teacher name' },
          { key: 'deptId', label: 'Department', type: 'select', options: deptOptions, width: '200px' },
          { key: 'maxPerDay', label: 'Max/day', type: 'number', min: 1, max: 20, width: '90px', rerender: true },
          { label: 'Availability', width: '150px', render: (t) => availabilityButton(t, `${t.name || 'Teacher'}: availability`) },
          { label: 'Load', width: '90px', render: (t) => loadChip(teacherLoad(t.id), teacherCapacity(t)) },
        ],
        addLabel: 'Add teacher',
        onAdd: () => state.teachers.push({ id: uid('t'), name: '', deptId: ui.teacherDept, maxPerDay: 6, unavailable: [] }),
        bulkAdd: (name) => state.teachers.push({ id: uid('t'), name, deptId: ui.teacherDept, maxPerDay: 6, unavailable: [] }),
        bulkHint: 'One teacher name per line. They are added to the department selected above.',
        onDelete: (t) => {
          const n = state.lessons.filter((l) => l.teacherId === t.id).length;
          if (!confirm(`Delete ${t.name || 'this teacher'}?` + (n ? ` ${plural(n, 'lesson')} will be left without a teacher.` : ''))) return;
          state.teachers = state.teachers.filter((x) => x !== t);
          state.lessons.forEach((l) => l.teacherId === t.id && (l.teacherId = ''));
          changed();
          render();
        },
        emptyText: 'No teachers yet.',
      })
    );
  }

  function renderSubjects() {
    return panel(
      'Subjects',
      'Set "Needs room type" only when a subject must be taught in a special room (e.g. Science Lab, Computer Lab, Gym). Add those rooms in the Rooms tab.',
      datalist('roomTypes', state.rooms.map((r) => r.type).concat(state.subjects.map((s) => s.roomType))),
      listEditor({
        items: state.subjects.slice().sort(byName),
        columns: [
          { key: 'name', label: 'Subject', placeholder: 'e.g. Mathematics' },
          { key: 'short', label: 'Short name', placeholder: 'MATH', width: '110px' },
          { key: 'deptId', label: 'Department', type: 'select', options: deptOptions, width: '200px' },
          { key: 'roomType', label: 'Needs room type', placeholder: '(any classroom)', list: 'roomTypes', width: '190px' },
        ],
        addLabel: 'Add subject',
        onAdd: () => state.subjects.push({ id: uid('s'), name: '', short: '', deptId: '', roomType: '' }),
        bulkAdd: (name) => state.subjects.push({ id: uid('s'), name, short: '', deptId: '', roomType: '' }),
        bulkHint: 'One subject per line',
        onDelete: (s) => {
          const n = state.lessons.filter((l) => l.subjectId === s.id).length;
          if (!confirm(`Delete subject "${s.name}"?` + (n ? ` This also deletes ${plural(n, 'lesson')}.` : ''))) return;
          state.subjects = state.subjects.filter((x) => x !== s);
          state.lessons = state.lessons.filter((l) => l.subjectId !== s.id);
          changed();
          render();
        },
        emptyText: 'No subjects yet.',
      })
    );
  }

  function renderClasses() {
    return panel(
      'Classes',
      'Each class (section) gets its own timetable. "Grade" groups classes so you can add lessons to a whole grade at once. "Load" compares the class\'s lessons with the slots in the week.',
      datalist('grades', state.classes.map((c) => c.grade)),
      listEditor({
        items: state.classes.slice().sort(byName),
        columns: [
          { key: 'name', label: 'Class', placeholder: 'e.g. 7A' },
          { key: 'grade', label: 'Grade / year', placeholder: 'e.g. Grade 7', list: 'grades', width: '180px' },
          { label: 'Availability', width: '150px', render: (c) => availabilityButton(c, `Class ${c.name || ''}: availability`) },
          { label: 'Load', width: '90px', render: (c) => loadChip(classLoad(c.id), slotsPerWeek() - (c.unavailable || []).length) },
        ],
        addLabel: 'Add class',
        onAdd: () => state.classes.push({ id: uid('c'), name: '', grade: '', unavailable: [] }),
        bulkAdd: (line) => {
          const [name, grade] = line.split(/[,\t;]/).map((s) => s.trim());
          state.classes.push({ id: uid('c'), name, grade: grade || '', unavailable: [] });
        },
        bulkHint: 'One class per line. Optionally add the grade after a comma, e.g.\n7A, Grade 7\n7B, Grade 7',
        onDelete: (c) => {
          const n = state.lessons.filter((l) => l.classId === c.id).length;
          if (!confirm(`Delete class "${c.name}"?` + (n ? ` This also deletes ${plural(n, 'lesson')}.` : ''))) return;
          state.classes = state.classes.filter((x) => x !== c);
          state.lessons = state.lessons.filter((l) => l.classId !== c.id);
          changed();
          render();
        },
        emptyText: 'No classes yet.',
      })
    );
  }

  function renderRooms() {
    return panel(
      'Special rooms',
      'Optional. Add rooms only for subjects that need them (labs, gym, art room). Ordinary lessons are assumed to happen in the class\'s own room. A room\'s type must match the "Needs room type" of the subject.',
      datalist('roomTypes', state.rooms.map((r) => r.type).concat(state.subjects.map((s) => s.roomType))),
      listEditor({
        items: state.rooms,
        columns: [
          { key: 'name', label: 'Room', placeholder: 'e.g. Lab 1' },
          { key: 'type', label: 'Type', placeholder: 'e.g. Science Lab', list: 'roomTypes', width: '220px' },
          {
            label: 'Used by',
            render: (r) => {
              const t = String(r.type || '').trim().toLowerCase();
              const names = state.subjects.filter((s) => t && String(s.roomType || '').trim().toLowerCase() === t).map((s) => s.name);
              return names.length ? names.join(', ') : h('span', { class: 'muted' }, 'no subject');
            },
          },
        ],
        addLabel: 'Add room',
        onAdd: () => state.rooms.push({ id: uid('r'), name: '', type: '' }),
        onDelete: (r) => {
          state.rooms = state.rooms.filter((x) => x !== r);
          changed();
          render();
        },
        emptyText: 'No special rooms. That is fine if no subject needs one.',
      })
    );
  }

  function renderLessons() {
    const L = lookups();
    const b = ui.bulk;
    const grades = new Map();
    state.classes.slice().sort(byName).forEach((c) => {
      const g = c.grade || 'Other';
      if (!grades.has(g)) grades.set(g, []);
      grades.get(g).push(c);
    });

    const classPicker = h(
      'div',
      { class: 'class-picker' },
      Array.from(grades.keys()).sort((a, b2) => a.localeCompare(b2, undefined, { numeric: true })).map((g) => {
        const list = grades.get(g);
        const all = list.every((c) => b.classIds.has(c.id));
        return h(
          'div',
          { class: 'grade-row' },
          h('button', { class: 'btn', style: 'min-width:110px', onclick: () => (list.forEach((c) => (all ? b.classIds.delete(c.id) : b.classIds.add(c.id))), render()) }, (all ? '✓ ' : '') + g),
          list.map((c) =>
            h(
              'label',
              { class: 'pill-check' + (b.classIds.has(c.id) ? ' on' : '') },
              h('input', { type: 'checkbox', checked: b.classIds.has(c.id), onchange: (e) => (e.target.checked ? b.classIds.add(c.id) : b.classIds.delete(c.id), render()) }),
              c.name
            )
          )
        );
      })
    );

    const subj = L.subjects.get(b.subjectId);
    const addForm = panel(
      'Add lessons',
      'Choose a subject, the teacher, how many periods a week, and the classes. One lesson is created for each class ticked. You can change the teacher of any single class in the list below.',
      state.classes.length && state.subjects.length
        ? h(
            'div',
            null,
            h(
              'div',
              { class: 'row', style: 'align-items:flex-end;margin-bottom:12px' },
              h('label', { class: 'field' }, 'Subject', h('select', { value: b.subjectId, onchange: (e) => ((b.subjectId = e.target.value), render()) }, h('option', { value: '' }, 'Choose…'), subjectOptions().map((o) => h('option', { value: o.value }, o.label)))),
              h(
                'label',
                { class: 'field' },
                'Teacher',
                h(
                  'select',
                  { value: b.teacherId, onchange: (e) => (b.teacherId = e.target.value) },
                  h('option', { value: '' }, 'Choose…'),
                  teacherOptions()
                    .sort((x, y) => (subj && L.depts.get(subj.deptId) && x.group === L.depts.get(subj.deptId).name ? -1 : subj && L.depts.get(subj.deptId) && y.group === L.depts.get(subj.deptId).name ? 1 : 0))
                    .map((g) => h('optgroup', { label: g.group }, g.items.map((x) => h('option', { value: x.value }, x.label))))
                )
              ),
              h('label', { class: 'field' }, 'Periods / week', h('input', { type: 'number', min: 1, max: 40, value: b.perWeek, onchange: (e) => (b.perWeek = Number(e.target.value)) })),
              h('label', { class: 'field', title: 'How many of those periods are double periods (two in a row)' }, 'Of which doubles', h('input', { type: 'number', min: 0, max: 20, value: b.doubles, onchange: (e) => (b.doubles = Number(e.target.value)) }))
            ),
            h('div', { class: 'muted small', style: 'margin-bottom:6px' }, 'Classes (click a grade to tick all its classes):'),
            classPicker,
            h(
              'div',
              { class: 'row', style: 'margin-top:14px' },
              h('button', {
                class: 'btn primary',
                onclick: () => {
                  if (!b.subjectId) return toast('Choose a subject.');
                  if (!b.classIds.size) return toast('Tick at least one class.');
                  if (!(b.perWeek > 0)) return toast('Periods per week must be at least 1.');
                  const doubles = Math.min(Math.max(0, b.doubles || 0), Math.floor(b.perWeek / 2));
                  b.classIds.forEach((classId) => state.lessons.push({ id: uid('l'), classId, subjectId: b.subjectId, teacherId: b.teacherId, perWeek: b.perWeek, doubles }));
                  toast(`Added ${plural(b.classIds.size, 'lesson')}.`);
                  b.classIds.clear();
                  changed();
                  render();
                },
              }, '+ Add lessons')
            )
          )
        : h('div', { class: 'notice info' }, 'Add classes and subjects first.')
    );

    // Lesson list with filter
    const [ftype, fid] = ui.lessonFilter.split(':');
    const lessons = state.lessons
      .filter((l) => !ftype || (ftype === 'c' && l.classId === fid) || (ftype === 't' && l.teacherId === fid) || (ftype === 's' && l.subjectId === fid))
      .sort((a, b2) => {
        const ca = L.classes.get(a.classId);
        const cb = L.classes.get(b2.classId);
        const sa = L.subjects.get(a.subjectId);
        const sb = L.subjects.get(b2.subjectId);
        return byName(ca || {}, cb || {}) || byName(sa || {}, sb || {});
      });
    const filter = h(
      'select',
      { value: ui.lessonFilter, onchange: (e) => ((ui.lessonFilter = e.target.value), render()) },
      h('option', { value: '' }, `All lessons (${state.lessons.length})`),
      h('optgroup', { label: 'Class' }, classOptions().map((o) => h('option', { value: 'c:' + o.value }, o.label))),
      h('optgroup', { label: 'Teacher' }, state.teachers.slice().sort(byName).map((t) => h('option', { value: 't:' + t.id }, t.name))),
      h('optgroup', { label: 'Subject' }, subjectOptions().map((o) => h('option', { value: 's:' + o.value }, o.label)))
    );
    const total = lessons.reduce((s, l) => s + (Number(l.perWeek) || 0), 0);

    const listPanel = panel(
      'Lesson list',
      null,
      h('div', { class: 'row', style: 'margin-bottom:10px' }, h('span', { class: 'muted' }, 'Show:'), filter, h('span', { class: 'muted' }, plural(total, 'period') + ' per week')),
      listEditor({
        items: lessons,
        columns: [
          { key: 'classId', label: 'Class', type: 'select', options: classOptions, width: '120px', rerender: true },
          { key: 'subjectId', label: 'Subject', type: 'select', options: subjectOptions, rerender: true },
          { key: 'teacherId', label: 'Teacher', type: 'select', options: teacherOptions, placeholder: '— no teacher —', rerender: true },
          { key: 'perWeek', label: 'Periods/wk', type: 'number', min: 1, width: '100px', rerender: true },
          { key: 'doubles', label: 'Doubles', type: 'number', min: 0, width: '90px' },
        ],
        addLabel: 'Add single lesson',
        onAdd: () => state.lessons.push({ id: uid('l'), classId: ftype === 'c' ? fid : '', subjectId: ftype === 's' ? fid : '', teacherId: ftype === 't' ? fid : '', perWeek: 1, doubles: 0 }),
        onDelete: (l) => {
          state.lessons = state.lessons.filter((x) => x !== l);
          changed();
          render();
        },
        emptyText: 'No lessons yet. Use "Add lessons" above.',
      })
    );

    return h('div', null, addForm, listPanel, workloadPanel());
  }

  function workloadPanel() {
    const classes = state.classes.slice().sort(byName);
    const teachers = state.teachers.slice().sort(byName);
    const over = classes.filter((c) => classLoad(c.id) > slotsPerWeek()).length + teachers.filter((t) => teacherLoad(t.id) > teacherCapacity(t)).length;
    return panel(
      'Workload check',
      over ? null : 'Every class and teacher fits in the week.',
      over ? h('div', { class: 'notice bad' }, `${plural(over, 'class or teacher')} has more periods than fit in the week. Fix these before generating.`) : null,
      h(
        'div',
        { class: 'grid-2' },
        h('div', null, h('h3', null, 'Classes'), h('table', { class: 'data' }, h('tbody', null, classes.map((c) => h('tr', null, h('td', null, c.name), h('td', { style: 'text-align:right' }, loadChip(classLoad(c.id), slotsPerWeek() - (c.unavailable || []).length))))))),
        h('div', null, h('h3', null, 'Teachers'), h('table', { class: 'data' }, h('tbody', null, teachers.map((t) => h('tr', null, h('td', null, t.name), h('td', { style: 'text-align:right' }, loadChip(teacherLoad(t.id), teacherCapacity(t))))))))
      )
    );
  }

  /* ---------- timetable ---------- */

  function generate() {
    if (!state.lessons.length) return toast('Add some lessons first (Lessons tab).');
    if (!state.settings.days.length || !state.settings.periods.length) return toast('Set school days and periods first.');
    ui.generating = true;
    ui.stop = false;
    ui.selected = null;
    render();
    const solver = Solver.createSolver(state, { maxIterations: 400000 });
    const t0 = performance.now();
    const tick = () => {
      const st = solver.step(300);
      const bar = $('genBar');
      const label = $('genLabel');
      if (bar) bar.style.width = Math.round((100 * st.bestPlaced) / Math.max(1, st.total)) + '%';
      if (label) label.textContent = `Placed ${st.bestPlaced} of ${st.total} lesson periods… (${Math.round((performance.now() - t0) / 1000)}s)`;
      if (!st.done && !ui.stop && performance.now() - t0 < 90000) return setTimeout(tick, 0);
      const r = solver.result();
      state.timetable = { placements: r.placements, unplaced: r.unplaced, generatedAt: new Date().toISOString(), stale: false };
      ui.generating = false;
      save();
      render();
      toast(r.unplaced.length ? `Done, but ${plural(r.unplaced.length, 'lesson period')} could not be placed.` : 'Timetable ready, with no clashes.');
    };
    setTimeout(tick, 30);
  }

  function belongs(kind, id, pl, L) {
    const lesson = L.lessons.get(pl.lessonId);
    if (!lesson) return false;
    if (kind === 'class') return lesson.classId === id;
    if (kind === 'teacher') return lesson.teacherId === id;
    if (kind === 'room') return pl.roomId === id;
    return false;
  }

  function lessonCard(pl, kind, L, extraClass) {
    const lesson = L.lessons.get(pl.lessonId);
    const subj = L.subjects.get(lesson.subjectId);
    const dept = subj && L.depts.get(subj.deptId);
    const cls = L.classes.get(lesson.classId);
    const teacher = L.teachers.get(lesson.teacherId);
    const room = pl.roomId && L.rooms.get(pl.roomId);
    const lines = [];
    if (kind !== 'class' && cls) lines.push(cls.name);
    if (kind !== 'teacher') lines.push(teacher ? teacher.name : 'No teacher');
    if (kind !== 'room' && room) lines.push(room.name);
    return h(
      'div',
      { class: 'lesson ' + (extraClass || ''), style: `--c:${dept ? dept.color : '#888'}`, title: [subj ? subj.name : '?', cls && cls.name, teacher && teacher.name, room && room.name].filter(Boolean).join(' · ') },
      h('b', null, subj ? subj.name : '?'),
      lines.map((x) => h('div', { class: 'sub' }, x))
    );
  }

  function periodHeader(p, i) {
    return h('th', null, p.label || i + 1, p.start ? h('span', { class: 'time' }, `${p.start}–${p.end}`) : null);
  }

  function gridFor(kind, ent, L) {
    const { days, periods } = state.settings;
    const P = periods.length;
    const items = state.timetable.placements.map((pl, i) => ({ pl, i })).filter((x) => belongs(kind, ent.id, x.pl, L));
    const cells = new Map();
    items.forEach((x) => {
      for (let k = 0; k < x.pl.length; k++) {
        const key = x.pl.day + '|' + (x.pl.period + k);
        if (!cells.has(key)) cells.set(key, []);
        cells.get(key).push(x);
      }
    });
    const interactive = kind !== 'dept' && !ui.generating;
    const selectedPl = ui.selected != null ? state.timetable.placements[ui.selected] : null;

    const rows = days.map((day) => {
      const tds = [];
      for (let p = 0; p < P; p++) {
        const here = cells.get(day + '|' + p) || [];
        if (!here.length) {
          tds.push(h('td', { class: 'free' + (selectedPl ? ' target' : ''), onclick: interactive ? () => onCell(day, p, null) : null }));
          continue;
        }
        let span = 1;
        if (here.length === 1 && here[0].pl.period === p) {
          while (span < here[0].pl.length && p + span < P) {
            const next = cells.get(day + '|' + (p + span)) || [];
            if (next.length !== 1 || next[0] !== here[0]) break;
            span++;
          }
        }
        const clash = here.length > 1;
        tds.push(
          h(
            'td',
            { colspan: span > 1 ? span : null, onclick: interactive ? () => onCell(day, p, here[0].i) : null },
            here.map((x) => lessonCard(x.pl, kind, L, (clash ? 'clash ' : '') + (x.i === ui.selected ? 'selected' : '')))
          )
        );
        p += span - 1;
      }
      return h('tr', null, h('th', null, day), tds);
    });

    const count = items.reduce((s, x) => s + x.pl.length, 0);
    const label = kind === 'class' ? `Class ${ent.name}` : kind === 'teacher' ? ent.name : `Room ${ent.name}`;
    const extra = kind === 'teacher' && L.depts.get(ent.deptId) ? ' · ' + L.depts.get(ent.deptId).name : kind === 'class' && ent.grade ? ' · ' + ent.grade : '';
    return h(
      'div',
      { class: 'tt-page' },
      h('div', { class: 'tt-title' }, h('h3', null, label, h('span', { class: 'muted', style: 'font-weight:400;font-size:13px' }, extra)), h('span', { class: 'muted small' }, `${state.settings.schoolName} · ${plural(count, 'period')}/week`)),
      h('table', { class: 'tt' + (P > 8 ? ' compact' : '') }, h('thead', null, h('tr', null, h('th', { style: 'width:92px' }), periods.map(periodHeader))), h('tbody', null, rows))
    );
  }

  function deptGrid(dept, L) {
    const { days, periods } = state.settings;
    const teachers = state.teachers.filter((t) => (dept ? t.deptId === dept.id : !L.depts.has(t.deptId))).sort(byName);
    const cell = new Map();
    state.timetable.placements.forEach((pl) => {
      const lesson = L.lessons.get(pl.lessonId);
      if (!lesson) return;
      for (let k = 0; k < pl.length; k++) {
        const key = lesson.teacherId + '|' + pl.day + '|' + (pl.period + k);
        if (!cell.has(key)) cell.set(key, []);
        cell.get(key).push(pl);
      }
    });
    const short = (pl) => {
      const lesson = L.lessons.get(pl.lessonId);
      const subj = L.subjects.get(lesson.subjectId);
      const cls = L.classes.get(lesson.classId);
      const d = subj && L.depts.get(subj.deptId);
      return h('div', { class: 'lesson' + '', style: `--c:${d ? d.color : '#888'}`, title: `${subj ? subj.name : ''} · ${cls ? cls.name : ''}` }, h('b', null, cls ? cls.name : '?'), h('div', { class: 'sub' }, subj ? subj.short || subj.name.slice(0, 4) : ''));
    };
    return h(
      'div',
      { class: 'tt-page' },
      h('div', { class: 'tt-title' }, h('h3', null, dept ? dept.name + ' department' : 'Teachers without a department'), h('span', { class: 'muted small' }, state.settings.schoolName)),
      teachers.length
        ? h(
            'div',
            { class: 'table-wrap' },
            h(
              'table',
              { class: 'tt dept', style: `min-width:${130 + days.length * periods.length * 30}px` },
              h(
                'thead',
                null,
                h('tr', null, h('th', { style: 'width:130px' }), days.map((d) => h('th', { colspan: periods.length, class: 'daystart' }, d))),
                h('tr', null, h('th'), days.map(() => periods.map((p, i) => h('th', { class: i === 0 ? 'daystart' : '' }, p.label || i + 1))))
              ),
              h(
                'tbody',
                null,
                teachers.map((t) =>
                  h(
                    'tr',
                    null,
                    h('th', null, t.name, h('div', { class: 'muted', style: 'font-weight:400;font-size:10px' }, `${teacherLoad(t.id)} periods`)),
                    days.map((d) =>
                      periods.map((p, i) => {
                        const list = cell.get(t.id + '|' + d + '|' + i) || [];
                        return h('td', { class: i === 0 ? 'daystart' : '' }, list.map(short));
                      })
                    )
                  )
                )
              )
            )
          )
        : h('div', { class: 'empty' }, 'No teachers in this department.')
    );
  }

  function onCell(day, p, idx) {
    const tt = state.timetable;
    if (ui.selected == null) {
      if (idx != null) {
        ui.selected = idx;
        render();
        toast('Now click the slot where this lesson should go. Press Esc to cancel.');
      }
      return;
    }
    if (idx === ui.selected) {
      ui.selected = null;
      render();
      return;
    }
    const next = tt.placements.map((x) => Object.assign({}, x));
    const A = next[ui.selected];
    if (idx != null) {
      const B = next[idx];
      if (A.length !== B.length) return toast('Only lessons of the same length can be swapped.');
      [A.day, B.day] = [B.day, A.day];
      [A.period, B.period] = [B.period, A.period];
    } else {
      if (p + A.length > state.settings.periods.length) return toast('A double period does not fit there.');
      A.day = day;
      A.period = p;
    }
    const before = Solver.validate(state, tt.placements).conflicts.length;
    const res = Solver.validate(state, next);
    if (res.conflicts.length > before) {
      const msg = res.conflicts.slice(0, 6).join('\n• ');
      if (!confirm(`This move creates a clash:\n\n• ${msg}\n\nMove it anyway?`)) return;
    }
    tt.placements = next;
    ui.selected = null;
    save();
    render();
    toast(idx != null ? 'Lessons swapped.' : 'Lesson moved.');
  }

  function exportCsv() {
    const L = lookups();
    const { days, periods } = state.settings;
    const rows = [];
    state.timetable.placements.forEach((pl) => {
      const lesson = L.lessons.get(pl.lessonId);
      if (!lesson) return;
      const subj = L.subjects.get(lesson.subjectId);
      const cls = L.classes.get(lesson.classId);
      const t = L.teachers.get(lesson.teacherId);
      const room = pl.roomId && L.rooms.get(pl.roomId);
      const dept = subj && L.depts.get(subj.deptId);
      for (let k = 0; k < pl.length; k++) {
        const p = periods[pl.period + k] || {};
        rows.push({
          sort: [cls ? cls.name : '', days.indexOf(pl.day), pl.period + k],
          cols: [pl.day, p.label || pl.period + k + 1, p.start || '', p.end || '', cls ? cls.name : '', cls ? cls.grade || '' : '', subj ? subj.name : '', dept ? dept.name : '', t ? t.name : '', room ? room.name : ''],
        });
      }
    });
    rows.sort((a, b) => a.sort[0].localeCompare(b.sort[0], undefined, { numeric: true }) || a.sort[1] - b.sort[1] || a.sort[2] - b.sort[2]);
    const esc = (v) => (/[",\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : String(v));
    const header = ['Day', 'Period', 'Start', 'End', 'Class', 'Grade', 'Subject', 'Department', 'Teacher', 'Room'];
    const csv = [header].concat(rows.map((r) => r.cols)).map((r) => r.map(esc).join(',')).join('\r\n');
    download(fileBase() + '-timetable.csv', '﻿' + csv, 'text/csv;charset=utf-8');
  }

  function fileBase() {
    return (state.settings.schoolName || 'school').replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, '').toLowerCase() || 'school';
  }

  function freeTeachersPanel(L) {
    const { days, periods } = state.settings;
    const f = ui.free;
    if (!days.includes(f.day)) f.day = days[0];
    if (f.period >= periods.length) f.period = 0;
    const busy = new Set();
    state.timetable.placements.forEach((pl) => {
      if (pl.day === f.day && f.period >= pl.period && f.period < pl.period + pl.length) {
        const lesson = L.lessons.get(pl.lessonId);
        if (lesson) busy.add(lesson.teacherId);
      }
    });
    const free = state.teachers
      .filter((t) => !busy.has(t.id) && !(t.unavailable || []).includes(f.day + '|' + f.period))
      .sort((a, b) => teacherLoad(a.id) - teacherLoad(b.id) || byName(a, b));
    return h(
      'details',
      { class: 'panel no-print' },
      h('summary', { style: 'cursor:pointer;font-weight:600' }, 'Who is free? (find cover for an absent teacher)'),
      h(
        'div',
        { class: 'row', style: 'margin:12px 0' },
        h('select', { value: f.day, onchange: (e) => ((f.day = e.target.value), render()) }, days.map((d) => h('option', { value: d }, d))),
        h('select', { value: String(f.period), onchange: (e) => ((f.period = Number(e.target.value)), render()) }, periods.map((p, i) => h('option', { value: String(i) }, `Period ${p.label || i + 1}${p.start ? ' (' + p.start + ')' : ''}`)))
      ),
      free.length
        ? h('div', { class: 'row' }, free.map((t) => h('span', { class: 'chip', title: `${teacherLoad(t.id)} periods per week` }, t.name + (L.depts.get(t.deptId) ? ` · ${L.depts.get(t.deptId).name}` : ''))))
        : h('div', { class: 'muted' }, 'No teacher is free then.'),
      h('p', { class: 'muted small' }, 'Teachers with the lightest weekly load are listed first.')
    );
  }

  function renderTimetable() {
    const L = lookups();
    const tt = state.timetable;
    const warnings = Solver.diagnose(state);

    const genPanel = panel(
      'Timetable',
      'The generator places every lesson so that no teacher, class or room is double-booked. It respects availability and daily limits, spreads each subject across the week, and keeps gaps to a minimum. Each run can give a different valid timetable.',
      warnings.length ? h('div', { class: 'notice warn' }, h('b', null, 'Check these first:'), h('ul', null, warnings.slice(0, 15).map((w) => h('li', null, w))), warnings.length > 15 ? h('div', null, `…and ${warnings.length - 15} more`) : null) : null,
      ui.generating
        ? h('div', null, h('div', { class: 'progress' }, h('div', { id: 'genBar' })), h('div', { class: 'row' }, h('span', { id: 'genLabel', class: 'muted' }, 'Starting…'), h('button', { class: 'btn', onclick: () => (ui.stop = true) }, 'Stop and keep best')))
        : h(
            'div',
            { class: 'row' },
            h('button', { class: 'btn primary big', onclick: generate }, tt ? '↻ Generate again' : '▶ Generate timetable'),
            tt ? h('span', { class: 'muted' }, 'Last generated ' + new Date(tt.generatedAt).toLocaleString()) : null
          )
    );

    if (!tt) {
      return h('div', null, genPanel, state.lessons.length ? null : h('div', { class: 'notice info' }, 'Tip: click "Load example school" at the top to see how everything works with sample data.'));
    }

    const check = Solver.validate(state, tt.placements);
    const status = h(
      'div',
      { class: 'no-print' },
      tt.stale ? h('div', { class: 'notice info' }, 'You have changed the school data since this timetable was made. Generate again to include the changes.') : null,
      check.conflicts.length
        ? h('div', { class: 'notice bad' }, h('b', null, check.conflicts.length + (check.conflicts.length === 1 ? ' clash:' : ' clashes:')), h('ul', null, check.conflicts.slice(0, 20).map((c) => h('li', null, c))))
        : null,
      check.missing.length
        ? h('div', { class: 'notice warn' }, h('b', null, 'Not scheduled:'), h('ul', null, check.missing.slice(0, 20).map((c) => h('li', null, c))), h('div', { class: 'small' }, 'Usually a teacher has too many periods, too little availability, or a special room is overbooked. Check the warnings above and the Workload check in the Lessons tab, then generate again.'))
        : null,
      !check.conflicts.length && !check.missing.length ? h('div', { class: 'notice ok' }, `✓ All ${plural(tt.placements.reduce((s, p) => s + p.length, 0), 'lesson period')} are scheduled with no clashes.`) : null
    );

    // view controls
    const lists = {
      class: state.classes.slice().sort(byName),
      teacher: state.teachers.slice().sort(byName),
      room: state.rooms.slice().sort(byName),
      dept: state.departments.slice().sort(byName),
    };
    const list = lists[ui.view];
    if (ui.entity !== '*' && !list.some((x) => x.id === ui.entity)) ui.entity = list[0] ? list[0].id : '';
    const controls = h(
      'div',
      { class: 'panel no-print' },
      h(
        'div',
        { class: 'row' },
        h('span', { class: 'muted' }, 'View by'),
        ['class', 'teacher', 'dept', 'room'].map((v) =>
          h('button', { class: 'btn' + (ui.view === v ? ' primary' : ''), onclick: () => ((ui.view = v), (ui.entity = ''), (ui.selected = null), render()) }, { class: 'Class', teacher: 'Teacher', dept: 'Department', room: 'Room' }[v])
        ),
        h(
          'select',
          { value: ui.entity, onchange: (e) => ((ui.entity = e.target.value), (ui.selected = null), render()) },
          list.map((x) => h('option', { value: x.id }, x.name || '(unnamed)')),
          list.length ? h('option', { value: '*' }, `— All ${list.length} (for printing) —`) : null
        ),
        h('span', { style: 'flex:1' }),
        h('button', { class: 'btn', onclick: () => window.print() }, '🖨 Print'),
        h('button', { class: 'btn', onclick: exportCsv }, '⬇ Export CSV (Excel)')
      ),
      ui.view !== 'dept' ? h('p', { class: 'muted small', style: 'margin:10px 0 0' }, 'To adjust by hand: click a lesson, then click an empty slot to move it there or another lesson to swap them. You are warned if the change causes a clash.') : null
    );

    let grids;
    const shown = ui.entity === '*' ? list : list.filter((x) => x.id === ui.entity);
    if (!list.length) grids = h('div', { class: 'empty' }, ui.view === 'room' ? 'No special rooms defined.' : 'Nothing to show.');
    else if (ui.view === 'dept') {
      grids = shown.map((d) => deptGrid(d, L));
      if (ui.entity === '*' && state.teachers.some((t) => !L.depts.has(t.deptId))) grids.push(deptGrid(null, L));
    } else grids = shown.map((x) => gridFor(ui.view, x, L));

    const legend = h('div', { class: 'legend no-print' }, state.departments.map((d) => h('span', null, h('span', { class: 'dot', style: `background:${d.color}` }), d.name)));

    return h('div', null, genPanel, status, controls, h('div', { class: 'panel' }, grids, legend), freeTeachersPanel(L));
  }

  /* ---------- shell ---------- */

  const RENDER = {
    school: renderSchool,
    departments: renderDepartments,
    teachers: renderTeachers,
    subjects: renderSubjects,
    classes: renderClasses,
    rooms: renderRooms,
    lessons: renderLessons,
    timetable: renderTimetable,
  };

  function tabCount(id) {
    const n = { departments: state.departments.length, teachers: state.teachers.length, subjects: state.subjects.length, classes: state.classes.length, rooms: state.rooms.length, lessons: state.lessons.length }[id];
    return n ? ` (${n})` : '';
  }

  function render() {
    const scroll = window.scrollY;
    $('schoolNameLabel').textContent = state.settings.schoolName || '';
    document.title = (state.settings.schoolName ? state.settings.schoolName + ' · ' : '') + 'Timetable Builder';
    const tabs = $('tabs');
    tabs.innerHTML = '';
    TABS.forEach((t, i) =>
      tabs.append(
        h('button', { class: 'tab' + (ui.tab === t.id ? ' active' : ''), role: 'tab', onclick: () => ((ui.tab = t.id), (ui.selected = null), render(), window.scrollTo(0, 0)) }, h('span', { class: 'num' }, i + 1), t.label + tabCount(t.id))
      )
    );
    const main = $('main');
    main.innerHTML = '';
    main.append(RENDER[ui.tab]());
    window.scrollTo(0, scroll);
  }

  /* ---------- top bar actions ---------- */

  const hasData = () => state.teachers.length || state.classes.length || state.lessons.length;

  $('btnSample').onclick = () => {
    if (hasData() && !confirm('Replace your current data with the example school? Use "Save to file" first if you want to keep it.')) return;
    state = migrate(window.TimetableSample.sampleSchool());
    ui.tab = 'timetable';
    ui.entity = '';
    save();
    render();
    toast('Example school loaded. Click "Generate timetable".');
  };
  $('btnExport').onclick = () => {
    download(fileBase() + '-timetable-data.json', JSON.stringify(state, null, 2), 'application/json');
    toast('Saved. Keep this file as your backup.');
  };
  $('fileImport').onchange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    file.text().then((text) => {
      try {
        const data = JSON.parse(text);
        if (!data || !data.settings || !Array.isArray(data.lessons)) throw new Error('bad file');
        state = migrate(data);
        ui.entity = '';
        save();
        render();
        toast('File opened.');
      } catch (err) {
        alert('This file is not a timetable file saved by this app.');
      }
      e.target.value = '';
    });
  };
  $('btnReset').onclick = () => {
    if (!confirm('Delete all data and start over? This cannot be undone (unless you saved a file).')) return;
    state = emptyState();
    ui.tab = 'school';
    save();
    render();
  };
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && ui.selected != null) {
      ui.selected = null;
      render();
    }
  });

  render();
})();

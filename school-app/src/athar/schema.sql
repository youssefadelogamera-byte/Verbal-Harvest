-- Athar storage. One SQLite file. The knowledge graph is these tables plus the
-- curriculum pack (concept nodes and prerequisite edges) loaded from packs/<id>/pack.yaml.
-- Node types: learner, teacher, concept, skill, evidence, finding.
-- `alias` is the handle used everywhere a record is written, read by the agent or sent to a model.
-- `display_name` is shown to teachers only. In the synthetic data it is an invented first name and an
-- initial. The MCP tools never return it, so no model and no MCP client ever sees a name.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS learners (
  id            TEXT PRIMARY KEY,            -- lrn_xxxx
  alias         TEXT NOT NULL,               -- e.g. "Learner A-17", never a legal name
  display_name  TEXT,                        -- shown in the teacher app only; never leaves through a tool
  pack_id       TEXT NOT NULL,               -- curriculum pack the learner follows
  start_year    INTEGER NOT NULL,            -- calendar year of first record
  start_grade   INTEGER NOT NULL,
  home_language TEXT NOT NULL DEFAULT 'en',  -- language for guardian-facing text
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS teachers (
  id         TEXT PRIMARY KEY,               -- tch_xxxx
  name       TEXT NOT NULL,                  -- teachers are named: they approve things
  subjects   TEXT NOT NULL DEFAULT '[]'      -- JSON list
);

-- A teacher's own description of how they teach. Never a score.
CREATE TABLE IF NOT EXISTS teacher_profiles (
  teacher_id TEXT PRIMARY KEY REFERENCES teachers(id),
  answers    TEXT NOT NULL,                 -- JSON: the teacher's own answers
  updated_at TEXT NOT NULL
);

-- Teacher data points: what was taught, when, and with which approach.
CREATE TABLE IF NOT EXISTS teaching_units (
  id          TEXT PRIMARY KEY,              -- unt_xxxx
  teacher_id  TEXT NOT NULL REFERENCES teachers(id),
  year        INTEGER NOT NULL,
  term        INTEGER NOT NULL CHECK (term BETWEEN 1 AND 3),
  grade       INTEGER NOT NULL,
  concept_id  TEXT NOT NULL,                 -- concept id in the pack
  approach_id TEXT NOT NULL,                 -- approach id in the pack
  note        TEXT
);

-- Learner data points. Every later claim must cite rows from here.
CREATE TABLE IF NOT EXISTS evidence (
  id          TEXT PRIMARY KEY,              -- evd_xxxx
  learner_id  TEXT NOT NULL REFERENCES learners(id),
  kind        TEXT NOT NULL CHECK (kind IN ('quiz_item','assignment','project','observation','attendance')),
  year        INTEGER NOT NULL,
  term        INTEGER NOT NULL CHECK (term BETWEEN 1 AND 3),
  period_ord  INTEGER NOT NULL,              -- year*3 + (term-1); sortable across years
  grade       INTEGER NOT NULL,
  concept_id  TEXT,                          -- NULL for attendance or untagged observations
  skill_id    TEXT,                          -- cross-subject skill id in the pack, optional
  score       REAL,                          -- 0..1, NULL when not a scored item
  absent_days INTEGER,                       -- for kind = attendance
  raw_text    TEXT,                          -- teacher's words or the item text, any language
  language    TEXT NOT NULL DEFAULT 'en',
  source_ref  TEXT NOT NULL,                 -- where it came from: "quiz:2023-T2-maths-03#item4", a file name, a note id
  teacher_id  TEXT REFERENCES teachers(id),
  unit_id     TEXT REFERENCES teaching_units(id),
  recorded_at TEXT NOT NULL,
  logged_late INTEGER NOT NULL DEFAULT 0,
  status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','needs_review','retracted'))
);
CREATE INDEX IF NOT EXISTS idx_evidence_learner ON evidence(learner_id, period_ord);
CREATE INDEX IF NOT EXISTS idx_evidence_concept ON evidence(learner_id, concept_id);

-- A finding is a proposal. It is never a label and never visible outside the teacher view
-- until a named teacher approves it.
CREATE TABLE IF NOT EXISTS findings (
  id           TEXT PRIMARY KEY,             -- fnd_xxxx
  learner_id   TEXT NOT NULL REFERENCES learners(id),
  kind         TEXT NOT NULL CHECK (kind IN ('root_cause','strength','struggle','what_worked')),
  statement    TEXT NOT NULL,                -- plain words, describes a pattern not a person
  concept_ids  TEXT NOT NULL DEFAULT '[]',   -- JSON list
  evidence_ids TEXT NOT NULL,                -- JSON list, must be non-empty
  path         TEXT NOT NULL DEFAULT '[]',   -- JSON list of concept ids walked (root_cause)
  confidence   REAL NOT NULL,
  status       TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','approved','edited','rejected')),
  proposed_by  TEXT NOT NULL,                -- agent run id or tool caller
  proposed_at  TEXT NOT NULL,
  decided_by   TEXT REFERENCES teachers(id),
  decided_at   TEXT,
  teacher_note TEXT
);

-- Plain-language text built only from approved findings. A second gate guards sharing.
CREATE TABLE IF NOT EXISTS summaries (
  id          TEXT PRIMARY KEY,              -- sum_xxxx
  learner_id  TEXT NOT NULL REFERENCES learners(id),
  audience    TEXT NOT NULL CHECK (audience IN ('teacher_handover','guardian')),
  language    TEXT NOT NULL,
  text        TEXT NOT NULL,
  finding_ids TEXT NOT NULL,                 -- JSON list, all must be approved or edited
  status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','rejected')),
  created_by  TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  decided_by  TEXT REFERENCES teachers(id),
  decided_at  TEXT
);

-- Every tool call, by anyone. Inputs, outputs, timestamps.
CREATE TABLE IF NOT EXISTS audit_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          TEXT NOT NULL,
  run_id      TEXT,                          -- agent run, when there is one
  actor       TEXT NOT NULL,                 -- 'agent', 'teacher:<id>', 'mcp-client', 'system'
  tool        TEXT NOT NULL,
  input       TEXT NOT NULL,                 -- JSON
  output      TEXT NOT NULL,                 -- JSON (truncated to 4000 chars)
  ok          INTEGER NOT NULL,
  duration_ms INTEGER NOT NULL
);

-- Every human decision, with the named teacher.
CREATE TABLE IF NOT EXISTS approvals (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  ts           TEXT NOT NULL,
  target_type  TEXT NOT NULL CHECK (target_type IN ('finding','summary')),
  target_id    TEXT NOT NULL,
  decision     TEXT NOT NULL CHECK (decision IN ('approved','edited','rejected')),
  teacher_id   TEXT NOT NULL REFERENCES teachers(id),
  teacher_name TEXT NOT NULL,
  note         TEXT
);

-- A question from the agent to a teacher: "the record has a hole here, do you have anything?"
-- Only a named teacher can answer it, with a record or by saying none exists.
CREATE TABLE IF NOT EXISTS record_requests (
  id               TEXT PRIMARY KEY,         -- req_xxxx
  learner_id       TEXT NOT NULL REFERENCES learners(id),
  concept_id       TEXT NOT NULL,            -- the topic with no records
  about_concept_id TEXT,                     -- the struggle whose trace stopped at the hole
  question         TEXT NOT NULL,            -- plain words, checked by the guard
  status           TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','provided','no_record')),
  asked_by         TEXT NOT NULL,            -- agent run id or tool caller
  asked_at         TEXT NOT NULL,
  answered_by      TEXT REFERENCES teachers(id),
  answered_at      TEXT,
  answer_text      TEXT,                     -- what the teacher typed, in any language
  answer_file      TEXT,                     -- or the name of a file in the inbox
  answer_year      INTEGER,
  answer_term      INTEGER CHECK (answer_term BETWEEN 1 AND 3)
);
CREATE INDEX IF NOT EXISTS idx_requests_learner ON record_requests(learner_id, status);

-- Sign-in for the teacher app. An account belongs to a named teacher. The password is never stored:
-- only a salted scrypt hash. While this table is empty the app runs in demonstration mode, where a
-- teacher is picked from a list (synthetic data only).
CREATE TABLE IF NOT EXISTS accounts (
  teacher_id    TEXT PRIMARY KEY REFERENCES teachers(id),
  username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,                -- scrypt, salted
  role          TEXT NOT NULL CHECK (role IN ('admin','teacher')),
  created_at    TEXT NOT NULL
);

-- One row per signed-in browser. Only a hash of the cookie value is stored.
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  teacher_id TEXT NOT NULL REFERENCES teachers(id),
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

-- A class is a group of learners in one school year. Once sign-in is on, a teacher sees the learners
-- of the classes they take and nobody else. The admin sees everyone.
CREATE TABLE IF NOT EXISTS classes (
  id         TEXT PRIMARY KEY,                -- cls_xxxx
  name       TEXT NOT NULL,                   -- "5A"
  grade      INTEGER NOT NULL,
  year       INTEGER NOT NULL,                -- the calendar year the school year starts in
  created_at TEXT NOT NULL,
  UNIQUE (name, year)
);

CREATE TABLE IF NOT EXISTS class_learners (
  class_id   TEXT NOT NULL REFERENCES classes(id),
  learner_id TEXT NOT NULL REFERENCES learners(id),
  PRIMARY KEY (class_id, learner_id)
);

CREATE TABLE IF NOT EXISTS class_teachers (
  class_id   TEXT NOT NULL REFERENCES classes(id),
  teacher_id TEXT NOT NULL REFERENCES teachers(id),
  subject    TEXT NOT NULL DEFAULT 'all',     -- subject id in the pack, or 'all'
  PRIMARY KEY (class_id, teacher_id, subject)
);

-- A few facts about this installation, such as who uses it: a school, or a family.
CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Topics a school adds to the installed curriculum: more grades, or another subject. A row starts as a
-- draft (typed in, or read from a contents page by the model), a named teacher checks every topic and
-- every link, and only an approved row is laid over the pack. The agent has no tool that touches this table.
CREATE TABLE IF NOT EXISTS curriculum_additions (
  id          TEXT PRIMARY KEY,              -- cur_xxxx
  pack_id     TEXT NOT NULL,                 -- the installed pack it adds to
  title       TEXT NOT NULL,
  status      TEXT NOT NULL CHECK (status IN ('draft','approved','discarded','withdrawn')),
  data        TEXT NOT NULL,                 -- JSON: the draft as the teacher sees and edits it
  approved    TEXT,                          -- JSON: subject, areas, topics and links exactly as approved
  read_by     TEXT NOT NULL,                 -- 'typed', or 'model:<name>' when a model read the document
  created_by  TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  decided_by  TEXT,                          -- the teacher who approved, discarded or withdrew it
  decided_at  TEXT
);

-- Parent accounts, made by the school admin. A parent is not a teacher: separate table, separate sign-in
-- and separate cookie. A parent sees only the children linked to them, and only what a teacher approved.
CREATE TABLE IF NOT EXISTS parents (
  id            TEXT PRIMARY KEY,               -- par_xxxx
  name          TEXT NOT NULL,
  username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,                  -- scrypt, salted
  created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS parent_learners (
  parent_id  TEXT NOT NULL REFERENCES parents(id) ON DELETE CASCADE,
  learner_id TEXT NOT NULL REFERENCES learners(id),
  PRIMARY KEY (parent_id, learner_id)
);

CREATE TABLE IF NOT EXISTS parent_sessions (
  token_hash TEXT PRIMARY KEY,
  parent_id  TEXT NOT NULL REFERENCES parents(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

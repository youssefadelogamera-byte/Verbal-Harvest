# Athar: notes for Claude Code

Athar follows one learner across years and builds a cited profile for a teacher. This copy is for Learning International Schools (Saudi Arabia): Cambridge, Years 1 to 11.
The Python package is `athar`, the command is `athar`, and every setting starts with `ATHAR_`.

Read this first, then `README.md`, `ARCHITECTURE.md`, `SECURITY.md` and `EVALS.md`. Where the project could go is in
`docs/VISION.md`.

## What this is

Three maps laid over each other:

- **Curriculum map**: topics and what each needs first, loaded from a pack (`packs/cambridge-school/pack.yaml`).
  We graph the school's curriculum. We never change it.
- **Learner map**: evidence rows (quiz items, notes, attendance) attached to topics over time.
- **Teacher map**: what was taught, when, and with which approach.

Who does what:

- The **graph engine** (`graph.py`) reaches the conclusions, in plain code: patterns held over terms,
  tracing a struggle back to where it began, which approaches were followed by improvement.
- The **model** only reads documents, chooses which analyses to run, and words text.
- A **named teacher** approves every finding and every note. Approving is not an MCP tool, so the
  agent cannot approve anything.

## Layout

| Path | What |
|---|---|
| `src/athar/server.py`, `tools.py` | The MCP server: 12 tools, 4 that write |
| `src/athar/graph.py` | The deterministic graph engine |
| `src/athar/guard.py` | Refuses statements that label, rank or track a child |
| `src/athar/review.py` | Teacher decisions (not reachable by the agent) |
| `src/athar/audit.py` | Every tool call is logged |
| `src/athar/agent/workflow.py` | The LangGraph agent: the ask-for-a-record loop and two teacher gates |
| `src/athar/agent/runner.py` | Starts, pauses and resumes runs |
| `src/athar/agent/llm.py` | Model access (any OpenAI-compatible endpoint) |
| `src/athar/explain.py` | Why a finding says what it says: plain facts and chart data, computed from its records |
| `src/athar/report.py` | Printable learner report, built from approved findings only |
| `src/athar/school.py` | Whole-school map by topic (never ranks learners) and its GraphML export |
| `src/athar/accounts.py` | Sign-in: accounts, scrypt password hashes, sessions, admin and teacher roles |
| `src/athar/parents.py` | Parent accounts the school admin makes: own table, sign-in and cookie; a parent sees only linked children and only approved items (`/parent`) |
| `src/athar/classes.py` | Classes. Once sign-in is on, a teacher sees only the learners of their own classes |
| `src/athar/privacy.py` | Backup and restore, one learner's record as a file, deleting one learner, withdrawing a record |
| `src/athar/imports.py` | Marks sheet template and upload, new learner records, documents for the agent |
| `src/athar/family.py` | The family side: the school-or-family choice, a parent's children, results and notes typed at home, and the summary a parent reads (plain code, no model) |
| `src/athar/curriculum_add.py` | Adding grades or a subject to the installed curriculum: a draft (typed, or read from a contents page by the model), plain-code checks, a named teacher's approval, withdrawal. Additions live in the database and `curriculum.py` lays them over the pack; pack files are never rewritten |
| `src/athar/photo.py` | Reading a photo of a marked paper with the local model. Saves nothing; plain code checks the reply; refuses any model that is not on this computer |
| `src/athar/i18n.py` | The Arabic lookup in Python, used by the report |
| `src/athar/web/` | Teacher web app (FastAPI and one HTML file), and the Arabic dictionaries in `static/` |
| `src/athar/synth_school.py` | A synthetic school built from any pack's own graph (`generator: school` in the pack) |
| `src/athar/synth.py` | A smaller synthetic cohort on the generic packs, used by the evaluation set |
| `src/athar/evals.py` | The evaluation set that writes `EVALS.md` |
| `packs/cambridge-*` | Cambridge, Years 1 to 11, one pack per subject (maths, science, English), and `cambridge-school` which joins them. ALL DRAFT, every topic `verified: false` |
| `packs/generic-*` | Small country-neutral packs, used by the evaluation set and as examples |
| `packaging/windows/` | The offline Windows package: `build.py`, `launch.py`, model download, start files |
| `tests/` | About 360 tests, no model needed |

## Commands

```
uv sync --extra dev          # install
uv run athar start           # the school's own, empty records (data/school.db), no made-up data; --lan for the network
uv run athar demo            # seed a made-up school if needed (data/athar.db), open the app at http://127.0.0.1:8765
uv run pytest -q             # tests (no model needed)
uv run ruff check src tests  # lint
uv run athar seed            # rebuild the synthetic Cambridge school, three subjects (wipes everything)
uv run athar seed --pack generic-maths    # the small reference cohort the evaluation set uses
uv run athar story           # findings waiting and decided, no model used
uv run athar family-demo     # a made-up family (parent, three children, three years), no model used
uv run athar learners        # list learners
uv run athar run <code> --file data/inbox/<file>
uv run athar pending         # what is waiting for a teacher
uv run athar answer <request_id> --teacher <id> --text "..."   # answer the agent's question, then `athar resume`
uv run athar report <code>   # printable report, approved findings only (--all for every learner)
uv run athar export-graph    # school graph as GraphML, for Gephi or Neo4j
uv run athar backup          # one file in data/backups
uv run athar eval --skip-model   # engine tasks only (this rewrites the table in EVALS.md)
uv run athar eval --repeats 1    # full evaluation, needs a model
```

## The model

The model is any OpenAI-compatible endpoint. Settings are read from the process environment.
The project does not load a `.env` file, so set them in the shell that runs the command:

```
ATHAR_LLM_BASE_URL   the provider's OpenAI-compatible base URL (ends in /v1). Default: LM Studio on this machine
ATHAR_LLM_API_KEY    the key
ATHAR_LLM_MODEL      the model id as the provider names it
ATHAR_LLM_REASONING  set to "default" for hosted APIs
```

`ATHAR_LLM_REASONING=default` matters: by default the code sends `reasoning_effort: "none"`, which
LM Studio accepts and some hosted APIs reject.

The Agent page can also use OpenAI or Claude for a run. A key is read from `OPENAI_API_KEY` or
`ANTHROPIC_API_KEY`, or typed on the page, where it is kept in memory only. See `SECURITY.md`.
Which models to use, and what was tried, is in `docs/MODELS.md`. Say which model produced any result you report.

## Arabic

- The page (`index.html`) is written in English. In Arabic, `tr()` in the page looks every piece of visible text up in
  `static/ar.json` and `static/ar-server.json` (exact match, then whole-string patterns, then fragments). A
  MutationObserver applies it to everything added to the page, so new English text shows up translated only if it has
  an entry. Add the entry when you add text. Data (a finding, a teacher's words, a name) must be marked `dir="auto"`
  or `lang`, which keeps it out of the dictionary.
- Server side, `curriculum.current_lang` is set per request from the `athar_lang` cookie, and `pack.label(id)` follows
  it. `i18n.tr()` is the same lookup in Python, used by `report.py` with `static/ar-report.json`.
- `ATHAR_LANGUAGE` (default `ar`) decides the language of seeded data and of the agent's findings. Tests set it to
  `en` in `tests/conftest.py`; `athar eval` forces `en`.
- Wording rules and fixed terms are in `docs/arabic-glossary.md`. Follow them.

## Rules that must not be broken

1. **Never commit a key.** No `.env` file, no key in code, docs, tests or commit messages.
2. **Synthetic data only in the repository.** No real learner data in code, tests, issues or screenshots. A learner's
   record code is the alias (A-17). No tool result and no model prompt ever carries a name.
3. **The agent never labels a child or assigns a track.** Do not weaken `guard.py` or the two teacher gates.
4. **No unsourced claim.** Every finding cites evidence ids, and those ids come from the tools, never from the model.
5. **Every tool call is logged.** New tools must use `@audited`.
6. **Report results as they are.** Do not edit the generated table in `EVALS.md` by hand. If something fails, write it down.
7. **Keep the one-command run working.** `uv run athar demo` must work on a fresh clone.

## School side and family side

- `settings.mode` is unset on a fresh database: the page then asks who is using it (`showChooser` in `index.html`).
- In family mode the page swaps `NAV` for `NAV_FAMILY` and the server limits every learner list to the family's group
  (`family.children_ids()` through `_only` and `_check_learner` in `web/app.py`). There is no sign-in on that side.
- A new family screen needs its text in `static/ar.json`. Put each literal piece in its own text node so it can be
  looked up whole.

## Things that bite

- A label in a pack with a comma must be in quotes (`{en: "Ratio, proportion and percent"}`). The loader refuses
  a cut label.
- Concept and strand ids must be unique across the packs that `cambridge-school` includes. Each subject uses a prefix
  with the year: `m4-` maths, `s4-` science, `e4-` English.
- A topic may only need topics taught earlier (an earlier grade, or the same grade no later in the year). A test
  checks every Cambridge pack.
- A new route that returns learner data must filter with `_mine(request, ...)` or check with `classes.check`.
  Routes under `/api/learners/{id}/` are checked by the middleware.
- `data/backups/` and `exports/` hold names. They are ignored by git. Keep it that way.
- Seeding wipes everything, accounts and classes included. No account is ever seeded.

## Working here

- Work on a branch and open a pull request. Do not push to `main`.
- Before every commit: `uv run pytest -q` and `uv run ruff check src tests` must both pass. CI runs both on
  every push and pull request (`.github/workflows/ci.yml`).
- `athar seed` rewrites the tracked files in `data/`. Restore them with `git checkout -- data/` before committing,
  unless the change is meant.
- `SECURITY.md` lists what the code enforces. If you change one of those rules, change the page and its test.
- Add a test with every fix.
- Docs are written in plain English with no em dashes or en dashes.
- Known weak spots are listed in `README.md` and at the end of `EVALS.md`. Start there.

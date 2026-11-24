# Security and data protection

Athar is a prototype. It is built to run on one machine inside a school, on synthetic data. This page
says what the code enforces today, what it does not, and how to report a problem.

## What the code enforces

| Rule | Where | Checked by |
|---|---|---|
| The agent cannot approve a finding or a note, or answer its own question. Those functions are not MCP tools. | `review.py`, `server.py` | `tests/test_server.py` |
| The agent cannot add to the curriculum or approve an addition: there is no MCP tool for it. An addition is used only after a named teacher approves it, and on the family side nobody can add one. | `curriculum_add.py`, `web/app.py` | `tests/test_curriculum_add.py` |
| Every tool call is written to the audit log, including refused ones, with who called it. | `audit.py` | `tests/test_tools.py` |
| A finding must cite evidence that exists and belongs to that learner. | `tools.py` | `tests/test_tools.py` |
| A statement that labels, ranks or tracks a child is refused, for the agent and for a teacher's edit. | `guard.py` | `tests/test_guard.py` |
| A document that names another learner is never recorded on this one. | `agent/workflow.py` | `tests/test_agent_units.py` |
| Instructions inside a document are treated as data. | `agent/prompts.py` | evaluation task A9 |
| A file is opened only by name from the inbox folder. A path from the page is never followed. | `web/app.py` | `tests/test_web.py` |
| All SQL uses bound parameters. Table and column names never come from a request. | `db.py`, `tools.py` | code review |
| The school map and the export never carry a learner's scores, and never rank learners. | `school.py` | `tests/test_report_and_school.py` |
| The teacher app and the MCP HTTP server listen on `127.0.0.1` unless you change it. | `config.py`, `server.py` | |
| The page loads no script, font or style from another site. | `web/static/index.html` | `tests/test_web.py` |
| No key is stored in the repository. Settings come from the environment. | `.gitignore`, `config.py` | |
| A cloud model key typed in the teacher app is kept in memory until the app stops. It is never written to the database, the audit log, a run record or a file, no endpoint returns it, and it is removed from any error text. | `agent/llm.py`, `web/app.py` | `tests/test_cloud_models.py` |
| A learner's name is shown to teachers only. No MCP tool returns it and no model prompt contains it: tools and models see the record code. | `tools.py`, `agent/workflow.py` | `tests/test_school_seed.py` |
| The explanation shown with a finding is computed from the records it cites, never written by a model. | `explain.py` | `tests/test_explain.py` |
| Once sign-in is on, a teacher is served only the learners of their own classes: lists are filtered, a learner outside them is refused (403) on every learner page, and so is a decision, an agent run or a marks sheet about one. The admin sees everyone. | `classes.py`, `web/app.py` | `tests/test_classes_privacy.py` |
| Only the school admin makes classes, adds teachers, makes a backup, saves one learner's record as a file, or deletes a learner. None of these is an MCP tool, so the agent cannot do them. | `web/app.py`, `privacy.py` | `tests/test_classes_privacy.py` |
| Deleting a learner needs their record code typed again. It removes the learner, every record, finding, note, question and decision about them, the agent runs about them and inbox files named with their code, and blanks the audit rows that mention them. One new audit row says a record was deleted, without a name. | `privacy.py` | `tests/test_classes_privacy.py` |
| A backup is downloaded by file name only, from the backups folder. | `web/app.py` | `tests/test_classes_privacy.py` |
| On the family side only the family's own children are served: every list is filtered, and any other learner is refused (403) on every learner page, for agent runs and for notes. Switching sides deletes nothing, and a child a parent added is never listed or served on the school side, with or without sign-in. A family's papers are kept in their own folder. Once a school has sign-in, only its admin can switch. | `family.py`, `web/app.py` | `tests/test_family.py` |
| A photo of a paper is read only by a model on this computer (`localhost`). If the model is anywhere else, reading is refused, because a paper usually shows the child's name. The photo is not stored and not logged, and nothing read from it is saved until the parent confirms the lines. | `photo.py`, `web/app.py` | `tests/test_photo.py` |
| A parent's note is stored as written and never becomes a score. The audit log records that a note was added, not its words. | `family.py` | `tests/test_family.py` |
| A label in a curriculum pack that was cut at an unquoted comma is refused when the pack loads. | `curriculum.py` | `tests/test_synth_school.py` |

## What it does not do yet

These are known gaps. Do not use Athar with real learners until they are closed.

- **Sign-in is off until a school admin exists.** With made-up data a teacher is chosen from a list, so anyone at
  the machine can approve as any teacher. Create the school admin on the School page before anything else. From
  then on every page of data needs a username and password, a decision is recorded under the signed-in teacher
  whatever the page sends, and only the admin adds teachers (`accounts.py`, `tests/test_accounts_upload.py`).
  Passwords are stored as salted scrypt hashes and are never logged. A session cookie is HttpOnly and
  SameSite=Strict, and only its hash is stored. There is no password reset by email: the admin resets it.
- **HTTPS is off unless you give it a certificate.** By default sign-in travels in the clear, which is only safe
  on `127.0.0.1`. To serve other machines, set `ATHAR_TLS_CERT` and `ATHAR_TLS_KEY` to a certificate and its key:
  the app then serves HTTPS and marks the session cookie Secure. The app does not make a certificate for you, and
  this path has not been tested on a school network.
- **No encryption at rest.** The database is one SQLite file. Protect the machine and its disk.
- **Two roles only, and a class opens the whole record.** A teacher who has a learner in a class sees that
  learner's records in every subject and every year. That is on purpose (a difficulty in one subject often starts
  in another), but it is wider than "my subject only". Files in the inbox are shared by all signed-in teachers,
  and the school map shows topic totals for the learners a teacher can see, which is a small group.
- **A photo is seen by the local model as it is.** The model is told to leave names out of its reply, and plain code keeps only marks, topics and the printed headings. But the heading text it copies is shown on the page and saved with the result if the parent keeps it, so a name printed inside a heading would be saved too.
- **The family side has no password.** It is meant for a home computer. Anyone who can use that computer can open the records, switch sides, make a backup or delete a child's record. Use the computer's own user accounts if that matters.
- **In demonstration mode there are no limits.** Until an admin exists, anyone at the machine sees every learner
  and can make a backup or delete a record. That mode is for made-up data only.
- **No consent records.** The app does not record that a family agreed to their child's records being kept.
- **Correcting a record is limited.** A wrong mark cannot be edited on the page yet. A whole learner can be
  deleted (School page, or `athar delete-learner`) and one learner's record can be saved as a file
  (`athar export-learner`).
- **Deleting does not reach old backups or shared files.** Backup copies made earlier still hold the record until
  they are deleted too (the page lists them). A note in the inbox that mentions the learner inside another file
  is not found. Rows blanked in the audit log are matched by the learner's id and record code.
- **Backups are manual and stay on the same disk.** `athar backup` or the School page writes one file to
  `data/backups` and keeps the newest 14. Nothing runs on a schedule and nothing is copied off the machine, so
  a lost or broken computer still loses the history unless someone saves a copy elsewhere. A backup is not
  encrypted and holds names.
- **A cloud key typed in the app is kept in memory until the app stops.** Any signed-in teacher (or, before an
  admin exists, anyone who can open the page) can start a run that uses it.
- **The MCP HTTP server has no authentication.** Keep it on `127.0.0.1`. Do not put it on a network or behind a
  public tunnel with real data.
- **The guard is a word list.** It blocked 2 of 6 labelling phrasings it was not written for (see `EVALS.md`). The
  teacher gate is the real protection.

## Data

All data in this repository is synthetic. Learners are aliases such as "Learner A-17", teachers are fictional and
the school is made up.
Never add real learner data to this repository, an issue, a pull request or a test.

The names shown for learners are invented (a first name and an initial). They are not real children.

The default is a local open-weights model, so nothing leaves the machine. The Agent page can use OpenAI or Claude
for a run instead. Then the document and the records the agent reads are sent to that company, by record code and
without names. Do that with synthetic data only. The page says so each time a cloud model is chosen.

The offline Windows package (`packaging/windows/`) starts the app and the model runner on `127.0.0.1` only, and
the runner with its own web page off and in offline mode. Its `settings.txt` may hold a model key if the person
writes one there. That is plain text on their own computer; the file that ships sets nothing, and a test checks
that. The launcher reads only the names it knows from that file and ignores the rest.

## Reporting a problem

Open a private security advisory on the GitHub repository (Security, then Report a vulnerability). Please do not
open a public issue for something that could expose learner data. Say what you did, what happened and what you
expected.

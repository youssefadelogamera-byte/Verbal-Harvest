> **Learning International Schools · مدارس التعليم العالمية.** This copy is branded and set up as an
> installable school app. Start with [SCHOOL.md](SCHOOL.md). Based on [Athar](https://github.com/OmarAxis/Athar)
> (Apache 2.0, see [NOTICE](NOTICE)).

# Athar

Athar follows one learner across years and shows a teacher where that learner is strong, where they struggle, and where a struggle may have started. This copy is set up for Learning International Schools in Saudi Arabia, on the Cambridge curriculum. The name is Arabic for a trace, the mark something leaves behind.

Status: stage two, on synthetic data only. It has not been used with a real teacher or a real learner. Do not put real learner data in it yet. See [SECURITY.md](SECURITY.md).

## Which one is for you

| You are | Take this | Then read |
|---|---|---|
| A parent or a teacher | `Athar-windows-with-model.zip` from the [Athar folder on Google Drive](https://drive.google.com/drive/folders/1Fg7QVpYEbY4f-Tua_oJ7YMvfS3-1tjMO). The model is inside. Nothing to install. | `START HERE.txt` in that folder ([بالعربي: «ابدأ من هنا»](https://drive.google.com/drive/folders/1Fg7QVpYEbY4f-Tua_oJ7YMvfS3-1tjMO)), then the guide inside the program |
| A developer | This repository: `git clone https://github.com/OmarAxis/Athar.git` | [Getting it running](docs/GETTING-STARTED.md) ([بالعربي](docs/GETTING-STARTED.ar.md)), [ARCHITECTURE.md](ARCHITECTURE.md), [CONTRIBUTING.md](CONTRIBUTING.md) |

What Athar does, in one page: [About Athar](docs/ABOUT.md) ([بالعربي](docs/ABOUT.ar.md)).

## What it has

- **The Cambridge curriculum for Years 1 to 11** (Primary, Lower Secondary and IGCSE) as a map of topics and what each topic needs first, in three subjects. Every topic has its grade (Cambridge stage or year), its term in a three-term year, and its source. All three maps are drafts: see "What is not finished".

  | Subject | Topics | Pack |
  |---|---|---|
  | Mathematics | 120 | `packs/cambridge-maths` |
  | Science | 100 | `packs/cambridge-science` |
  | English | 78 | `packs/cambridge-english` |

  `packs/cambridge-school` joins the three and adds eight links between subjects. The subjects taught for the Saudi Ministry of Education (Arabic, Islamic Studies, Social Studies) are not mapped yet: a school admin can add them on the School page.
- **A synthetic Saudi Cambridge school** on that map: 40 learners, 9 teachers (one per stage, Primary, Lower Secondary and IGCSE, in each subject), one class per grade, three past school years and a term in progress. Everything in it is made up.
- **Sign-in for teachers**, with a school admin who creates the accounts.
- **Classes.** Once sign-in is on, a teacher sees the learners of their own classes and nobody else. The admin sees everyone.
- **Learner records.** A teacher adds a learner and gets a record code. There is no login for learners.
- **An Add records page**: a marks sheet for Excel that needs no model, and document upload for the agent.
- **Adding to the curriculum** (School page, admin). A school adds topics for another grade or another subject: it types them in, or uploads a contents page (text, Word, Excel, or a picture) for the model to read. The model lists the topics and suggests which needs which. Plain code checks what it returns, a named teacher checks every topic and every link, and only then is the addition laid over the installed curriculum. The installed pack files are never rewritten, and an addition can be withdrawn while no record uses it. See "What is not finished".
- **Looking after the records** (School page, admin): a backup copy, one learner's whole record as a file, deleting one learner for good, and withdrawing one wrong record.

- **Two sides in one program: a school, or a family.** The first time it opens, it asks who is using it. A teacher gets classes and marks sheets. A parent gets their own child only: they type in results and notes, and read what is going well, where to help first, and what to ask the teacher. See "For parents" below.
- **Arabic, right to left.** The page opens in Modern Standard Arabic and has a button to switch to English. Topic names, the made-up school, the marks sheet, the printable report and the agent's findings are in Arabic too. See "Arabic" below.

Underneath: a graph engine in plain code that reaches the conclusions, an agent that only reads and words, two teacher gates, a guard that refuses labels, and a log of every action.

## Run it

The full guide, with every step, is [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md) ([بالعربي](docs/GETTING-STARTED.ar.md)). In short:

**Windows, no installing, model inside (easiest).** Download `Athar-windows-with-model.zip` (6.4 GB) from the [Athar folder on Google Drive](https://drive.google.com/drive/folders/1Fg7QVpYEbY4f-Tua_oJ7YMvfS3-1tjMO), extract it, double-click **Start Athar**. Nothing else to download. The same folder has a `START HERE.txt`, two short videos and screenshots.

**Windows, no installing, small download.** Download `Athar-windows.zip` from the Releases page, extract it, double-click **Start Athar**. The first start offers to fetch the model.

**From the source.**

```
uv sync
uv run athar demo
```

Open http://127.0.0.1:8765. The first run builds the synthetic school.

**The model.** Only the Agent page needs one. Three ways, pick any:

- **LM Studio or Ollama on your computer.** Switch its server on. Athar finds it and uses a model it offers.
- **Your own OpenAI or Claude key.** Paste it on the Agent page under "Cloud models". It is kept in memory only.
- **The model inside the Windows package.** Run "Download the model" once (6.1 GB).

To see findings waiting for a decision without running a model:

```
uv run athar story
```

## Try the upload

1. Open **Add records**.
2. Upload the file in `data/samples` (its name starts with `marks-grade`). Give the quiz a name, choose the grade in the file name, term 1, year 2026.
3. Press **Check the sheet**. Nothing is saved yet. You see every mark, the topic of each question, and anything unclear.
4. Press **Save**. Each mark becomes a record tagged with its topic, under your name, and shows in each learner's map.

To make your own sheet, download the template on the same page. Choose a class and a subject, and it lists those learners and has a Topics sheet to pick from.

## Turn on sign-in and set up classes

1. Open **School** and create the school admin. From then on every page of data needs a username and a password.
2. On the same page, add each teacher. A new teacher sees no learner yet.
3. Open a class and give it to a teacher for a subject. The synthetic school already has one class per grade.

Seeding again (`uv run athar seed`) wipes all data, accounts and classes included.

## For parents

Choose **I am a parent** the first time Athar opens. Then:

1. Add your child: a first name and the grade. There is no account for the child.
2. Add a result. Take a photo of the marked paper and Athar fills in the lines for you to check, or type them in: for each part of a test, the topic, the mark, and what it was out of. Old papers from earlier years count too.
3. Write a note in your own words whenever you notice something while studying together.
4. Read the home page. It is worked out in plain code from what you entered, and each part lists the results behind it.

With fewer than six marks it says there is too little to tell, and says nothing else. It never compares a child with anyone. You can look around first with a made-up child, and remove them with one click.

Nothing is sent anywhere. A family's records and a school's records live in the same file on the same computer, and each side shows only its own.

The step-by-step version is [docs/FOR-PARENTS.md](docs/FOR-PARENTS.md).

## Arabic

The page is written in English. In Arabic, every piece of text that reaches the screen is looked up in three dictionaries in `src/athar/web/static`: `ar.json` (the page), `ar-server.json` (sentences the server writes) and `ar-report.json` (the printable report). To change a word, change it there. Three registers are used on purpose:

- buttons, labels and help text: plain Modern Standard Arabic, short and clear, with the school words used in Saudi Arabia (طالب، معلم، الفصل الدراسي);
- topic, strand and subject names: the Arabic of the school books;
- findings, explanations and the report: simple Modern Standard Arabic, because they go on a child's record.

Settings, read from the environment:

```
ATHAR_LANGUAGE=ar          # ar (default) or en: the language the page opens in and findings are worded in
ATHAR_ARABIC_WORDING=fixed # fixed (default): Arabic findings use sentences written in code. model: the model words them
```

`uv run athar seed` writes the made-up school in the language of `ATHAR_LANGUAGE`.

## Looking after the records

```
uv run athar backup                          # one file in data/backups, newest 14 kept
uv run athar restore data/backups/<file>     # stop the app first
uv run athar export-learner K-42             # everything held about one learner, as a file
uv run athar delete-learner K-42 --code K-42 # for good
```

The same four jobs are on the School page for the admin. A backup holds names and is not encrypted. It stays on the same disk unless someone copies it elsewhere.

## What is not finished

- **No teacher has reviewed the maps.** The curriculum says what is taught and when. It does not say which topic depends on which. Those "needs this first" links were written by the authors of this software. The trace-back is only as good as those links. This is the first thing to fix before a pilot.
- **The topic lists were written from general knowledge of the Cambridge frameworks.** They follow the strands of Cambridge Primary, Lower Secondary and IGCSE, but they were not copied from the frameworks or from the school's Marshall Cavendish books, so every topic is marked `verified: false`. The term of each topic follows a typical scheme of work, not the school's own: teachers need to move each topic to the term their books teach it in.
- **No Arabic speaker other than the authors has read the Arabic.** The page text (about 770 phrases), the server sentences (about 350) were translated, and 298 topic names were written by the authors with the help of a language model. The topic names were written from knowledge of the school books, not copied from them, so some will differ from the book's wording. Teachers of each subject need to check them.
- **In Arabic the model does not word the findings.** The local model's Arabic dropped words and added claims in our tries, so Arabic findings and questions use fixed sentences. They are correct but all sound alike. Notes for families are still worded by the model, and a teacher must approve each one.
- **The guard is weaker in Arabic.** It is a word list written mostly for English. A teacher's Arabic edit that labels a child may get through. The teacher gates are the real protection.
- **Parts still in English in Arabic mode:** the raw entries of the audit log, tool names, file names, model names, and any server message that has no entry in the dictionary yet. The learning map and charts keep their left-to-right shape (grade 4 on the left). Numbers are not given Arabic plural forms, so counts are written like "عدد السجلات: 5".
- **The family side is new and untried.** No parent has used it.
- **Photo reading was tried on made-up papers only, never on a real photo of real handwriting.** On clear, straight pictures it read every mark. On a dim or tilted picture it put marks beside the wrong questions and once invented a mark. The check against the total written on the paper caught most of those, not all. So the lines are never saved until the parent ticks that they checked each one. It needs a model that can see pictures, on the same computer. See `EVALS.md`.
- **Wording on the family side is not finished.** The assistant and review pages still speak of "the teacher" in places. There is no password on the family side, so anyone who uses the computer can open it.
- **Links a model suggests for an added curriculum are often wrong.** In our tries the local model listed the topics of a contents page correctly, but some of its "needs this first" links were weak or wrong (it once said sound needs light). Code removes the laziest patterns, and nothing is added before a teacher approves it, but the result is only as good as that teacher's check. PDF files are not read: use a screenshot of the contents page. An approved addition cannot be edited, only withdrawn and made again, and it adds to the installed curriculum; it does not replace it. Parents cannot add to the curriculum.
- **The school's own marking is not modelled.** A mark is a number out of a maximum. Cambridge checkpoint and IGCSE grades, and any house levels the school uses, are not built in.
- **A class opens the whole record.** A teacher with a learner in a class sees that learner in every subject and every year, not only their own subject.
- **No HTTPS by default, no encryption at rest, no consent records, no scheduled or off-machine backup.** See [SECURITY.md](SECURITY.md).
- **Tested by the authors only.** The automated tests pass and the pages were checked by hand in one browser on one computer. No teacher has used it.
- **The agent was tried by the original authors on an earlier made-up school in a handful of runs, not on this one, and not measured.** The numbers in `EVALS.md` are for a small reference cohort on a generic curriculum (`uv run athar seed --pack generic-maths`), and `athar eval` still expects that cohort. See the note at the end of `EVALS.md`.
- **No fine-tuned model.** The stock open-weights model is used.
- **The offline Windows package was built and started on one computer only**, the one it was built on, which has a graphics card. It has not been tried on a school computer. Build it with `uv run python packaging/windows/build.py --out <a folder outside this one>`.

## Guides

- [Getting it running](docs/GETTING-STARTED.md) ([بالعربي](docs/GETTING-STARTED.ar.md))
- [About Athar: what it does for a parent and for a teacher](docs/ABOUT.md) ([بالعربي](docs/ABOUT.ar.md)), with [screenshots](docs/screenshots) in English and Arabic
- [For parents: the first five minutes](docs/FOR-PARENTS.md) ([بالعربي](docs/FOR-PARENTS.ar.md))
- [For teachers: the first ten minutes](docs/FOR-TEACHERS.md) ([بالعربي](docs/FOR-TEACHERS.ar.md))
- The guide with pictures, in both languages: open **Guide and help** inside Athar, or the `Guide` files in the Windows folder
- [Which model to use, especially for Arabic](docs/MODELS.md)
- [Using your own class data](docs/DATA-GUIDE.md) ([بالعربي](docs/DATA-GUIDE.ar.md))
- [How it is built](ARCHITECTURE.md), [what the code protects](SECURITY.md), [how it was tested](EVALS.md)
- [Contributing](CONTRIBUTING.md) and the [code of conduct](CODE_OF_CONDUCT.md)

## Where this could go

[docs/VISION.md](docs/VISION.md) sets out what we think is worth building next, how Athar could connect to the systems schools already have, how it could grow past one computer, and what we think should never be built. It is thinking, not a promise.

## Commands

```
uv run pytest -q                           # tests, no model needed
uv run ruff check src tests                # lint
uv run athar seed                          # rebuild the synthetic Cambridge school, three subjects (wipes everything)
uv run athar seed --pack cambridge-maths   # one subject only
uv run athar seed --pack generic-maths     # the small reference cohort the evaluation set uses
uv run athar story                         # findings waiting and decided, no model used
uv run athar family-demo                   # a made-up family with three children, to look around the parent side
uv run athar learners                      # list learners
uv run athar run <code> --file data/inbox/<file>   # run the agent for one learner
uv run athar report <code>                 # printable report, approved findings only
```

## Licence

Apache 2.0. See [LICENSE](LICENSE).

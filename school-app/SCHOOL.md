# Learning International Schools: setting up the app

This copy of Athar is branded for **Learning International Schools · مدارس التعليم العالمية**.
It runs on one school computer (the server). Teachers open it from their laptops, tablets and phones on the
school Wi-Fi, and can install it on the home screen like an app.

> **Before real student data:** Athar has only been tried on made-up data. Read [SECURITY.md](SECURITY.md)
> and the "What is not finished" part of [README.md](README.md). Agree consent and data protection with the
> school's leadership first.

## 1. Install on the school server

**Easiest, on Windows:** double-click **`Start LIS Athar.cmd`** in this folder. The first time, it installs what it
needs (uv and the app's packages, so it needs the internet once), then it starts the app and opens the browser.
It opens the school's own, **empty** records (`data/school.db`): no made-up school, names or sample papers.
Keep its window open while you use the app; close it to stop. **`Start LIS Athar (school network).cmd`** does the
same for every computer and phone on the school Wi-Fi (step 4).

Or by hand, on any computer:

```
uv sync
uv run athar start
```

Open http://127.0.0.1:8765 on the server itself. (`uv run athar demo` instead opens a separate made-up school, for trying things out.)

## Setting up the school (admin)

1. Open **School** and create the school admin account. This turns on sign-in.
2. **Teachers:** under "Teachers and accounts", add each teacher with a username and a first password.
3. **School years and classes:** under "Classes", make each class with its grade and the school year it belongs to
   (the year it starts, for example 2026 for 2026/27). Open a class to give it to its teachers.
4. **Students:** under "Add a learner", add each student with their class and grade. Each gets a record code.
5. **Parents:** under "Parents", add each parent with a username and password and choose their children. Give
   them the username, the password and the address of the parents' page: `http://<server>:8765/parent`. A parent
   sees only their own children, and only what a teacher has approved.

## 2. Add the logo

Save the school logo as `branding/logo.png`. See [branding/README.md](branding/README.md).

## 3. Turn on sign-in

Open **School** and create the school admin, then add each teacher and give each class to its teachers.
From then on every page of data needs a username and password.

## 4. Open it to the school network

```
uv run athar start --lan
```

It prints the address to type on other devices, for example `http://192.168.1.20:8765`.
If sign-in is not on yet, it warns you: in that case anyone on the network could see every record.

## 5. Install it on phones (needs HTTPS)

Phones only offer "Install app" / "Add to Home Screen" as a full app over HTTPS. Give the server a
certificate, for example one made by the school's IT team or with `mkcert` for the school's network name:

```
ATHAR_TLS_CERT=/path/to/cert.pem ATHAR_TLS_KEY=/path/to/key.pem uv run athar start --lan
```

Then on each phone, open `https://<server address>:8765`:

- **Android (Chrome):** menu ⋮ → *Install app*.
- **iPhone/iPad (Safari):** Share → *Add to Home Screen*.

The installed app keeps only its icons and word lists. It never stores student records on the phone, and
it shows a clear message when the school server cannot be reached.

## Settings

| Setting | Default | What it does |
|---|---|---|
| `ATHAR_SCHOOL_NAME` | Learning International Schools | School name in English |
| `ATHAR_SCHOOL_NAME_AR` | مدارس التعليم العالمية | School name in Arabic |
| `ATHAR_SCHOOL_TAGLINE` | AI-Powered · Future Skills · Wellbeing | Line under the name |
| `ATHAR_BRANDING` | `branding/` | Folder that holds `logo.png` |
| `ATHAR_LANGUAGE` | `ar` | Language the app opens in (`ar` or `en`) |
| `ATHAR_WEB_PORT` | 8765 | Port |
| `ATHAR_TLS_CERT`, `ATHAR_TLS_KEY` | none | Serve HTTPS |

## The curriculum

The app ships with **Cambridge maps for Mathematics, Science and English, Years 1 to 11** (`packs/cambridge-*`):
Primary (Years 1 to 6), Lower Secondary (Years 7 to 9) and IGCSE (Years 10 and 11), three terms a year.
"Grade" in the app means the Cambridge year.

These maps are drafts. Before relying on them, the heads of each subject should:

1. Check each topic name against the Cambridge framework and the school's Marshall Cavendish books.
2. Move each topic to the term the school's books teach it in (the terms now follow a typical scheme of work).
3. Check every "needs this first" link: the trace-back is only as good as these links.

The pack files are plain YAML, one line per topic, and say all this at the top.

## Still to do for the school

- **Ministry subjects.** Arabic, Islamic Studies and Social Studies are not mapped yet. Add them on the School page
  (type the topics or upload a contents page), or write a pack for each under `packs/`.
- **Teacher access by subject.** A teacher with a learner in their class sees that learner in every subject.

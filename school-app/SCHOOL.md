# Learning International Schools: setting up the app

This copy of Athar is branded for **Learning International Schools · مدارس التعليم العالمية**.
It runs on one school computer (the server). Teachers open it from their laptops, tablets and phones on the
school Wi-Fi, and can install it on the home screen like an app.

> **Before real student data:** Athar has only been tried on made-up data. Read [SECURITY.md](SECURITY.md)
> and the "What is not finished" part of [README.md](README.md). Agree consent and data protection with the
> school's leadership first.

## 1. Install on the school server

```
uv sync
uv run athar demo
```

Open http://127.0.0.1:8765 on the server itself. The first run builds a made-up school so you can look around.

## 2. Add the logo

Save the school logo as `branding/logo.png`. See [branding/README.md](branding/README.md).

## 3. Turn on sign-in

Open **School** and create the school admin, then add each teacher and give each class to its teachers.
From then on every page of data needs a username and password.

## 4. Open it to the school network

```
uv run athar demo --lan
```

It prints the address to type on other devices, for example `http://192.168.1.20:8765`.
If sign-in is not on yet, it warns you: in that case anyone on the network could see every record.

## 5. Install it on phones (needs HTTPS)

Phones only offer "Install app" / "Add to Home Screen" as a full app over HTTPS. Give the server a
certificate, for example one made by the school's IT team or with `mkcert` for the school's network name:

```
ATHAR_TLS_CERT=/path/to/cert.pem ATHAR_TLS_KEY=/path/to/key.pem uv run athar demo --lan
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

## Still to do for the school

- **Curriculum.** The maps that ship are the Egyptian national curriculum, grades 4–8. If the school follows
  a British, American or IB programme, or other grades, it needs its own maps. A school admin can add topics on
  the School page, or new packs can be written under `packs/`.
- **Parent access.** Parents cannot yet sign in to the school's server to see their own child.
- **Teacher access by subject.** A teacher with a learner in their class sees that learner in every subject.

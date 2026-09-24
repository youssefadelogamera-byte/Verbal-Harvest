# Verbal Harvest

**Speak English with confidence.** Verbal Harvest is an AI-powered English speaking and communication app aligned to the **CEFR** (Common European Framework of Reference, Pre-A1 → C2). It has separate tracks for **children, young learners (teens), adults and business professionals**.

## Highlights

| | |
|---|---|
| **Accounts** | Email + password sign-up and sign-in. Passwords are hashed with scrypt, and sessions use httpOnly cookies. Children's accounts need a parent/guardian email and consent. Users can delete their own account. |
| **Adaptive placement test (required)** | Covers grammar, vocabulary, reading, listening (browser text-to-speech) and everyday language. Questions come in blocks at one level (3 of 4 correct to pass, with tie-breakers), and the test moves up or down until it finds the learner's level. A final **speaking/writing task** is rated on the CEFR speaking criteria. The two results are combined (60/40) into a recommended level. |
| **Level choice after the test** | Learners can only choose a level after finishing the placement test. The results page shows the recommended level, a skill profile and speaking feedback. Learners then confirm that level or pick another one within their track. |
| **Can-do curriculum** | 42 units, each tied to a CEFR "can-do" statement. Each unit has key phrases, a pronunciation drill and an AI role-play. Children, business learners and general learners (teens and adults) each have their own units. |
| **AI conversation coach** | Role-plays and free talk with **Harvey**. The coach adjusts its language to the learner's CEFR level and age group. Learners can speak (speech recognition) or type. Replies can be read aloud, and corrections and tips appear after each turn. |
| **Pronunciation lab** | Learners read a phrase aloud, and the app compares it word by word with what speech recognition heard. |
| **Speaking test** | Tasks in exam style, with a report covering range, accuracy, fluency, coherence, interaction, an estimated level and an improved version of the answer. |
| **Dashboard** | XP, daily streak, progress along the learning path, skill averages and recent activity. |

Children get a brighter, more playful look and simpler wording. The AI is told to keep content age-appropriate and never ask children for personal details.

## Tech stack

- **Frontend:** React 18 + Vite + React Router, with hand-written CSS (Fraunces and Inter fonts). It works on desktop and mobile.
- **Backend:** Node.js 22 + Express, using SQLite through the built-in `node:sqlite`, so there are no native dependencies.
- **AI:** Claude (`claude-opus-5`) via the official `@anthropic-ai/sdk`, returning structured JSON. If Claude declines a request, a fallback model answers it. Without an API key the app runs in **practice mode** with rule-based feedback, so every feature still works.
- **Speech:** the browser's Web Speech API (speech recognition and text-to-speech). Recognition works best in Chrome, Edge and Safari. Learners can always type instead.

## Getting started

```bash
npm install
cp .env.example .env        # add ANTHROPIC_API_KEY to enable the Claude coach
npm run dev                 # API on :8787, web app on http://localhost:5173
```

Production:

```bash
npm run build
npm start                   # serves the built app and API on $PORT (default 8787)
```

`npm start` uses Secure cookies, so serve it over HTTPS. To try a production build over plain HTTP, set `COOKIE_SECURE=false`.

### Tests

```bash
npm test
```

The tests cover the item bank, correct placement at every level for every track, the answer key never being sent to the browser, the rule that the test must come before choosing a level, the full sign-up → placement → level → learn → coach flow, guardian consent for children, and JSON-only writes (CSRF protection).

## Project layout

```
server/
  index.js            Express API + static hosting
  auth.js             scrypt hashing, sessions, rate limiting
  db.js               SQLite schema, XP/streak tracking
  placement.js        adaptive CEFR placement engine
  ai.js               Claude coach & examiner + offline fallback
  data/cefr.js        CEFR levels, descriptors, learner tracks
  data/placementBank.js  placement items (kids / general / business)
  data/curriculum.js  can-do units & role-play scenarios
  tests/              node:test suites
client/src/
  pages/              Landing, Auth, Placement, PlacementResult, Dashboard,
                      Learn, Unit, Coach, Pronunciation, Speaking, Profile
  components/         Layout, Logo, LevelBadge, Mic, Icons
  speech.js           speech recognition / TTS hooks, word alignment
```

## Notes

- The CEFR descriptors are paraphrased from the Council of Europe's *CEFR Companion Volume (2020)*.
- Speech recognition turns speech into text in the browser (some browsers use a cloud service to do this). The app sends and stores only text transcripts, never audio.

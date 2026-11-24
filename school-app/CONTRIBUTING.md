# Contributing to Athar

Thank you for wanting to help. Athar is young and has been tested by its authors only. You do not need to be a programmer: a subject teacher who reads one curriculum map helps as much as anyone.

Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first.

## Set up

You need [uv](https://docs.astral.sh/uv/).

```
uv sync --extra dev          # install
uv run athar demo            # build the made-up school and open the app
uv run pytest -q             # tests, no model needed
uv run ruff check src tests  # lint
```

## How to send a change

1. Work on a branch. Do not push to `main`.
2. Add a test with every fix.
3. Run the tests and the lint. Both must pass.
4. `uv run athar seed` rewrites tracked files in `data/`. Restore them with `git checkout -- data/` before you commit.
5. Open a pull request. Say what you changed, why, and how you checked it.

Documents use plain English, short sentences, and no em dashes or en dashes. Arabic text follows [docs/arabic-glossary.md](docs/arabic-glossary.md).

## Rules that must not be broken

1. **Made-up data only in the repository.** Never a real learner's data in code, tests, issues, pull requests or screenshots.
2. **Never commit a key.** No `.env` file, no key in code, documents, tests or commit messages.
3. **Nothing that labels, ranks or tracks a child.** Do not weaken `src/athar/guard.py` or the teacher gates.
4. **Every finding cites its records.** The record ids come from the tools, never from the model.
5. **Every tool call is logged.** A new tool must use `@audited`.
6. **Report results as they are.** Do not edit the generated table in `EVALS.md` by hand. If something fails, write it down.

[SECURITY.md](SECURITY.md) lists what the code enforces. If you change one of those rules, change that page and its test too.

## Where help is most wanted

- **Subject teachers to review the curriculum maps.** The "needs this first" links were written by the authors and no teacher has checked them. The Arabic topic names need checking against the school books too.
- **New curriculum packs** for other countries and grades.
- **Testing on ordinary school computers.** The Windows package has run on one computer only. Tell us the machine, the steps and the result.
- **Arabic wording.** No Arabic speaker other than the authors has read it.
- **Accessibility.** Try the pages with a keyboard only, a screen reader or large text, and tell us what breaks.

The README section "What is not finished" and [docs/VISION.md](docs/VISION.md) have the full list.

## Proposing a curriculum change

A pack is a folder in `packs/` with a `pack.yaml` file. In your pull request or issue:

- Say where each topic comes from: the book, the grade, the term and the year of printing. Say so if the source is a workbook or an article.
- Say who reviewed each "needs this first" link and what they teach. If nobody has, say that. An unreviewed link is welcome when it is marked as one.
- A topic may only need topics taught earlier. A test checks this.

## Questions and problems

Open an issue for a bug or an idea. For anything that could expose learner data, use a private security advisory, as [SECURITY.md](SECURITY.md) explains.

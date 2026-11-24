"""Command line. `uv run athar demo` is the one command a stranger needs."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import db
from .config import get_settings

app = typer.Typer(add_completion=False, help="Athar: a cited learning map for every learner.")
console = Console()


def _ensure_seeded() -> None:
    """Create the synthetic demo data the first time, so one command is enough.
    Messages go to stderr: on stdio, stdout belongs to the MCP protocol."""
    settings = get_settings()
    db.init_db()
    with db.connect() as conn:
        count = db.one(conn, "SELECT COUNT(*) AS n FROM learners")["n"]
    if count == 0:
        notices = Console(stderr=True)
        notices.print(f"No data yet. Generating a synthetic school on the '{settings.demo_pack}' curriculum...")
        summary = _generate(settings.demo_pack)
        notices.print(f"Seeded {settings.db_path} ({summary})")


def _generate(pack: str | None, seed: int | None = None, learners: int | None = None, years: int = 4,
              school: bool = False) -> dict:
    """A pack that says `generator: school` gets a whole synthetic school built from its own graph.
    Any other pack gets the small reference cohort."""
    from . import synth, synth_school
    from .curriculum import read_pack_data
    settings = get_settings()
    if pack and read_pack_data(settings.packs_dir / pack / "pack.yaml").get("generator") == "school":
        return synth_school.generate_school(seed=seed if seed is not None else 11, pack_id=pack,
                                            n_learners=learners or 40)
    if school:
        pack = pack or "generic-school"
    count = learners or (synth.SCHOOL_LEARNERS if school else 12)
    return synth.generate(seed=seed if seed is not None else 7, n_learners=count, years=years, pack_id=pack, school=school)


def _resolve_learner(text: str) -> str:
    """Accept a learner id or an alias such as 'A-17'."""
    with db.connect() as conn:
        row = db.one(conn, "SELECT id FROM learners WHERE id=? OR alias=? OR alias LIKE ?", (text, text, f"%{text}"))
    if not row:
        raise typer.BadParameter(f"No learner matches '{text}'. Try `athar learners`.")
    return row["id"]


@app.command()
def seed(seed: int = typer.Option(None, help="Random seed. The same seed gives the same data."), learners: int | None = typer.Option(None, help="How many learners. Default 12, or 36 with --school."),
         years: int = 4,
         pack: str = typer.Option(None, help="Curriculum pack id, e.g. generic-school for all subjects."),
         school: bool = typer.Option(False, "--school", help="A whole school: all four subjects, 36 learners, ten "
                                                             "teachers who each teach a subject and describe how they teach.")) -> None:
    """Regenerate the synthetic data. Wipes existing data, accounts included."""
    if pack is None and not school:
        pack = get_settings().demo_pack
    console.print_json(json.dumps(_generate(pack, seed, learners, years, school), default=str))


@app.command()
def story() -> None:
    """Build a ready state for presenting: findings proposed by the engine, some approved, some waiting.
    No model is used. Every step is logged with the actor 'demo-setup'."""
    _ensure_seeded()
    from . import story as story_module
    console.print_json(json.dumps(story_module.build(), default=str))


@app.command("family-demo")
def family_demo(english: bool = typer.Option(False, "--english", help="English names and notes instead of Arabic.")) -> None:
    """Set up a made-up family to look around or take pictures: a parent, three children, results across
    three school years, notes, and findings. Everything is invented. No model is used."""
    if english:                       # findings are worded in the language of the installation
        import os
        os.environ["ATHAR_LANGUAGE"] = "en"
    _ensure_seeded()
    from . import demo_family
    console.print_json(json.dumps(demo_family.build(language="en" if english else None), default=str))


@app.command()
def demo(lan: bool = typer.Option(False, "--lan", help="Serve every computer and phone on the school network, "
                                    "not only this computer. Turn sign-in on first.")) -> None:
    """Seed if needed, then open the teacher app."""
    if lan:
        os.environ["ATHAR_WEB_HOST"] = "0.0.0.0"
    _ensure_seeded()
    s = get_settings()
    scheme = "https" if s.tls_cert else "http"
    if lan:
        console.print(f"School app on the network: {scheme}://{_network_address()}:{s.web_port}   (Ctrl+C to stop)")
    else:
        console.print(f"Teacher app: {scheme}://{s.web_host}:{s.web_port}   (Ctrl+C to stop)")
    from .web.app import main as web_main
    web_main()


def _network_address() -> str:
    """This computer's address on the school network, for teachers to type on their phones."""
    import socket

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))  # sends nothing: it only asks which interface would be used
        return probe.getsockname()[0]
    except OSError:
        return socket.gethostname()
    finally:
        probe.close()


@app.command()
def serve(lan: bool = typer.Option(False, "--lan", help="Serve the whole school network.")) -> None:
    """Run the teacher app."""
    demo(lan=lan)


@app.command()
def mcp(http: bool = typer.Option(False, help="Serve streamable HTTP instead of stdio.")) -> None:
    """Run the Athar MCP server (stdio by default) for any MCP host."""
    _ensure_seeded()
    from . import server
    if http:
        sys.argv = [sys.argv[0], "--http"]
    else:
        sys.argv = [sys.argv[0]]
    server.main()


@app.command()
def learners() -> None:
    """List learners (alphabetical, by alias)."""
    _ensure_seeded()
    with db.connect() as conn:
        found = db.rows(conn, "SELECT id, alias, home_language FROM learners ORDER BY alias")
    table = Table("id", "alias", "home language")
    for r in found:
        table.add_row(r["id"], r["alias"], r["home_language"])
    console.print(table)


@app.command()
def teachers() -> None:
    """List teachers and their ids (needed for `athar decide`)."""
    _ensure_seeded()
    with db.connect() as conn:
        found = db.rows(conn, "SELECT id, name FROM teachers ORDER BY name")
    table = Table("id", "name")
    for r in found:
        table.add_row(r["id"], r["name"])
    console.print(table)


def _print_run(record: dict) -> None:
    console.rule(f"run {record['run_id']} · {record['status']} · model {record.get('model')}")
    for step in record.get("steps", []):
        mark = "ok " if step.get("ok", True) else "!! "
        console.print(f"[dim]{step['ts'][11:19]}[/dim] {mark}[bold]{step['node']}[/bold]: {step['note']}", highlight=False)
    for q in record.get("open_questions", []):
        console.print(f"   open question: {q}", highlight=False)
    if record.get("pending"):
        console.print(f"Waiting for a teacher: {record['pending']}", highlight=False)
    if record.get("error"):
        console.print(f"[red]{record['error']}[/red]", highlight=False)
    console.print(f"usage: {record.get('usage')}", highlight=False)


@app.command()
def run(learner: str, file: Path | None = typer.Option(None, help="A new document to ingest first."),
        frontier: bool = typer.Option(False, help="Use the optional frontier model instead of the local one."),
        model: str | None = typer.Option(None, help="Model id to use."),
        provider: str = typer.Option("local", help="local (open weights, the default), openai or anthropic. The cloud "
                                                   "ones read OPENAI_API_KEY or ANTHROPIC_API_KEY and send documents out.")) -> None:
    """Run the agent for one learner until it finishes or stops for a teacher."""
    _ensure_seeded()
    from .agent import runner
    task = {"learner_id": _resolve_learner(learner), "which_model": "frontier" if frontier else provider}
    if file:
        task["inbox_file"] = str(file.resolve())
    if model:
        task["model"] = model
    _print_run(runner.run_blocking(task))


@app.command()
def resume(run_id: str) -> None:
    """Continue a run after the teacher has decided."""
    from .agent import runner
    _print_run(runner.resume_blocking(run_id))


@app.command()
def report(learner: str = typer.Argument(None, help="Alias such as A-17, or a learner id. Leave out with --all."),
           out: Path | None = typer.Option(None, help="File to write, or a folder with --all. Default: reports/"),
           everyone: bool = typer.Option(False, "--all", help="Write one report for every learner.")) -> None:
    """Write a printable report: the learner's records as a graph, then approved findings and notes only."""
    _ensure_seeded()
    from . import report as report_module
    if everyone:
        with db.connect() as conn:
            wanted = [r["id"] for r in db.rows(conn, "SELECT id FROM learners ORDER BY alias COLLATE NOCASE, id")]
    elif learner:
        wanted = [_resolve_learner(learner)]
    else:
        raise typer.BadParameter("Name a learner, or use --all.")
    folder = out if (out and everyone) else Path("reports")
    for learner_id in wanted:
        data = report_module.build(learner_id)
        target = out if (out and not everyone) else folder / f"{data['learner']['alias'].split()[-1]}.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(report_module.render_html(data), encoding="utf-8")
        console.print(f"Wrote {target} ({len(data['findings'])} approved findings, {len(data['notes'])} approved notes).", highlight=False)


@app.command("export-graph")
def export_graph(out: Path = typer.Option(Path("exports") / "school.graphml", help="GraphML file to write.")) -> None:
    """Write the whole school graph to a file that Gephi, Cytoscape, yEd or Neo4j can open."""
    _ensure_seeded()
    from . import school
    done = school.export_graph(out)
    console.print(f"Wrote {out}: {done['nodes']} nodes, {done['edges']} links.", highlight=False)


@app.command()
def answer(request_id: str, teacher: str = typer.Option(..., help="Teacher id. See `athar teachers`."),
           text: str | None = typer.Option(None, help="The record in the teacher's own words."),
           file: str | None = typer.Option(None, help="Name of a file in the inbox."),
           year: int | None = typer.Option(None), term: int | None = typer.Option(None),
           none: bool = typer.Option(False, "--none", help="Answer that no record exists.")) -> None:
    """Answer the agent's question about a missing record, as a named teacher. Then `athar resume`."""
    from . import review
    result = review.answer_request(request_id, "no_record" if none else "provided", teacher, text, file, year, term)
    console.print(f"Request {result['id']} is now '{result['status']}'.", highlight=False)


@app.command()
def pending() -> None:
    """Show what is waiting for a teacher."""
    from . import review
    console.print_json(json.dumps(review.pending(), ensure_ascii=False, default=str))


@app.command()
def decide(target_id: str, decision: str, teacher: str = typer.Option(..., help="Teacher id (tch_...)."),
           note: str | None = None, edited: str | None = typer.Option(None, help="New statement, for decision=edited.")) -> None:
    """Record a teacher's decision on a finding (fnd_...) or a summary (sum_...)."""
    from . import review
    if target_id.startswith("sum_"):
        result = review.decide_summary(target_id, decision, teacher, note=note)
    else:
        result = review.decide_finding(target_id, decision, teacher, note=note, edited_statement=edited)
    console.print_json(json.dumps(result, ensure_ascii=False, default=str))


@app.command()
def audit(limit: int = 20) -> None:
    """Show the most recent tool calls."""
    with db.connect() as conn:
        found = db.rows(conn, "SELECT ts, actor, tool, ok, duration_ms, run_id FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
    table = Table("time", "actor", "tool", "ok", "ms", "run")
    for r in found:
        table.add_row(r["ts"], r["actor"], r["tool"], "yes" if r["ok"] else "NO", str(r["duration_ms"]), r["run_id"] or "")
    console.print(table)


@app.command("eval")
def eval_(repeats: int = typer.Option(3, help="Runs per model-dependent task, to measure variation."),
          skip_model: bool = typer.Option(False, help="Only run the tasks that need no model."),
          models: str | None = typer.Option(None, help="Comma-separated model ids to compare.")) -> None:
    """Run the evaluation set and write evals/results and EVALS.md."""
    from .evals import run_all
    run_all(repeats=repeats, skip_model=skip_model, models=models.split(",") if models else None)


@app.command()
def backup(to: Path = typer.Option(None, help="Folder to write the copy to. Default: data/backups, newest 14 kept.")) -> None:
    """Copy the whole database to one file. Safe while the app is running."""
    from . import privacy
    console.print_json(json.dumps(privacy.make_backup(to), default=str))


@app.command()
def restore(file: Path, yes: bool = typer.Option(False, "--yes", help="Do it without asking.")) -> None:
    """Replace the database with a backup copy. Stop the app first."""
    from . import privacy
    if not yes:
        typer.confirm(f"Replace {get_settings().db_path} with {file}? The current data is kept as a .before-restore file.",
                      abort=True)
    console.print_json(json.dumps(privacy.restore_backup(file), default=str))


@app.command("export-learner")
def export_learner(learner: str, out: Path = typer.Option(None, help="File to write. Default: exports/record-<code>.json")) -> None:
    """Write everything held about one learner to a file, for a family that asks."""
    from . import privacy
    data = privacy.export_learner(_resolve_learner(learner), actor="cli")
    code = data["learner"]["alias"].replace("Learner ", "")
    target = out or Path("exports") / f"record-{code}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"Wrote {target} ({len(data['evidence'])} records).")


@app.command("delete-learner")
def delete_learner(learner: str, code: str = typer.Option(..., help="The record code again, to confirm. For example K-42.")) -> None:
    """Delete one learner's record for good. This cannot be undone."""
    from . import privacy
    console.print_json(json.dumps(privacy.delete_learner(_resolve_learner(learner), code, actor="cli"), default=str))


if __name__ == "__main__":
    app()

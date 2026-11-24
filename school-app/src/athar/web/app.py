"""Teacher web app: a thin JSON API over graph, review and db, plus one static page.

Sign-in: once the school has an account, every page of data needs a signed-in teacher, and a decision
is recorded under the signed-in teacher whatever the page sends. While no account exists (synthetic
demonstration data) a teacher is chosen from a list so every decision still carries a name.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import (
    accounts,
    audit,
    classes,
    curriculum_add,
    db,
    family,
    graph,
    imports,
    photo,
    privacy,
    report,
    review,
    school,
    tools,
)
from ..config import get_settings
from ..curriculum import current_lang, load_pack
from . import dashboard, people

STATIC = Path(__file__).with_name("static")
_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,119}")
_LEARNER_PATH = re.compile(r"^/(?:api/)?learners/([^/]+)")

app = FastAPI(title="Athar", docs_url=None, redoc_url=None)
# Brand assets (the logo). The page itself is served at "/".
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class _RunnerUnavailable(Exception):
    pass


@app.exception_handler(ValueError)
async def _value_error(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=400)


@app.exception_handler(_RunnerUnavailable)
async def _runner_unavailable(_: Request, exc: _RunnerUnavailable) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=503)


@app.exception_handler(accounts.NotAllowed)
async def _not_allowed(_: Request, exc: accounts.NotAllowed) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=403)


_OPEN = {"/api/session", "/api/session/sign-in", "/api/session/setup", "/api/session/sign-out"}


@app.middleware("http")
async def _require_sign_in(request: Request, call_next):
    """Once the school has an account, learner data is served to a signed-in teacher only."""
    path = request.url.path
    request.state.who = None
    # Topic names follow the reader's language: their own choice (a cookie), else the school's setting.
    chosen = request.cookies.get("athar_lang")
    current_lang.set(chosen if chosen in ("ar", "en") else get_settings().language)
    if path.startswith(("/api/", "/learners/")) and path not in _OPEN and accounts.enabled():
        who = accounts.session_teacher(request.cookies.get(accounts.COOKIE))
        if who is None:
            return JSONResponse({"error": "Sign in first."}, status_code=401)
        request.state.who = who
        named = _LEARNER_PATH.match(path)
        if named:
            allowed = classes.visible(who)
            if (allowed is not None and named.group(1) not in allowed) or named.group(1) in family.own_children_ids():
                return JSONResponse({"error": "This learner is not in one of your classes. Ask the school admin."},
                                    status_code=403)
    elif path.startswith(("/api/learners/", "/learners/")):
        named = _LEARNER_PATH.match(path)
        at_home = family.mode() == "family"
        if named and at_home and named.group(1) not in family.children_ids():
            return JSONResponse({"error": "That child is not in this family's records."}, status_code=403)
        if named and not at_home and named.group(1) in family.own_children_ids():
            return JSONResponse({"error": "This learner is not in your records."}, status_code=403)
    return await call_next(request)


def _acting(request: Request, claimed: str | None) -> str:
    """The teacher an action is recorded under. Signed in: always the signed-in teacher. Demonstration
    mode: the name chosen on the page."""
    who = getattr(request.state, "who", None)
    if who is not None:
        return who["id"]
    parent = family.guardian()
    if parent is not None:            # at home every record is written under the parent's name
        return parent["id"]
    if not claimed:
        raise ValueError("Choose your name first, so the record shows who did this.")
    return claimed


def _only(request: Request) -> set[str] | None:
    """The learner ids the person asking may see. None means everyone (the admin, or demonstration mode)."""
    who = getattr(request.state, "who", None)
    if who is None and family.mode() == "family":
        return family.children_ids()
    allowed, private = classes.visible(who), family.own_children_ids()
    if not private:
        return allowed
    if allowed is None:                    # everyone the school has, but never a family's own children
        with db.connect() as conn:
            allowed = {row["id"] for row in db.rows(conn, "SELECT id FROM learners")}
    return allowed - private


def _check_learner(request: Request, learner_id: str) -> None:
    """Refuse a learner the person asking may not see: outside their classes, or outside the family."""
    only = _only(request)
    if only is not None and learner_id not in only:
        raise accounts.NotAllowed("This learner is not in your records.")


def _mine(request: Request, items: list[dict], key: str = "learner_id") -> list[dict]:
    only = _only(request)
    return items if only is None else [item for item in items if item.get(key) in only]


def _check_target(request: Request, table: str, target_id: str) -> None:
    """Refuse a decision on a finding, note or question about a learner outside the teacher's classes."""
    with db.connect() as conn:
        row = db.one(conn, f"SELECT learner_id FROM {table} WHERE id = ?", (target_id,))
    if row is not None:
        _check_learner(request, row["learner_id"])


def _admin_or_demo(request: Request) -> str:
    """The admin once sign-in is on. With demonstration data and no account, anyone at the machine."""
    who = getattr(request.state, "who", None)
    if who is None:
        return "teacher-app"
    if who["role"] != "admin":
        raise accounts.NotAllowed("Only the school admin can do this.")
    return f"teacher:{who['id']}"


def _admin(request: Request) -> dict:
    who = getattr(request.state, "who", None)
    if who is None:
        raise ValueError("Create the school admin account first.")
    if who["role"] != "admin":
        raise accounts.NotAllowed("Only the school admin can do this.")
    return who


class SetupBody(BaseModel):
    name: str
    username: str
    password: str


class SignInBody(BaseModel):
    username: str
    password: str


class PasswordBody(BaseModel):
    password: str
    current: str | None = None


class NewTeacher(BaseModel):
    name: str
    username: str
    password: str
    subjects: list[str] = []
    role: str = "teacher"


class NewLearner(BaseModel):
    name: str
    grade: int
    year: int | None = None
    home_language: str = "ar"
    class_id: str | None = None


class NewClass(BaseModel):
    name: str
    grade: int
    year: int | None = None


class ClassTeacher(BaseModel):
    teacher_id: str
    subject: str = "all"


class ClassLearners(BaseModel):
    learner_ids: list[str]


class DeleteLearner(BaseModel):
    confirm_code: str


class WithdrawRecord(BaseModel):
    reason: str
    teacher_id: str = ""


class FindingDecision(BaseModel):
    decision: str
    teacher_id: str
    note: str | None = None
    edited_statement: str | None = None


class SummaryDecision(BaseModel):
    decision: str
    teacher_id: str
    note: str | None = None


class RequestAnswer(BaseModel):
    answer: str
    teacher_id: str
    text: str | None = None
    inbox_file: str | None = None
    year: int | None = None
    term: int | None = None


class RunRequest(BaseModel):
    learner_id: str
    inbox_file: str | None = None
    model: str | None = None
    provider: str | None = None


class ProviderKey(BaseModel):
    key: str


def _runner():
    """Import the agent runner lazily; the rest of the app works without it."""
    try:
        from ..agent import runner
    except Exception as exc:  # module missing, or one of its optional dependencies is
        raise _RunnerUnavailable(f"The agent is not available on this machine: {exc}") from exc
    return runner


def _learner_exists(conn, learner_id: str) -> None:
    if db.one(conn, "SELECT id FROM learners WHERE id = ?", (learner_id,)) is None:
        raise ValueError(f"Unknown learner '{learner_id}'.")


# ------------------------------------------------------------------ learners

@app.get("/api/learners")
def learners(request: Request) -> dict:
    with db.connect() as conn:
        found = _mine(request, tools.learner_rows(conn, names=True))
    if family.mode() == "family" and getattr(request.state, "who", None) is None:
        now = {c["learner_id"]: c for c in family.children()}       # a child moves up a grade each year
        for row in found:
            row["grade_now"] = now.get(row["learner_id"], row)["grade_now"]
            row["example"] = now.get(row["learner_id"], {}).get("example", False)
        found.sort(key=lambda row: list(now).index(row["learner_id"]) if row["learner_id"] in now else 99)
    in_class = classes.class_of()
    for row in found:
        row["class_name"] = (in_class.get(row["learner_id"]) or {}).get("name")
    return {"learners": found}


@app.get("/api/overview")
def overview(request: Request) -> dict:
    return dashboard.overview(only=_only(request))


@app.get("/api/school/graph")
def school_graph(request: Request) -> dict:
    """The whole school by topic. It never ranks learners."""
    return school.school_graph(only=_only(request))


@app.get("/api/learners/{learner_id}/report")
def learner_report(learner_id: str) -> dict:
    return report.build(learner_id)


@app.get("/learners/{learner_id}/report", response_class=HTMLResponse)
def learner_report_page(learner_id: str) -> str:
    """A printable page with only what a named teacher has approved."""
    return report.render_html(report.build(learner_id))


@app.get("/api/learners/{learner_id}/dashboard")
def learner_dashboard(learner_id: str) -> dict:
    return dashboard.learner_dashboard(learner_id)


@app.get("/api/learners/{learner_id}/mind")
def learner_mind(learner_id: str) -> dict:
    return people.learner_mind(learner_id)


@app.get("/api/learners/{learner_id}/fit")
def learner_fit(learner_id: str, request: Request, teacher_id: str = "") -> dict:
    return people.fit(learner_id, _acting(request, teacher_id))


@app.get("/api/teachers/{teacher_id}/profile")
def teacher_profile(teacher_id: str) -> dict:
    return people.teacher_profile(teacher_id)


@app.post("/api/teachers/{teacher_id}/profile")
def save_teacher_profile(teacher_id: str, body: dict[str, Any], request: Request) -> dict:
    if _acting(request, teacher_id) != teacher_id:
        raise accounts.NotAllowed("A teacher describes their own way of teaching. Nobody else can change it.")
    return people.save_teacher_profile(teacher_id, body)


@app.get("/api/learners/{learner_id}/graph")
def learner_graph(learner_id: str) -> dict:
    data = graph.learner_graph(learner_id)
    # The page recolours nodes while replaying, so it needs the same cut-offs the engine uses.
    data["thresholds"] = {"strong_above": graph.STRENGTH_ABOVE, "gap_below": graph.STRUGGLE_BELOW}
    with db.connect() as conn:
        row = db.one(conn, "SELECT pack_id FROM learners WHERE id = ?", (learner_id,))
    pack = load_pack(row["pack_id"])
    data["subjects"] = [{"id": s, "label": pack.label(s)} for s in pack.subjects]
    data["strand_subject"] = dict(pack.strand_subject)
    return data


@app.get("/api/learners/{learner_id}/timeline")
def learner_timeline(learner_id: str, concept_id: str | None = None) -> dict:
    sql = "SELECT * FROM evidence WHERE learner_id = ? AND status != 'retracted'"
    params: list[Any] = [learner_id]
    if concept_id:
        sql += " AND concept_id = ?"
        params.append(concept_id)
    sql += " ORDER BY period_ord, id"
    with db.connect() as conn:
        _learner_exists(conn, learner_id)
        items = db.rows(conn, sql, tuple(params))
    periods: dict[str, list[dict]] = {}
    for item in items:
        periods.setdefault(db.period_label(item["period_ord"]), []).append(item)
    return {"learner_id": learner_id, "periods": [{"period": p, "items": v} for p, v in periods.items()],
            "counts": {"items": len(items)}}


@app.get("/api/learners/{learner_id}/trace/{concept_id}")
def learner_trace(learner_id: str, concept_id: str) -> dict:
    return graph.trace_root(learner_id, concept_id)


@app.get("/api/learners/{learner_id}/patterns")
def learner_patterns(learner_id: str, min_periods: int = 3) -> dict:
    tools.check_min_periods(min_periods)
    return graph.find_patterns(learner_id, min_periods)


@app.get("/api/learners/{learner_id}/what-worked")
def learner_what_worked(learner_id: str) -> dict:
    return graph.what_worked(learner_id)


@app.get("/api/evidence")
def evidence(request: Request, ids: str = "") -> dict:
    wanted = [i.strip() for i in ids.split(",") if i.strip()][:200]
    if not wanted:
        return {"evidence": []}
    marks = ",".join("?" for _ in wanted)
    with db.connect() as conn:
        found = db.rows(conn, f"SELECT * FROM evidence WHERE id IN ({marks}) ORDER BY period_ord, id",
                        tuple(wanted))
    return {"evidence": _mine(request, found)}


@app.post("/api/evidence/{evidence_id}/withdraw")
def withdraw_record(evidence_id: str, body: WithdrawRecord, request: Request) -> dict:
    """A teacher takes a wrong record out of the analysis. The row is kept and the reason is logged."""
    _check_target(request, "evidence", evidence_id)
    return privacy.withdraw_record(evidence_id, _acting(request, body.teacher_id), body.reason)


@app.get("/api/teachers")
def teachers() -> dict:
    with db.connect() as conn:
        found = db.rows(conn, "SELECT id, name, subjects FROM teachers ORDER BY name COLLATE NOCASE")
    for t in found:
        t["subjects"] = db.jload(t["subjects"], [])
    return {"teachers": found}


# ------------------------------------------------------------------ review

def _expand_finding(conn, finding: dict) -> dict:
    out = review.expand_finding(conn, finding)
    learner = db.one(conn, "SELECT pack_id FROM learners WHERE id = ?", (finding["learner_id"],))
    out["next_step"] = people.next_step(out, load_pack(learner["pack_id"])) if learner else None
    return out


@app.get("/api/review/pending")
def review_pending(request: Request) -> dict:
    data = review.pending()
    data = {key: _mine(request, items) for key, items in data.items()}
    with db.connect() as conn:
        packs = {r["id"]: r["pack_id"] for r in db.rows(conn, "SELECT id, pack_id FROM learners")}
    for finding in data["findings"]:
        finding["next_step"] = people.next_step(finding, load_pack(packs[finding["learner_id"]]))
    for asked in data["requests"]:
        asked["learner_name"] = asked.pop("learner_display_name", None) or asked["learner_alias"]
        pack = load_pack(packs[asked["learner_id"]])
        asked["concept_label"] = pack.label(asked["concept_id"])
        asked["grade"] = pack.concepts[asked["concept_id"]].grade if asked["concept_id"] in pack.concepts else None
    return data


@app.get("/api/findings")
def findings(request: Request, learner_id: str | None = None, status: str | None = None) -> dict:
    sql, params, where = "SELECT * FROM findings", [], []
    if learner_id:
        where.append("learner_id = ?")
        params.append(learner_id)
    if status:
        if status not in tools.FINDING_STATUSES:
            raise ValueError(f"Unknown status '{status}'. Use one of: {', '.join(tools.FINDING_STATUSES)}.")
        where.append("status = ?")
        params.append(status)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY proposed_at DESC, id"
    with db.connect() as conn:
        return {"findings": [_expand_finding(conn, f) for f in _mine(request, db.rows(conn, sql, tuple(params)))]}


@app.get("/api/summaries")
def summaries(request: Request, learner_id: str | None = None) -> dict:
    sql, params = "SELECT * FROM summaries", []
    if learner_id:
        sql += " WHERE learner_id = ?"
        params.append(learner_id)
    sql += " ORDER BY created_at DESC, id"
    with db.connect() as conn:
        found = db.rows(conn, sql, tuple(params))
    found = _mine(request, found)
    for s in found:
        s["finding_ids"] = db.jload(s["finding_ids"], [])
    return {"summaries": found}


def _resume_waiting(target_id: str) -> list[str]:
    """Best effort: continue any run that was waiting on this item."""
    resumed: list[str] = []
    try:
        runner = _runner()
        for run in runner.list_runs():
            if run.get("status") != "waiting_for_teacher":
                continue
            if target_id in json.dumps(run.get("pending") or {}):
                runner.resume(run["run_id"])
                resumed.append(run["run_id"])
    except Exception:  # noqa: BLE001, S110 - resuming is best effort; the decision is already saved
        pass
    return resumed


@app.post("/api/findings/{finding_id}/decision")
def decide_finding(finding_id: str, body: FindingDecision, request: Request) -> dict:
    _check_target(request, "findings", finding_id)
    result = review.decide_finding(finding_id, body.decision, _acting(request, body.teacher_id), body.note,
                                   body.edited_statement)
    return {"finding": result, "resumed_runs": _resume_waiting(finding_id)}


@app.post("/api/summaries/{summary_id}/decision")
def decide_summary(summary_id: str, body: SummaryDecision, request: Request) -> dict:
    _check_target(request, "summaries", summary_id)
    result = review.decide_summary(summary_id, body.decision, _acting(request, body.teacher_id), body.note)
    return {"summary": result, "resumed_runs": _resume_waiting(summary_id)}


@app.get("/api/requests")
def record_requests(request: Request, learner_id: str | None = None) -> dict:
    """Every question the agent asked about a missing record, newest first, with the answer."""
    sql = ("SELECT r.*, t.name AS answered_by_name FROM record_requests r "
           "LEFT JOIN teachers t ON t.id = r.answered_by")
    params: list[Any] = []
    if learner_id:
        sql += " WHERE r.learner_id = ?"
        params.append(learner_id)
    with db.connect() as conn:
        return {"requests": _mine(request, db.rows(conn, sql + " ORDER BY r.asked_at DESC, r.id", tuple(params)))}


@app.post("/api/requests/{request_id}/answer")
def answer_request(request_id: str, body: RequestAnswer, request: Request) -> dict:
    _check_target(request, "record_requests", request_id)
    file_name = None
    if body.inbox_file:
        # Only a file that is in the inbox, by name: a path from the page is never followed.
        file_name = Path(body.inbox_file).name
        if not (_inbox_dir() / file_name).is_file():
            raise ValueError(f"No file called '{file_name}' in the inbox.")
    result = review.answer_request(request_id, body.answer, _acting(request, body.teacher_id), body.text, file_name,
                                   body.year, body.term)
    return {"request": result, "resumed_runs": _resume_waiting(request_id)}


# ------------------------------------------------------------------ audit

@app.get("/api/audit")
def audit_log(request: Request, limit: int = 100, run_id: str | None = None, tool: str | None = None) -> dict:
    sql, params, where = "SELECT * FROM audit_log", [], []
    if run_id:
        where.append("run_id = ?")
        params.append(run_id)
    if tool:
        where.append("tool = ?")
        params.append(tool)
    who = getattr(request.state, "who", None)
    if who is not None and who["role"] != "admin":
        own_runs = [r["run_id"] for r in _visible_runs(request)]
        where.append("(actor = ?" + (f" OR run_id IN ({','.join('?' for _ in own_runs)})" if own_runs else "") + ")")
        params += [f"teacher:{who['id']}", *own_runs]
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(limit, 1000)))
    with db.connect() as conn:
        return {"entries": db.rows(conn, sql, tuple(params))}


@app.get("/api/approvals")
def approvals(request: Request) -> dict:
    with db.connect() as conn:
        found = db.rows(conn, "SELECT * FROM approvals ORDER BY id DESC")
    who = getattr(request.state, "who", None)
    if who is not None and who["role"] != "admin":
        found = [row for row in found if row["teacher_id"] == who["id"]]
    return {"approvals": found}


# ------------------------------------------------------------------ agent runs

def _inbox_dir() -> Path:
    """Where documents wait for the assistant. A family has its own folder, so a parent never sees the
    made-up school's sample files, and a school never sees a family's papers."""
    return get_settings().db_path.parent / ("inbox-family" if family.mode() == "family" else "inbox")


@app.get("/api/inbox")
def inbox() -> dict:
    folder = _inbox_dir()
    files = sorted(p for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []
    return {"files": [{"name": p.name, "path": str(p), "bytes": p.stat().st_size} for p in files
                      if p.name.lower() != "readme.md"]}


@app.post("/api/runs")
def start_run(body: RunRequest, request: Request) -> dict:
    _check_learner(request, body.learner_id)
    task: dict[str, Any] = {"learner_id": body.learner_id}
    with db.connect() as conn:
        _learner_exists(conn, body.learner_id)
    if body.inbox_file:
        path = _inbox_dir() / Path(body.inbox_file).name
        if not path.is_file():
            raise ValueError(f"No file called '{Path(body.inbox_file).name}' in the inbox.")
        task["inbox_file"] = str(path)
    if body.model:
        if not _MODEL_ID.fullmatch(body.model):
            raise ValueError("That model id has characters a model id cannot have.")
        task["model"] = body.model
    elif not body.provider or body.provider == "local":
        try:
            from ..agent import llm
            picked = _usable_model(llm.list_models(), get_settings().llm_model)
            if picked != get_settings().llm_model:
                task["model"] = picked
        except Exception:  # noqa: BLE001, S110 - the endpoint being off is reported by the run itself
            pass
    if body.provider and body.provider != "local":
        from ..agent import llm
        if body.provider not in llm.PROVIDERS:
            raise ValueError(f"Unknown model provider '{body.provider}'.")
        if not llm.key_source(body.provider):
            raise ValueError(f"No key for {llm.PROVIDERS[body.provider].label}. Add one on the Agent page first.")
        task["which_model"] = body.provider
    return _runner().start(task)


def _usable_model(offered: list[str], configured: str) -> str:
    """The model a run uses when the teacher did not pick one. The configured model if the local program
    offers it. Otherwise one it does offer, so a person with LM Studio and any model loaded can start at once."""
    if configured in offered or not offered:
        return configured
    chat = [m for m in offered if "embed" not in m.lower()]
    for wanted in (lambda m: configured in m.lower() and "uncensored" not in m.lower(),
                   lambda m: "qwen" in m.lower() and "uncensored" not in m.lower()):
        found = next((m for m in chat if wanted(m)), None)
        if found:
            return found
    return chat[0] if chat else configured


@app.get("/api/models")
def models() -> dict:
    """The models the local endpoint offers, so a teacher or a tester can pick one for a run."""
    settings = get_settings()
    try:
        from ..agent import llm
        found, problem = llm.list_models(), None
    except Exception as exc:  # noqa: BLE001 - the endpoint being off must not break the page
        found, problem = [], f"The model endpoint at {settings.llm_base_url} did not answer ({type(exc).__name__})."
    return {"default": _usable_model(found, settings.llm_model), "models": found, "endpoint": settings.llm_base_url,
            "problem": problem,
            "providers": _providers(found, problem)}


def _providers(local_models: list[str], local_problem: str | None) -> list[dict]:
    """Every place a model can come from, whether it is ready, and what it offers. Never a key."""
    from ..agent import llm
    settings = get_settings()
    out = [{"id": "local", "label": llm.PROVIDERS["local"].label, "cloud": False, "ready": not local_problem,
            "key_source": None, "models": list(dict.fromkeys([settings.llm_model, *local_models])),
            "problem": local_problem}]
    for provider in (p for p in llm.PROVIDERS.values() if p.cloud):
        source, offered, trouble = llm.key_source(provider.id), [], None
        if source:
            try:
                offered = llm.list_models(provider.id)
            except Exception as exc:  # noqa: BLE001 - a provider being down or refusing the key must not break the page
                trouble = f"{provider.label} did not list its models ({type(exc).__name__}). Check the key."
                offered = llm.CLAUDE_FALLBACK if provider.id == "anthropic" else []
        out.append({"id": provider.id, "label": provider.label, "cloud": True, "ready": bool(source),
                    "key_source": source, "key_env": provider.key_env, "models": offered, "problem": trouble})
    return out


@app.post("/api/providers/{provider}/key")
def set_provider_key(provider: str, body: ProviderKey) -> dict:
    """Keep a cloud provider key in memory for this session. It is not saved and never returned."""
    from .. import audit
    from ..agent import llm
    llm.set_key(provider, body.key)
    audit.log_call("set_model_key", {"provider": provider}, {"kept": "in memory until the app stops"}, True, 0,
                   actor="teacher-app")
    return {"provider": provider, "ready": True, "key_source": llm.key_source(provider)}


@app.delete("/api/providers/{provider}/key")
def forget_provider_key(provider: str) -> dict:
    from ..agent import llm
    llm.forget_key(provider)
    return {"provider": provider, "ready": bool(llm.key_source(provider)), "key_source": llm.key_source(provider)}


def _run_learner(run: dict) -> str | None:
    return (run.get("task") or {}).get("learner_id") or run.get("learner_id")


def _visible_runs(request: Request) -> list[dict]:
    only = _only(request)
    try:
        found = _runner().list_runs()
    except _RunnerUnavailable:
        return []
    return found if only is None else [run for run in found if _run_learner(run) in only]


@app.get("/api/runs")
def runs(request: Request) -> dict:
    _runner()
    return {"runs": _visible_runs(request)}


@app.get("/api/runs/{run_id}")
def run_status(run_id: str, request: Request) -> dict:
    found = _runner().status(run_id)
    learner = _run_learner(found)
    if learner:
        _check_learner(request, learner)
    return found


# ------------------------------------------------------------------ sign-in

def _pack() -> Any:
    with db.connect() as conn:
        learner = db.one(conn, "SELECT pack_id FROM learners LIMIT 1")
    return load_pack(learner["pack_id"] if learner else None)


def _latest_year() -> int | None:
    with db.connect() as conn:
        return db.one(conn, "SELECT MAX(year) AS year FROM evidence")["year"]


def _session_view(who: dict | None) -> dict:
    pack = _pack()
    return {"product": get_settings().product_name, "school": _school(), "sign_in": accounts.enabled(), "teacher": who,
            "language": get_settings().language, "curriculum_name": pack.title(),
            "mode": family.mode(), "guardian": family.guardian(), "school_year": family.school_year(),
            "curriculum": {"id": pack.id, "name": pack.title(), "grades": list(pack.grades), "terms": pack.terms,
                           "subjects": [{"id": sid, "label": pack.label(sid)} for sid in pack.subjects]},
            "latest_year": _latest_year()}


def _set_cookie(response: Response, signed: dict) -> None:
    # HttpOnly: page scripts cannot read it. SameSite=Strict: another site cannot make the browser send it.
    response.set_cookie(accounts.COOKIE, signed["token"], max_age=signed["max_age"], httponly=True,
                        samesite="strict", path="/", secure=bool(get_settings().tls_cert))


@app.get("/api/session")
def session(request: Request) -> dict:
    return _session_view(accounts.session_teacher(request.cookies.get(accounts.COOKIE)))


@app.post("/api/session/setup")
def session_setup(body: SetupBody, response: Response) -> dict:
    """The first account: the school admin. Refused once any account exists."""
    if accounts.enabled():
        raise accounts.NotAllowed("This school already has an admin. Ask them for an account.")
    accounts.create_teacher(body.name, [], body.username, body.password, "admin", actor="setup")
    signed = accounts.sign_in(body.username, body.password)
    _set_cookie(response, signed)
    return _session_view(signed["teacher"])


@app.post("/api/session/sign-in")
def session_sign_in(body: SignInBody, response: Response) -> dict:
    signed = accounts.sign_in(body.username, body.password)
    _set_cookie(response, signed)
    return _session_view(signed["teacher"])


@app.post("/api/session/sign-out")
def session_sign_out(request: Request, response: Response) -> dict:
    accounts.sign_out(request.cookies.get(accounts.COOKIE))
    response.delete_cookie(accounts.COOKIE, path="/")
    return {"signed_out": True}


@app.post("/api/session/password")
def session_password(body: PasswordBody, request: Request) -> dict:
    who = getattr(request.state, "who", None)
    if who is None:
        raise ValueError("Sign in first.")
    accounts.sign_in(who["username"], body.current or "")          # proves the current password
    return accounts.set_password(who["id"], body.password, actor=f"teacher:{who['id']}")


# ------------------------------------------------------------------ people (school admin)

@app.get("/api/school/people")
def school_people(request: Request) -> dict:
    _admin(request)
    return {"people": accounts.people()}


@app.post("/api/teachers")
def add_teacher(body: NewTeacher, request: Request) -> dict:
    who = _admin(request)
    return accounts.create_teacher(body.name, body.subjects, body.username, body.password, body.role,
                                   actor=f"teacher:{who['id']}")


@app.post("/api/teachers/{teacher_id}/password")
def reset_password(teacher_id: str, body: PasswordBody, request: Request) -> dict:
    who = _admin(request)
    return accounts.set_password(teacher_id, body.password, actor=f"teacher:{who['id']}")


@app.post("/api/learners")
def add_learner(body: NewLearner, request: Request) -> dict:
    who = getattr(request.state, "who", None)
    if who is None:
        if family.mode() == "family":
            raise ValueError("On the family side, add a child from the family page.")
        return imports.add_learner(body.name, body.grade, body.year or _latest_year() or family.school_year(),
                                   body.home_language, actor="teacher-app", class_id=body.class_id)
    if who["role"] != "admin":
        own = {c["id"] for c in classes.list_classes(who)}
        if not own:
            raise accounts.NotAllowed("You have no class yet. Ask the school admin to give you one.")
        if body.class_id not in own:
            raise ValueError("Choose one of your classes for this learner.")
    return imports.add_learner(body.name, body.grade, body.year or _latest_year() or 2025, body.home_language,
                               actor=f"teacher:{who['id']}", class_id=body.class_id)


# ------------------------------------------------------------------ who uses this: a school or a family

class ModeBody(BaseModel):
    mode: str
    name: str = ""


class ChildBody(BaseModel):
    name: str
    grade: int


class ResultsBody(BaseModel):
    items: list[dict[str, Any]]
    title: str = ""
    grade: int | None = None
    year: int | None = None
    term: int = 1


class NoteBody(BaseModel):
    text: str
    topic_id: str | None = None


@app.post("/api/mode")
def choose_mode(body: ModeBody, request: Request) -> dict:
    """Say whether a school or a family uses this installation. Once a school has sign-in, only its admin may change it."""
    if accounts.enabled():
        _admin(request)
    return family.choose(body.mode, body.name)


@app.get("/api/family/children")
def family_children() -> dict:
    return {"children": family.children()}


@app.post("/api/family/children")
def family_add_child(body: ChildBody) -> dict:
    return family.add_child(body.name, body.grade)


@app.post("/api/family/example-child")
def family_example_child() -> dict:
    return family.add_example_child()


@app.delete("/api/family/example-child")
def family_remove_example(learner_id: str = "") -> dict:
    return family.remove_example_child(learner_id or None)


class RenameBody(BaseModel):
    name: str


@app.post("/api/family/children/{learner_id}/name")
def family_rename(learner_id: str, body: RenameBody) -> dict:
    return family.rename_child(learner_id, body.name)


@app.get("/api/family/children/{learner_id}/summary")
def family_summary(learner_id: str) -> dict:
    return family.summary(learner_id)


@app.post("/api/family/children/{learner_id}/results")
def family_results(learner_id: str, body: ResultsBody) -> dict:
    return family.add_results(learner_id, body.items, title=body.title, grade=body.grade, year=body.year, term=body.term)


@app.get("/api/family/children/{learner_id}/notes")
def family_notes(learner_id: str) -> dict:
    return {"notes": family.notes(learner_id)}


@app.post("/api/family/children/{learner_id}/notes")
def family_add_note(learner_id: str, body: NoteBody) -> dict:
    return family.add_note(learner_id, body.text, body.topic_id)


@app.post("/api/family/children/{learner_id}/photo")
async def family_photo(learner_id: str, file: UploadFile = File(...), grade: int = Form(...),   # noqa: B008
                       subject: str = Form("")) -> dict:
    """Read a photo of a marked paper with the model on this computer. Nothing is saved: the lines go back
    to the page for the parent to check against the paper."""
    parent = family.guardian()
    if parent is None or learner_id not in family.children_ids():
        raise ValueError("That child is not in this family's records.")
    with db.connect() as conn:
        pack = load_pack(db.one(conn, "SELECT pack_id FROM learners WHERE id = ?", (learner_id,))["pack_id"])
    data = await file.read(photo.MAX_BYTES + 1)
    model = get_settings().llm_model
    try:
        from ..agent import llm
        model = _usable_model(llm.list_models(), model)
    except Exception:  # noqa: BLE001, S110 - if the model is off, read_paper says so in plain words
        pass
    return await run_in_threadpool(photo.read_paper, data, pack, int(grade), subject or None, model=model,
                                   actor=f"guardian:{parent['id']}")


# ------------------------------------------------------------------ classes

@app.get("/api/classes")
def class_list(request: Request) -> dict:
    return {"classes": classes.list_classes(getattr(request.state, "who", None))}


@app.post("/api/classes")
def class_create(body: NewClass, request: Request) -> dict:
    who = _admin(request)
    return classes.create_class(body.name, body.grade, body.year or _latest_year() or 2025, actor=f"teacher:{who['id']}")


@app.post("/api/classes/{class_id}/teachers")
def class_assign(class_id: str, body: ClassTeacher, request: Request) -> dict:
    who = _admin(request)
    return classes.assign_teacher(class_id, body.teacher_id, body.subject, actor=f"teacher:{who['id']}")


@app.delete("/api/classes/{class_id}/teachers/{teacher_id}")
def class_unassign(class_id: str, teacher_id: str, request: Request) -> dict:
    who = _admin(request)
    return classes.remove_teacher(class_id, teacher_id, actor=f"teacher:{who['id']}")


@app.post("/api/classes/{class_id}/learners")
def class_put(class_id: str, body: ClassLearners, request: Request) -> dict:
    who = _admin(request)
    return classes.put_learners(class_id, body.learner_ids, actor=f"teacher:{who['id']}")


@app.delete("/api/classes/{class_id}/learners/{learner_id}")
def class_take_out(class_id: str, learner_id: str, request: Request) -> dict:
    who = _admin(request)
    return classes.take_learner_out(class_id, learner_id, actor=f"teacher:{who['id']}")


# ------------------------------------------------------------------ looking after the records (school admin)

@app.get("/api/admin/backups")
def backup_list(request: Request) -> dict:
    _admin_or_demo(request)
    return {"backups": privacy.list_backups(), "folder": str(privacy.backups_dir())}


@app.post("/api/admin/backups")
def backup_make(request: Request) -> dict:
    made = privacy.make_backup(actor=_admin_or_demo(request))
    return {"made": made, "backups": privacy.list_backups()}


@app.get("/api/admin/backups/{name}")
def backup_download(name: str, request: Request) -> FileResponse:
    _admin_or_demo(request)
    path = privacy.backups_dir() / Path(name).name          # by name only: a path from the page is never followed
    if not re.fullmatch(r"athar-[0-9_-]+\.db", path.name) or not path.is_file():
        raise ValueError("No backup with that name.")
    return FileResponse(path, media_type="application/octet-stream", filename=path.name)


@app.get("/api/learners/{learner_id}/export")
def learner_export(learner_id: str, request: Request) -> Response:
    """Everything held about one learner, as a file, for a family that asks."""
    data = privacy.export_learner(learner_id, actor=_admin_or_demo(request))
    code = data["learner"]["alias"].replace("Learner ", "")
    return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="record-{code}.json"'})


@app.post("/api/learners/{learner_id}/delete")
def learner_delete(learner_id: str, body: DeleteLearner, request: Request) -> dict:
    """Delete one learner's record for good. The record code must be typed to confirm."""
    return privacy.delete_learner(learner_id, body.confirm_code, actor=_admin_or_demo(request))


# ------------------------------------------------------------------ upload

@app.get("/api/upload/topics")
def upload_topics(grade: int | None = None, term: int | None = None, subject: str = "") -> dict:
    return {"topics": imports.topics(_pack(), grade, term, subject or None)}


@app.get("/api/upload/template")
def upload_template(request: Request, grade: int, term: int = 1, questions: int = 5, format: str = "xlsx",
                    class_id: str = "", subject: str = "") -> Response:
    """A marks sheet ready to fill in: the learners of one grade down the side."""
    with db.connect() as conn:
        rows = [row for row in _mine(request, tools.learner_rows(conn, names=True)) if row["grade_now"] == grade]
    if class_id:
        members = {x["learner_id"] for c in classes.list_classes() if c["id"] == class_id for x in c["learners"]}
        rows = [row for row in rows if row["learner_id"] in members]
    table = imports.template_rows(rows, max(1, min(int(questions), imports.MAX_QUESTIONS)))
    name = f"marks-grade{grade}-term{term}"
    if format == "csv":
        return Response(imports.template_csv(table), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    return Response(imports.template_xlsx(table, imports.topics(_pack(), grade, term, subject or None)),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@app.post("/api/upload/marks")
async def upload_marks(request: Request, file: UploadFile = File(...), title: str = Form(""),   # noqa: B008
                       year: int = Form(...), term: int = Form(...), grade: int = Form(...),
                       teacher_id: str = Form(""), confirm: bool = Form(False)) -> dict:
    """Check a filled marks sheet. With `confirm`, save it as records under the teacher's name."""
    table = imports.read_table(file.filename or "", await file.read(imports.MAX_FILE_BYTES + 1))
    if not confirm:
        return {"saved": None, "check": imports.check_marks(table, title=title, year=year, term=term, grade=grade,
                                                            only=_only(request))}
    saved = imports.save_marks(table, title=title, year=year, term=term, grade=grade,
                               teacher_id=_acting(request, teacher_id), filename=file.filename or "",
                               only=_only(request))
    return {"saved": saved, "check": None}


@app.post("/api/upload/document")
async def upload_document(request: Request, file: UploadFile = File(...),   # noqa: B008
                          teacher_id: str = Form("")) -> dict:
    """Put a quiz sheet or a note in the inbox for the agent. This adds no record by itself."""
    who = _acting(request, teacher_id)
    saved = imports.save_document(_inbox_dir(), file.filename or "", await file.read(1_000_001))
    audit.log_call("upload_document", {"file": saved["name"], "bytes": saved["bytes"]}, {"saved": True}, True, 0,
                   actor=f"teacher:{who}")
    return saved


# ------------------------------------------------------------------ adding to the curriculum (school side)

class DraftEdit(BaseModel):
    title: str = ""
    topics: list[dict[str, Any]] = []
    areas: list[dict[str, Any]] = []
    teacher_id: str = ""


class DraftApprove(DraftEdit):
    checked: bool = False


class Actor(BaseModel):
    teacher_id: str = ""


def _curriculum_actor(request: Request, claimed: str | None) -> str:
    """Who may add to the curriculum: the school admin once sign-in is on, and before that the teacher whose
    name is chosen on the page. Never a parent: on the family side the curriculum arrives already reviewed."""
    who = getattr(request.state, "who", None)
    if who is not None:
        if who["role"] != "admin":
            raise accounts.NotAllowed("Only the school admin can add to the curriculum.")
        return who["id"]
    if family.mode() == "family":
        raise accounts.NotAllowed("Adding to the curriculum is done on the school side.")
    if not claimed:
        raise ValueError("Choose your name first, so the record shows who did this.")
    with db.connect() as conn:
        if db.one(conn, "SELECT id FROM teachers WHERE id = ?", (claimed,)) is None:
            raise ValueError("Choose your name first, so the record shows who did this.")
    return claimed


@app.get("/api/curriculum")
def curriculum_view(request: Request) -> dict:
    """What the school has added to the installed curriculum, and the drafts waiting for a teacher."""
    pack = _pack()
    who = getattr(request.state, "who", None)
    found = curriculum_add.listing(pack)
    found["can_add"] = (who["role"] == "admin") if who is not None else family.mode() != "family"
    found["name"] = pack.title()
    found["installed_grades"] = list(pack.grades)
    return found


@app.post("/api/curriculum/drafts")
async def curriculum_draft(request: Request, file: UploadFile | None = File(None),   # noqa: B008
                           title: str = Form(""), subject: str = Form(""), new_subject: str = Form(""),
                           grade: int = Form(...), term: int = Form(0), text: str = Form(""),
                           use_model: str = Form(""), teacher_id: str = Form("")) -> dict:
    """Make a draft from pasted lines, a file, or a picture of a contents page. Nothing is added yet."""
    actor = _curriculum_actor(request, teacher_id)
    pack = _pack()
    image, with_model = None, use_model in ("1", "true", "on", "yes")
    if file is not None and file.filename:
        data = await file.read(curriculum_add.MAX_FILE + 1)
        if photo.kind_of(data):
            image, with_model = data, True          # a picture can only be read by the model
        else:
            text = (text + "\n" + curriculum_add.text_of_file(file.filename, data)).strip()
    model = None
    if with_model:
        model = get_settings().llm_model
        try:
            from ..agent import llm
            model = _usable_model(llm.list_models(), model)
        except Exception:  # noqa: BLE001, S110 - if the model is off, the reading step says so in plain words
            pass
    return await run_in_threadpool(lambda: curriculum_add.create_draft(
        pack, title=title, subject_id=subject, new_subject=new_subject, grade=grade, term=term, text=text, image=image,
        use_model=with_model, model=model, actor=actor))


@app.get("/api/curriculum/drafts/{addition_id}")
def curriculum_get(addition_id: str, request: Request, teacher_id: str = "") -> dict:
    _curriculum_actor(request, teacher_id)
    return curriculum_add.get(_pack(), addition_id)


@app.post("/api/curriculum/drafts/{addition_id}")
def curriculum_save(addition_id: str, body: DraftEdit, request: Request) -> dict:
    actor = _curriculum_actor(request, body.teacher_id)
    return curriculum_add.save_draft(_pack(), addition_id, title=body.title, topics=body.topics, areas=body.areas, actor=actor)


@app.post("/api/curriculum/drafts/{addition_id}/approve")
def curriculum_approve(addition_id: str, body: DraftApprove, request: Request) -> dict:
    """A named teacher approves the draft exactly as it is on their screen."""
    actor = _curriculum_actor(request, body.teacher_id)
    pack = _pack()
    curriculum_add.save_draft(pack, addition_id, title=body.title, topics=body.topics, areas=body.areas, actor=actor)
    return curriculum_add.approve(pack, addition_id, teacher_id=actor, checked=body.checked)


@app.post("/api/curriculum/drafts/{addition_id}/discard")
def curriculum_discard(addition_id: str, body: Actor, request: Request) -> dict:
    return curriculum_add.discard(addition_id, actor=_curriculum_actor(request, body.teacher_id))


@app.post("/api/curriculum/additions/{addition_id}/withdraw")
def curriculum_withdraw(addition_id: str, body: Actor, request: Request) -> dict:
    return curriculum_add.withdraw(addition_id, actor=_curriculum_actor(request, body.teacher_id))


# ------------------------------------------------------------------ page

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html", media_type="text/html")


# ------------------------------------------------------------------ school branding and the installed app
# These are open without sign-in on purpose: they hold no learner data, and the sign-in page and the phone's
# home-screen icon need them before anyone has signed in.

_LOGO_TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg",
               ".jpeg": "image/jpeg"}


def _school() -> dict:
    s = get_settings()
    return {"name": s.school_name, "name_ar": s.school_name_ar, "tagline": s.school_tagline,
            "logo": "/brand/logo", "has_logo": _logo_file() is not None}


def _logo_file() -> Path | None:
    folder = get_settings().branding_dir
    for suffix in _LOGO_TYPES:
        candidate = folder / f"logo{suffix}"
        if candidate.is_file():
            return candidate
    return None


@app.get("/brand/logo")
def brand_logo() -> FileResponse:
    """The school's own logo when one is in the branding folder, else a plain mark in the school's colours."""
    found = _logo_file()
    if found is None:
        return FileResponse(STATIC / "brand" / "mark.svg", media_type="image/svg+xml")
    return FileResponse(found, media_type=_LOGO_TYPES[found.suffix.lower()],
                        headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifest() -> JSONResponse:
    """What a phone or a computer needs to install the app on its home screen or desktop."""
    s = get_settings()
    lang = s.language
    name = s.school_name_ar if lang == "ar" else s.school_name
    icons = [{"src": f"/static/brand/icon-{size}.png", "sizes": f"{size}x{size}", "type": "image/png",
              "purpose": "any"} for size in (192, 512)]
    icons.append({"src": "/static/brand/icon-maskable-512.png", "sizes": "512x512", "type": "image/png",
                  "purpose": "maskable"})
    body = {"name": f"{name}: {s.product_name}", "short_name": s.product_name if lang == "en" else "أثر",
            "description": s.school_tagline, "lang": lang, "dir": "rtl" if lang == "ar" else "ltr",
            "start_url": "/", "scope": "/", "display": "standalone", "orientation": "any",
            "background_color": "#F5F7FB", "theme_color": "#1B2A6B", "icons": icons}
    return JSONResponse(body, media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker() -> FileResponse:
    # Served from the root so it may look after every page of the app.
    return FileResponse(STATIC / "sw.js", media_type="text/javascript",
                        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


def _local_only(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


def main() -> None:
    import uvicorn

    settings = get_settings()
    if not _local_only(settings.web_host):
        print(f"Serving the school network on {settings.web_host}:{settings.web_port}.")
        if not accounts.enabled():
            print("WARNING: sign-in is not on yet. Anyone on this network can open every record. "
                  "Open the School page and create the school admin first.")
        if not settings.tls_cert:
            print("NOTE: without ATHAR_TLS_CERT and ATHAR_TLS_KEY the app is served over plain HTTP. "
                  "Phones can only install the app over HTTPS. See SCHOOL.md.")
    tls = {"ssl_certfile": settings.tls_cert, "ssl_keyfile": settings.tls_key} if settings.tls_cert else {}
    uvicorn.run(app, host=settings.web_host, port=settings.web_port, log_level="info", **tls)


if __name__ == "__main__":
    main()

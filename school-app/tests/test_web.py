"""Web app: JSON API over a small seeded database, and the single static page."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from athar import db, synth, tools


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    base = tmp_path_factory.mktemp("web")
    db_path = base / "athar.db"
    mp = pytest.MonkeyPatch()
    mp.setenv("ATHAR_DB", str(db_path))
    synth.generate(db_path=db_path, n_learners=6, out_dir=base / "out")
    from athar.web.app import app

    yield TestClient(app)
    mp.undo()


@pytest.fixture()
def proposed(client):
    """A freshly proposed finding citing two scored items of one learner."""
    with db.connect() as conn:
        row = db.one(conn, "SELECT learner_id, concept_id FROM evidence WHERE score IS NOT NULL "
                           "AND concept_id IS NOT NULL AND status = 'active' "
                           "GROUP BY learner_id, concept_id HAVING COUNT(*) >= 2 LIMIT 1")
        ids = [r["id"] for r in db.rows(conn, "SELECT id FROM evidence WHERE learner_id = ? AND concept_id = ? "
                                              "AND score IS NOT NULL LIMIT 2", (row["learner_id"], row["concept_id"]))]
    out = tools.propose_finding(learner_id=row["learner_id"], kind="struggle",
                                statement="Scores on this concept stayed low over several terms.",
                                evidence_ids=ids, concept_ids=[row["concept_id"]], confidence=0.6)
    return {"finding_id": out["finding_id"], "learner_id": row["learner_id"], "evidence_ids": ids}


def _teacher(client) -> dict:
    return client.get("/api/teachers").json()["teachers"][0]


def test_learners_alphabetical_by_alias(client):
    learners = client.get("/api/learners").json()["learners"]
    assert len(learners) == 6
    aliases = [lr["alias"] for lr in learners]
    assert aliases == sorted(aliases, key=str.lower)
    assert set(learners[0]) >= {"learner_id", "alias", "grade_now", "home_language", "evidence_count"}


def test_graph_endpoint_has_nodes_edges_timeline(client):
    lid = client.get("/api/learners").json()["learners"][0]["learner_id"]
    body = client.get(f"/api/learners/{lid}/graph").json()
    assert body["nodes"] and body["edges"] and body["timeline"]
    assert {"strong_above", "gap_below"} <= set(body["thresholds"])
    assert {n["state"] for n in body["nodes"]} <= {"strong", "shaky", "gap", "unseen"}


def test_timeline_trace_patterns_what_worked(client):
    lid = client.get("/api/learners").json()["learners"][0]["learner_id"]
    tl = client.get(f"/api/learners/{lid}/timeline").json()
    assert tl["periods"] and tl["periods"][0]["items"]
    g = client.get(f"/api/learners/{lid}/graph").json()
    concept = next(n["id"] for n in g["nodes"] if n["type"] == "concept")
    assert "reason" in client.get(f"/api/learners/{lid}/trace/{concept}").json()
    assert "patterns" in client.get(f"/api/learners/{lid}/patterns").json()
    assert "approaches" in client.get(f"/api/learners/{lid}/what-worked").json()


def test_unknown_learner_is_400(client):
    r = client.get("/api/learners/lrn_nope/graph")
    assert r.status_code == 400 and "error" in r.json()


def test_pending_review_expands_evidence(client, proposed):
    pending = client.get("/api/review/pending").json()
    mine = next(f for f in pending["findings"] if f["id"] == proposed["finding_id"])
    assert {e["id"] for e in mine["evidence"]} == set(proposed["evidence_ids"])
    rows = client.get("/api/evidence", params={"ids": ",".join(proposed["evidence_ids"])}).json()["evidence"]
    assert len(rows) == 2


def test_decision_without_valid_teacher_is_400(client, proposed):
    r = client.post(f"/api/findings/{proposed['finding_id']}/decision",
                    json={"decision": "approved", "teacher_id": "tch_nobody"})
    assert r.status_code == 400
    assert "teacher" in r.json()["error"].lower()
    still = client.get("/api/findings", params={"status": "proposed"}).json()["findings"]
    assert any(f["id"] == proposed["finding_id"] for f in still)


def test_approve_writes_approval_and_audit(client, proposed):
    teacher = _teacher(client)
    r = client.post(f"/api/findings/{proposed['finding_id']}/decision",
                    json={"decision": "approved", "teacher_id": teacher["id"], "note": "Checked with class notes."})
    assert r.status_code == 200, r.text
    approvals = client.get("/api/approvals").json()["approvals"]
    row = next(a for a in approvals if a["target_id"] == proposed["finding_id"])
    assert row["teacher_name"] == teacher["name"] and row["decision"] == "approved"
    entries = client.get("/api/audit", params={"tool": "decide_finding", "limit": 20}).json()["entries"]
    assert any(e["actor"] == f"teacher:{teacher['id']}" for e in entries)
    again = client.post(f"/api/findings/{proposed['finding_id']}/decision",
                        json={"decision": "approved", "teacher_id": teacher["id"]})
    assert again.status_code == 400


def test_inbox_and_runs_do_not_crash(client):
    files = client.get("/api/inbox").json()["files"]
    assert all(f["name"].lower() != "readme.md" for f in files)
    assert client.get("/api/runs").status_code in (200, 503)


def test_index_served_without_external_hosts(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "Athar" in r.text
    urls = re.findall(r"https?://[^\s\"'<>)]+", r.text)
    assert [u for u in urls if u != "http://www.w3.org/2000/svg"] == []


def test_page_and_logo_are_served(client):
    page = client.get("/")
    assert page.status_code == 200
    # Athar's wordmark is type: the Arabic word, the Latin word, and three dots.
    assert 'class="logo"' in page.text and "أثر" in page.text and 'lang="en">Athar<' in page.text
    # Above it, the school's block, with its logo served by this app, never from another host.
    assert 'id="school-logo" src="/brand/logo"' in page.text and "Learning International Schools" in page.text
    assert "meska" not in page.text.lower()


def test_school_branding_without_a_logo_file(client, monkeypatch, tmp_path):
    monkeypatch.setenv("ATHAR_BRANDING", str(tmp_path))
    school = client.get("/api/session").json()["school"]
    assert school["name"] == "Learning International Schools" and school["name_ar"] == "مدارس التعليم العالمية"
    assert school["has_logo"] is False
    logo = client.get("/brand/logo")
    assert logo.status_code == 200 and logo.headers["content-type"].startswith("image/svg+xml")


def test_school_logo_from_the_branding_folder(client, monkeypatch, tmp_path):
    monkeypatch.setenv("ATHAR_BRANDING", str(tmp_path))
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    (tmp_path / "logo.png").write_bytes(png)
    assert client.get("/api/session").json()["school"]["has_logo"] is True
    logo = client.get("/brand/logo")
    assert logo.status_code == 200 and logo.headers["content-type"] == "image/png" and logo.content == png


def test_school_name_comes_from_the_settings(client, monkeypatch):
    monkeypatch.setenv("ATHAR_SCHOOL_NAME", "Another School")
    assert client.get("/api/session").json()["school"]["name"] == "Another School"


def test_the_app_can_be_installed(client):
    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200 and manifest.headers["content-type"].startswith("application/manifest+json")
    body = manifest.json()
    assert body["display"] == "standalone" and body["start_url"] == "/"
    assert {i["sizes"] for i in body["icons"]} >= {"192x192", "512x512"}
    assert any(i["purpose"] == "maskable" for i in body["icons"])
    for icon in body["icons"]:
        assert client.get(icon["src"]).status_code == 200
    page = client.get("/").text
    assert 'rel="manifest" href="/manifest.webmanifest"' in page and 'name="theme-color"' in page


def test_service_worker_never_keeps_learner_data(client):
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"]
    assert sw.headers["service-worker-allowed"] == "/"
    # Every request for data goes straight to the server: the worker returns before touching the cache.
    assert 'url.pathname.startsWith("/api/") || url.pathname.startsWith("/learners/")' in sw.text


def test_branding_and_app_files_are_open_before_sign_in(client):
    for path in ("/brand/logo", "/manifest.webmanifest", "/sw.js", "/static/brand/icon-192.png"):
        assert client.get(path).status_code == 200, path


def test_overview_describes_topics_and_records_not_learner_scores(client):
    body = client.get("/api/overview").json()
    assert body["totals"]["learners"] == 6
    assert body["totals"]["records"] == sum(p["n"] for p in body["records_by_period"])
    assert body["coverage"]["strands"] and body["coverage"]["grades"]
    # The roster shows how complete each record is and what is waiting. It must never carry a score.
    aliases = [r["alias"] for r in body["roster"]]
    assert aliases == sorted(aliases, key=str.lower)
    for row in body["roster"]:
        assert not {"score", "mean", "average", "rank"} & set(row)


def test_learner_dashboard_series_follow_the_record(client):
    lid = client.get("/api/learners").json()["learners"][0]["learner_id"]
    body = client.get(f"/api/learners/{lid}/dashboard").json()
    assert body["totals"]["terms"] == len(body["periods"]) == len(body["timeline"])
    assert body["totals"]["days_absent"] == sum(a["days"] for a in body["absences"])
    for strand in body["strands"]:
        assert all(0 <= p["mean"] <= 1 and p["n"] > 0 and p["period"] in body["periods"] for p in strand["points"])
    assert client.get("/api/learners/nobody/dashboard").status_code == 400


def test_learner_mind_describes_results_and_leaves_out_dispositions(client):
    lid = client.get("/api/learners").json()["learners"][0]["learner_id"]
    body = client.get(f"/api/learners/{lid}/mind").json()
    assert body["strands"] and body["teachers"]
    assert all(0 <= s["mean"] <= 1 and s["n"] > 0 for s in body["strands"] + body["skills"])
    # Persistence is a disposition: it is never summarised as a trait of a child.
    assert "persistence-on-hard-problems" not in {s["id"] for s in body["skills"]}


def test_teaching_style_is_saved_logged_and_never_a_score(client):
    teacher = _teacher(client)
    lid = client.get("/api/learners").json()["learners"][0]["learner_id"]
    before = client.get(f"/api/learners/{lid}/fit", params={"teacher_id": teacher["id"]}).json()
    assert before["has_profile"] is False
    saved = client.post(f"/api/teachers/{teacher['id']}/profile",
                        json={"approaches": {"concrete_objects": "rarely", "peer_groups": "often", "made_up": "always"},
                              "languages": "English, Swahili"}).json()
    assert saved["answers"]["approaches"] == {"concrete_objects": "rarely", "peer_groups": "often"}
    profile = client.get(f"/api/teachers/{teacher['id']}/profile").json()
    assert profile["answers"]["languages"] == "English, Swahili"
    assert len(profile["recorded_units"]) == len(profile["questions"]["approaches"])
    after = client.get(f"/api/learners/{lid}/fit", params={"teacher_id": teacher["id"]}).json()
    assert after["has_profile"] is True
    for row in after["rows"]:
        assert not {"score", "rating", "rank", "grade"} & set(row)
    logged = client.get("/api/audit", params={"tool": "save_teaching_style"}).json()["entries"]
    assert logged and logged[0]["actor"] == f"teacher:{teacher['id']}"
    assert client.post("/api/teachers/nobody/profile", json={}).status_code == 400


def test_pending_findings_carry_a_next_step_for_the_teacher(client, proposed):
    pending = client.get("/api/review/pending").json()["findings"]
    mine = next(f for f in pending if f["id"] == proposed["finding_id"])
    assert mine["next_step"] and "trace back" in mine["next_step"]


def test_patterns_page_cannot_lower_the_evidence_bar(client):
    lid = client.get("/api/learners").json()["learners"][0]["learner_id"]
    r = client.get(f"/api/learners/{lid}/patterns", params={"min_periods": 1})
    assert r.status_code == 400 and "at least 3 terms" in r.json()["error"]


def test_unknown_finding_status_is_400(client):
    assert client.get("/api/findings", params={"status": "bogus"}).status_code == 400


def test_a_teacher_answers_a_record_request(client):
    from athar.curriculum import load_pack
    with db.connect() as conn:
        learner = db.one(conn, "SELECT id, pack_id FROM learners ORDER BY id LIMIT 1")
        seen = {r["concept_id"] for r in db.rows(conn, "SELECT DISTINCT concept_id FROM evidence WHERE learner_id = ? "
                                                       "AND score IS NOT NULL", (learner["id"],))}
    concept = next(c for c in load_pack(learner["pack_id"]).concepts if c not in seen)
    request_id = tools.request_record(learner_id=learner["id"], concept_id=concept,
                                      question="There are no records for this topic. Do you have a quiz?")["request_id"]
    waiting = client.get("/api/review/pending").json()["requests"]
    assert [(r["id"], bool(r["concept_label"]), bool(r["learner_alias"])) for r in waiting] == [(request_id, True, True)]
    url = f"/api/requests/{request_id}/answer"
    teacher = _teacher(client)["id"]
    assert client.post(url, json={"answer": "provided", "teacher_id": teacher}).status_code == 400
    assert client.post(url, json={"answer": "provided", "teacher_id": "nope", "text": "Q1 1 out of 2"}).status_code == 400
    bad_file = client.post(url, json={"answer": "provided", "teacher_id": teacher, "inbox_file": "../../pyproject.toml"})
    assert bad_file.status_code == 400 and "inbox" in bad_file.json()["error"]
    done = client.post(url, json={"answer": "provided", "teacher_id": teacher, "text": "Q1 1 out of 2", "year": 2022, "term": 2})
    assert done.status_code == 200 and done.json()["request"]["status"] == "provided"
    assert client.post(url, json={"answer": "no_record", "teacher_id": teacher}).status_code == 400
    assert client.get("/api/review/pending").json()["requests"] == []
    listed = client.get("/api/requests", params={"learner_id": learner["id"]}).json()["requests"]
    assert listed[0]["answered_by_name"]


def test_school_graph_and_printable_report_are_served(client):
    graph = client.get("/api/school/graph").json()
    assert graph["totals"]["learners"] == 6 and any(n["type"] == "concept" for n in graph["nodes"])
    lid = client.get("/api/learners").json()["learners"][0]["learner_id"]
    data = client.get(f"/api/learners/{lid}/report")
    assert data.status_code == 200 and data.json()["learner"]["learner_id"] == lid
    page = client.get(f"/learners/{lid}/report")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert "Learning report" in page.text
    assert client.get("/learners/nope/report").status_code == 400
    home = client.get("/").text
    assert "viewSchool" in home and "mapSvg" in home


def test_a_run_uses_a_model_the_local_program_really_offers():
    from athar.web.app import _usable_model
    assert _usable_model(["qwen3.5-9b", "llama-3"], "qwen3.5-9b") == "qwen3.5-9b"
    assert _usable_model(["text-embedding-x", "llama-3", "qwen/qwen3.8-27b"], "qwen3.5-9b") == "qwen/qwen3.8-27b"
    assert _usable_model(["text-embedding-x", "llama-3"], "qwen3.5-9b") == "llama-3"
    assert _usable_model([], "qwen3.5-9b") == "qwen3.5-9b"          # nothing listed: say what was configured


def test_the_guide_is_linked_from_the_page_and_served(client):
    assert 'id="help-link"' in client.get("/").text
    guide = client.get("/static/guide/guide.html")
    assert guide.status_code == 200 and "If something is not working" in guide.text and "لو حاجة مش شغالة" in guide.text
    assert client.get("/static/guide/img/parent-home-ar.png").status_code == 200


def test_the_knowledge_graph_draws_itself_in_and_respects_reduced_motion(client):
    page = client.get("/").text
    assert "@keyframes kg-draw" in page and "pathLength: 1" in page
    assert "prefers-reduced-motion: reduce) { .kg-edge { animation: none" in page


def test_the_school_page_has_the_curriculum_card_and_its_arabic(client):
    import json
    from pathlib import Path

    page = client.get("/").text
    arabic = json.loads((Path(__file__).parents[1] / "src" / "athar" / "web" / "static" / "ar.json").read_text(encoding="utf-8"))
    for label in ("The curriculum", "Add topics", "Make a draft", "Check this draft", "Needs first:", "Needed by:",
                  "I checked every topic and every link.", "Approve and add to the curriculum", "Discard this draft",
                  "Let the model read it and suggest which topic needs which", "Read by the model"):
        assert f'"{label}"' in page and label in arabic["exact"], label
    assert "curriculumCard" in page and client.get("/api/curriculum").json()["additions"] == []

"""The presenting state: built by the engine and templates, logged as demo-setup, never by a model."""

from athar import db, story, synth


def test_story_is_sourced_logged_and_leaves_work_for_a_teacher(tmp_path):
    db_path = tmp_path / "athar.db"
    synth.generate(db_path=db_path, out_dir=tmp_path / "out")
    out = story.build(db_path=db_path)
    assert out["proposed"] == out["approved"] + out["waiting"] and out["waiting"] >= 1 and out["approved"] >= 1
    with db.connect(db_path) as conn:
        findings = db.rows(conn, "SELECT * FROM findings")
        actors = {r["actor"] for r in db.rows(conn, "SELECT actor FROM audit_log WHERE tool = 'propose_finding'")}
        notes = {r["note"] for r in db.rows(conn, "SELECT note FROM approvals")}
    assert len(findings) == out["proposed"]
    assert all(len(db.jload(f["evidence_ids"], [])) >= 2 for f in findings)      # every finding is sourced
    assert actors == {story.ACTOR}                                               # never logged as the agent
    assert notes == {"Recorded by the demo setup, not by a real teacher."}
    # Running it twice must not pile up duplicates.
    assert "skipped" in story.build(db_path=db_path)

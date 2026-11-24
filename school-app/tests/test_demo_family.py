"""The made-up family used for looking around and for pictures."""

from __future__ import annotations

from athar import db, demo_family, family, synth_school


def test_the_made_up_family_shows_every_kind_of_page_and_is_never_logged_as_a_parent(tmp_path):
    db_path = tmp_path / "athar.db"
    synth_school.generate_school(db_path=db_path, pack_id="cambridge-school", n_learners=6, out_dir=tmp_path, lang="en")
    out = demo_family.build(language="en", db_path=db_path)
    assert out["parent"] == "Abeer" and [c["marks"] > 0 for c in out["children"]] == [True, True, True]
    assert family.mode(db_path) == "family"
    by_name = {c["name"]: c for c in family.children(db_path)}
    first, second, third = by_name["Dalal"], by_name["Rayan"], by_name["Lamees"]

    helped = family.summary(first["learner_id"], db_path)                 # a difficulty that began in an earlier grade
    assert helped["enough"] and helped["help_first"] and helped["help_first"][0]["start"]["grade"] < first["grade_now"]
    assert helped["next_up"] and len(family.notes(first["learner_id"], db_path)) == 2
    assert family.summary(second["learner_id"], db_path)["going_well"]
    assert family.summary(third["learner_id"], db_path)["enough"] is False   # too little to say anything

    assert out["approved"] >= 1 and out["waiting"] >= 1                    # something decided, something to decide
    with db.connect(db_path) as conn:
        cited = db.rows(conn, "SELECT evidence_ids FROM findings")
        actors = {r["actor"] for r in db.rows(conn, "SELECT DISTINCT actor FROM audit_log WHERE tool = 'add_home_results'")}
    assert cited and all(len(row["evidence_ids"]) > 4 for row in cited)   # every finding cites records
    assert not any(a.startswith("demo") is False and a.startswith("guardian") is False for a in actors)
    assert "skipped" in demo_family.build(language="en", db_path=db_path)  # never on top of a family's own children

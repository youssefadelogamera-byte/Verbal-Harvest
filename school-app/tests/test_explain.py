"""The plain explanation and the numbers behind the pictures on a finding."""

from __future__ import annotations

from athar import db, report, review, tools
from athar.curriculum import load_pack
from athar.explain import explain


def _root_cause(db_path) -> dict:
    made = tools.propose_finding(
        learner_id="lrn_a", kind="root_cause", evidence_ids=["evd_a03", "evd_a04", "evd_a05"],
        statement="Ratio items trace back to division, first met in a term with 18 days absent.",
        concept_ids=["ratios", "division"], path=["ratios", "fractions", "division"], confidence=0.67, db_path=db_path)
    with db.connect(db_path) as conn:
        return review.expand_finding(conn, db.one(conn, "SELECT * FROM findings WHERE id = ?", (made["finding_id"],)))


def test_explanation_only_says_what_the_cited_records_say(db_path):
    finding = _root_cause(db_path)
    got = finding["explain"]
    scored = [r for r in finding["evidence"] if r["score"] is not None]
    assert got["records"] == 3 and sum(point["records"] for point in got["series"]) == len(scored)
    for point in got["series"]:
        mine = [r["score"] for r in scored if db.period_label(r["period_ord"]) == point["period"]]
        assert point["mean"] == round(sum(mine) / len(mine), 3)
    assert [p["period"] for p in got["series"]] == sorted(p["period"] for p in got["series"])
    assert got["days_absent"] == sum(r["absent_days"] or 0 for r in finding["evidence"] if r["kind"] == "attendance")


def test_root_cause_chain_runs_from_where_it_began_to_where_it_shows_now(db_path):
    got = _root_cause(db_path)["explain"]
    assert [topic["id"] for topic in got["chain"]] == ["division", "fractions", "ratios"]
    assert got["chain"][0]["label"] and got["chain"][-1]["grade"] is not None
    text = " ".join(got["facts"])
    assert "builds on" in text and "earliest low point the records show" in text and "not a verdict" in text
    for topic in got["chain"]:                     # a topic with no cited record is shown as that, never as a score
        assert (topic["mean"] is None) == (topic["records"] == 0)


def test_pattern_findings_get_a_term_series_and_no_chain(db_path):
    with db.connect(db_path) as conn:
        pack = load_pack(db.one(conn, "SELECT pack_id FROM learners WHERE id = 'lrn_a'")["pack_id"])
    rows = [{"id": "e1", "kind": "quiz_item", "score": 0.9, "period_ord": db.period_ord(2022, 1), "concept_id": None, "absent_days": None},
            {"id": "e2", "kind": "quiz_item", "score": 0.7, "period_ord": db.period_ord(2022, 2), "concept_id": None, "absent_days": None},
            {"id": "e3", "kind": "attendance", "score": None, "period_ord": db.period_ord(2022, 2), "concept_id": None, "absent_days": 4}]
    got = explain({"kind": "strength", "path": [], "concept_ids": [], "evidence": rows}, pack)
    assert got["chain"] == [] and [p["mean"] for p in got["series"]] == [0.9, 0.7]
    assert got["facts"][0] == "2 records across 2 terms, from 2022-T1 to 2022-T2."
    assert "They average 80%. Term averages ran from 70% to 90%." in got["facts"]
    assert got["facts"][-1] == "4 days of absence were recorded in 2022-T2."
    empty = explain({"kind": "struggle", "path": [], "concept_ids": [], "evidence": []}, pack)
    assert empty == {"facts": [], "series": [], "chain": [], "days_absent": 0, "records": 0}


def test_report_draws_the_chain_and_the_term_chart(db_path):
    finding = _root_cause(db_path)
    review.decide_finding(finding["id"], "approved", "tch_jean", db_path=db_path)
    page = report.render_html(report.build("lrn_a", db_path=db_path))
    assert "Began here" in page and "Shows up here now" in page and "Why this is suggested" in page
    assert 'class="terms"' in page and "Results on the cited records, term by term" in page
    assert report.term_chart_svg([]) == ""
    chart = report.term_chart_svg([{"period": "2022-T1", "mean": 0.25, "records": 3}])
    assert ">25%<" in chart and ">22-T1<" in chart and "http" not in chart

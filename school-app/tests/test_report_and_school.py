"""The printable learner report and the whole-school map."""

from __future__ import annotations

import networkx as nx
import pytest

from athar import db, report, review, school, tools


def _approved_finding(db_path, kind="root_cause") -> str:
    made = tools.propose_finding(
        learner_id="lrn_a", kind=kind, evidence_ids=["evd_a03", "evd_a04", "evd_a05"],
        statement="Ratio items trace back to division, first met in a term with 18 days absent.",
        concept_ids=["ratios", "division"], path=["ratios", "fractions", "division"], confidence=0.67, db_path=db_path)
    review.decide_finding(made["finding_id"], "approved", "tch_jean", note="Checked with the class book.", db_path=db_path)
    return made["finding_id"]


# ---------------------------------------------------------------- report

def test_report_holds_only_what_a_teacher_approved(db_path):
    approved = _approved_finding(db_path)
    waiting = tools.propose_finding(
        learner_id="lrn_a", kind="struggle", evidence_ids=["evd_a03", "evd_a04"],
        statement="Results on ratio items stayed low for three terms.", concept_ids=["ratios"], db_path=db_path)
    data = report.build("lrn_a", db_path=db_path)
    assert [f["id"] for f in data["findings"]] == [approved]
    assert waiting["finding_id"] not in str(data) and data["waiting"] == 1
    finding = data["findings"][0]
    assert finding["teacher"] and finding["note"] == "Checked with the class book."
    assert {r["id"] for r in finding["records"]} == {"evd_a03", "evd_a04", "evd_a05"} and finding["records_total"] == 3
    assert data["learner"]["alias"] == "Learner A-01" and data["span"]["records"] > 0


def test_report_page_cites_records_and_names_the_teacher(db_path):
    _approved_finding(db_path)
    page = report.render_html(report.build("lrn_a", db_path=db_path))
    for expected in ("Learning report: Learner A-01", "Ratio items trace back to division", "evd_a03", "Approved by",
                     "not a grade, a rank or a recommendation", "Where a difficulty may have started"):
        assert expected in page
    assert "<script" not in page and "http://" not in page and "https://" not in page   # one self-contained file
    assert "—" not in page and "–" not in page


def test_report_escapes_text_and_reports_gaps_and_nothing_approved(db_path):
    empty = report.render_html(report.build("lrn_b", db_path=db_path))
    assert "No finding has been approved by a teacher yet" in empty
    made = tools.propose_finding(
        learner_id="lrn_a", kind="root_cause", evidence_ids=["evd_a03", "evd_a04"], concept_ids=["ratios", "division"],
        statement="Results on ratio items stayed low for three terms.", db_path=db_path)
    review.decide_finding(made["finding_id"], "edited", "tch_jean",
                          edited_statement="Results on <b>ratio</b> items stayed low for three terms.", db_path=db_path)
    page = report.render_html(report.build("lrn_a", db_path=db_path))
    assert "&lt;b&gt;ratio&lt;/b&gt;" in page and "<b>ratio</b>" not in page and "Edited and approved" in page
    with pytest.raises(ValueError, match="Unknown learner"):
        report.build("lrn_zz", db_path=db_path)


def test_report_says_what_the_records_cannot_tell(db_path):
    from athar.curriculum import load_pack
    with db.connect(db_path) as conn:
        pack = load_pack(db.one(conn, "SELECT pack_id FROM learners WHERE id = 'lrn_a'")["pack_id"])
        seen = {r["concept_id"] for r in db.rows(conn, "SELECT DISTINCT concept_id FROM evidence WHERE learner_id = 'lrn_a' "
                                                       "AND score IS NOT NULL")}
    concept = next(c for c in pack.concepts if c not in seen)
    asked = tools.request_record(learner_id="lrn_a", concept_id=concept, db_path=db_path,
                                 question="There are no records for this topic. Do you have a quiz or a note?")
    assert report.build("lrn_a", db_path=db_path)["gaps"] == [
        {"topic": pack.label(concept), "answered": False, "teacher": None, "answered_at": None}]
    review.answer_request(asked["request_id"], "no_record", "tch_jean", db_path=db_path)
    gap = report.build("lrn_a", db_path=db_path)["gaps"][0]
    assert gap["answered"] and gap["teacher"]
    assert "confirmed" in report.render_html(report.build("lrn_a", db_path=db_path))


# ---------------------------------------------------------------- school map

def test_school_graph_adds_up_by_topic_and_names_learners_only_through_approved_findings(db_path):
    before = school.school_graph(db_path)
    topics = {n["id"]: n for n in before["nodes"] if n["type"] == "concept"}
    assert before["totals"]["learners"] == 5 and before["totals"]["approved_findings"] == 0
    assert all(n["approved_for"] == [] for n in topics.values())
    assert topics["division"]["records"] > 0 and 0 <= topics["division"]["mean"] <= 1
    assert topics["division"]["state"] in ("strong", "shaky", "gap")
    assert {e["type"] for e in before["edges"]} == {"requires"}
    # No per-learner score anywhere: a learner can only show up in `approved_for`.
    assert "lrn_a" not in str(before) and "Learner A-01" not in str(before)

    _approved_finding(db_path)
    after = {n["id"]: n for n in school.school_graph(db_path)["nodes"] if n["type"] == "concept"}
    assert after["division"]["findings"]["root_cause"] == 1          # placed on the root, not on the struggling topic
    assert after["ratios"]["findings"]["root_cause"] == 0
    assert after["division"]["approved_for"] == [
        {"learner_id": "lrn_a", "alias": "Learner A-01", "name": "Learner A-01", "kind": "root_cause"}]
    assert set(after["division"]["approved_for"][0]) == {"learner_id", "alias", "name", "kind"}   # and never a score


def test_school_graph_of_an_empty_school(tmp_path):
    empty = tmp_path / "empty.db"
    db.init_db(empty)
    got = school.school_graph(empty)
    assert got["nodes"] == [] and got["totals"]["learners"] == 0


def test_export_writes_a_graph_file_without_learner_scores(db_path, tmp_path):
    _approved_finding(db_path)
    target = tmp_path / "out" / "school.graphml"
    done = school.export_graph(target, db_path=db_path)
    graph = nx.read_graphml(target)
    assert done == {"nodes": graph.number_of_nodes(), "edges": graph.number_of_edges()} and done["nodes"] > 5
    kinds = {data["kind"] for _, data in graph.nodes(data=True)}
    assert {"topic", "strand", "learner"} <= kinds
    assert graph.nodes["lrn_a"]["label"] == "Learner A-01"
    assert graph["lrn_a"]["division"]["kind"] == "approved_root_cause" and graph["lrn_a"]["division"]["records"] > 0
    for source, _, data in graph.edges(data=True):
        if graph.nodes[source]["kind"] == "learner":
            assert set(data) <= {"kind", "records"}       # a count of records, never a score


# ---------------------------------------------------------------- the picture in the report

def test_report_graph_draws_this_learners_strands_with_their_averages(db_path):
    data = report.build("lrn_a", db_path=db_path)
    with db.connect(db_path) as conn:
        expected = db.one(conn, "SELECT COUNT(*) AS n, AVG(score) AS mean FROM evidence WHERE learner_id = 'lrn_a' "
                                "AND status = 'active' AND score IS NOT NULL AND concept_id IS NOT NULL")
    seen = [st for st in data["strands"] if st["records"]]
    assert sum(st["records"] for st in seen) == expected["n"] and all(0 <= st["mean"] <= 1 for st in seen)
    svg = report.graph_svg(data)
    assert svg.startswith("<svg") and ">A-01<" in svg and svg.count("<line") >= len(data["strands"])
    for st in data["strands"]:
        assert (f"{round(st['mean'] * 100)}%" if st["mean"] is not None else "none") in svg
    page = report.render_html(data)
    assert "What the records show" in page and "not\ncompared with any other learner" in page and "<script" not in page


def test_report_graph_marks_a_strand_with_no_records_instead_of_scoring_it():
    data = {"learner": {"alias": "Learner X-01"},
            "strands": [{"id": "a", "label": "Number", "subject": "maths", "subject_label": "Mathematics", "records": 4, "mean": 0.25},
                        {"id": "b", "label": "Reading and understanding texts", "subject": "language", "subject_label": "Language", "records": 0, "mean": None}]}
    svg = report.graph_svg(data)
    assert ">25%<" in svg and ">none<" in svg and "stroke-dasharray" in svg
    assert ">Mathematics<" in svg and ">Language<" in svg          # two subjects: a ring of subjects, then strands
    assert report.graph_svg({"learner": {"alias": "Learner X-01"}, "strands": []}) == ""

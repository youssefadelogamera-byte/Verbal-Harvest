import pytest

from athar import db, graph


def test_concept_mastery_groups_by_period(db_path):
    mastery = graph.concept_mastery("lrn_a", db_path=db_path)
    assert set(mastery) == {"multiplication", "division", "fractions", "ratios"}
    assert mastery["division"] == [{"period_ord": 2021 * 3 + 1, "period": "2021-T2", "mean": 0.25, "n": 2,
                                    "evidence_ids": ["evd_a03", "evd_a04"]}]
    assert [p["period"] for p in mastery["ratios"]] == ["2023-T1", "2023-T2", "2023-T3"]
    assert mastery["ratios"][0]["evidence_ids"] == ["evd_a09", "evd_a10"]


def test_struggle_patterns_for_ratios_learner(db_path):
    result = graph.find_patterns("lrn_a", db_path=db_path)
    patterns = {(p["scope"], p["scope_id"]): p for p in result["patterns"]}
    assert set(patterns) == {("strand", "number"), ("concept", "ratios")}

    ratios = patterns[("concept", "ratios")]
    assert ratios["kind"] == "struggle"
    assert ratios["periods"] == ["2023-T1", "2023-T2", "2023-T3"]
    assert ratios["evidence_ids"] == ["evd_a09", "evd_a10", "evd_a11", "evd_a12"]
    assert ratios["mean"] == pytest.approx(0.275, abs=1e-3)
    assert ratios["concept_ids"] == ["ratios"]

    number = patterns[("strand", "number")]
    assert number["kind"] == "struggle"
    assert number["periods"] == ["2021-T2", "2022-T1", "2023-T1", "2023-T2", "2023-T3"]
    assert number["evidence_ids"] == ["evd_a03", "evd_a04", "evd_a07", "evd_a08",
                                      "evd_a09", "evd_a10", "evd_a11", "evd_a12"]
    assert number["concept_ids"] == ["ratios", "fractions", "division"]


def test_strength_in_geometry_strand_and_skill(db_path):
    result = graph.find_patterns("lrn_b", db_path=db_path)
    expected_ids = ["evd_b01", "evd_b02", "evd_b03", "evd_b04", "evd_b05", "evd_b06", "evd_b07", "evd_b08"]
    expected_periods = ["2021-T1", "2021-T2", "2021-T3", "2022-T1"]
    assert [(p["kind"], p["scope"], p["scope_id"]) for p in result["patterns"]] == [
        ("strength", "strand", "geometry"), ("strength", "skill", "spatial-reasoning")]
    for pattern in result["patterns"]:
        assert pattern["periods"] == expected_periods
        assert pattern["evidence_ids"] == expected_ids
        assert pattern["n_items"] == 8
        assert pattern["confidence"] == 0.67
        assert pattern["concept_ids"] == ["area", "position-direction", "shapes-2d"]
    assert result["patterns"][1]["label"] == "Spatial reasoning"


def test_too_little_data_gives_no_patterns(db_path):
    result = graph.find_patterns("lrn_e", db_path=db_path)
    assert result["patterns"] == []
    assert result["data_gaps"] == [
        {"period": None, "reason": "only 2 period(s) have scored items; a pattern needs at least 3"}]


def test_data_gaps_list_empty_periods(db_path):
    gaps = graph.find_patterns("lrn_a", db_path=db_path)["data_gaps"]
    assert [g["period"] for g in gaps] == ["2020-T2", "2020-T3", "2021-T1", "2021-T3", "2022-T2", "2022-T3"]


def test_trace_root_finds_division_and_the_absence(db_path):
    result = graph.trace_root("lrn_a", "ratios", db_path=db_path)
    assert result["target"] == {"concept_id": "ratios", "label": "Ratios and proportion", "mean": 0.275, "n": 4}
    assert result["path"] == ["ratios", "fractions", "division"]
    assert result["root"] == {"concept_id": "division", "label": "Division as sharing and grouping", "grade": 3,
                              "mean": 0.25, "n": 2, "period": "2021-T2", "taught_period": "2021-T2",
                              "evidence_ids": ["evd_a03", "evd_a04"]}
    assert result["context"] == [{"type": "absence", "period": "2021-T2", "absent_days": 18,
                                  "evidence_id": "evd_a05"}]
    assert result["root_is_target"] is False and result["root_is_certain"] is True
    assert result["unknowns"] == []
    assert result["unknowns_on_path"] == []
    assert result["unrecorded_prerequisites_of_root"] == []
    assert result["alternatives"] == []
    assert result["evidence_ids"] == ["evd_a03", "evd_a04", "evd_a05", "evd_a07", "evd_a08",
                                      "evd_a09", "evd_a10", "evd_a11", "evd_a12"]
    assert result["confidence"] == 0.6  # root 2 items + target 4 items -> 6 / 10
    assert "18 days of absence were recorded in 2021-T2, when Division" in result["reason"]


def test_trace_root_with_a_hole_in_the_record_is_not_certain(db_path):
    result = graph.trace_root("lrn_d", "ratios", db_path=db_path)
    assert result["path"] == ["ratios", "fractions", "division"]
    assert result["unknowns"] == ["fractions", "multiplication", "addition", "counting"]
    assert result["unknowns_on_path"] == ["fractions"]
    assert result["prerequisites_missing_in_record"] == ["multiplication"]
    assert result["prerequisites_before_record"] == []
    assert result["root"]["concept_id"] == "division"
    assert result["root"]["evidence_ids"] == ["evd_d03", "evd_d04"]
    assert result["root_is_certain"] is False
    assert result["context"] == []
    # Fractions has no records, so the difficulty could also start at ratios itself.
    assert [a["concept_id"] for a in result["alternatives"]] == ["ratios"]
    assert result["evidence_ids"] == ["evd_d03", "evd_d04", "evd_d05", "evd_d06"]
    assert result["confidence"] == 0.35  # 4 items -> 0.5, one gap on the path -> 0.4, capped at 0.35
    assert result["reason"].endswith("there are no records for Multiplication as repeated addition, although "
                                     "the learner was enrolled when it was taught.")


def test_trace_root_target_is_root_when_prerequisites_are_fine(db_path):
    result = graph.trace_root("lrn_b", "multiplication", db_path=db_path)
    assert result["root_is_target"] is True and result["root_is_certain"] is True
    assert result["path"] == ["multiplication"]
    assert result["root"]["concept_id"] == "multiplication"
    assert result["root"]["evidence_ids"] == ["evd_b12", "evd_b13"]
    assert result["root"]["period"] == "2022-T1" and result["root"]["taught_period"] == "2021-T3"
    assert result["context"] == [{"type": "absence", "period": "2021-T3", "absent_days": 1,
                                  "evidence_id": "evd_b14"}]
    assert result["unrecorded_prerequisites_of_root"] == []
    assert result["confidence"] == 0.33  # 2 items -> 2/6
    assert "difficulty starts here" in result["reason"]
    assert "1 day of absence was recorded in 2021-T3" in result["reason"]


def test_trace_root_cannot_tell_when_prerequisite_unrecorded(db_path):
    result = graph.trace_root("lrn_e", "addition", db_path=db_path)
    assert result["root"] is None and result["root_is_target"] is False and result["root_is_certain"] is False
    assert result["confidence"] == 0.0
    assert result["path"] == ["addition"]
    assert result["unknowns"] == ["counting"]
    assert result["unrecorded_prerequisites_of_root"] == ["counting"]
    assert result["evidence_ids"] == ["evd_e01", "evd_e02"]
    assert result["reason"] == ("Addition within 100 is low, but there are no records for Counting to 100 "
                                "(its prerequisite), so where the difficulty began cannot be told from the records.")


def test_prerequisite_before_the_record_is_listed_but_not_capped(db_path):
    with db.connect(db_path) as conn:
        conn.execute("UPDATE learners SET start_grade = 2 WHERE id = 'lrn_e'")
    result = graph.trace_root("lrn_e", "addition", db_path=db_path)
    assert result["root"]["concept_id"] == "addition"
    assert result["root_is_target"] is True and result["root_is_certain"] is True
    assert result["prerequisites_before_record"] == ["counting"]
    assert result["prerequisites_missing_in_record"] == []
    assert result["confidence"] == 0.33
    assert "Records begin in grade 2, so Counting to 100 was taught before the record." in result["reason"]


def test_trace_root_without_evidence_or_struggle(db_path):
    no_data = graph.trace_root("lrn_a", "volume", db_path=db_path)
    assert no_data["root"] is None and no_data["evidence_ids"] == [] and no_data["confidence"] == 0.0
    fine = graph.trace_root("lrn_a", "multiplication", db_path=db_path)
    assert fine["root"] is None and "not low" in fine["reason"]


def test_trace_root_rejects_unknown_ids(db_path):
    with pytest.raises(ValueError, match="Unknown concept"):
        graph.trace_root("lrn_a", "calculus", db_path=db_path)
    with pytest.raises(ValueError, match="Unknown learner"):
        graph.trace_root("lrn_zz", "ratios", db_path=db_path)


def test_what_worked_counts_clear_gains(db_path):
    result = graph.what_worked("lrn_c", db_path=db_path)
    assert [a["approach_id"] for a in result["approaches"]] == ["visual_models", "worked_examples"]
    visual, worked = result["approaches"]
    assert (visual["units"], visual["improved"], visual["not_improved"]) == (2, 2, 0)
    assert visual["mean_gain"] == pytest.approx(0.3225, abs=1e-3)  # (0.42 + 0.225) / 2
    assert visual["instances"] == [
        {"concept_id": "multiplication", "period": "2021-T2", "before": 0.43, "after": 0.85, "unit_id": "unt_c1",
         "baseline_periods": ["2020-T3", "2021-T1"],
         "evidence_ids": ["evd_c08", "evd_c12", "evd_c01", "evd_c02", "evd_c09", "evd_c03", "evd_c04"]},
        {"concept_id": "division", "period": "2022-T1", "before": 0.6, "after": 0.825, "unit_id": "unt_c2",
         "baseline_periods": ["2021-T2", "2021-T3"],
         "evidence_ids": ["evd_c03", "evd_c04", "evd_c05", "evd_c13", "evd_c06", "evd_c07"]},
    ]
    assert (worked["units"], worked["improved"], worked["not_improved"]) == (1, 0, 1)
    assert worked["instances"][0]["before"] == 0.475 and worked["instances"][0]["after"] == 0.55
    assert worked["instances"][0]["baseline_periods"] == ["2020-T2", "2020-T3"]
    assert "does not rate teachers" in result["note"]
    assert "own recent average" in result["note"]


def test_what_worked_skips_thin_baseline(db_path):
    assert graph.what_worked("lrn_a", db_path=db_path)["approaches"] == []


def test_learner_graph_states_and_timeline(db_path):
    result = graph.learner_graph("lrn_d", db_path=db_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    assert nodes["division"]["state"] == "gap"
    assert nodes["fractions"]["state"] == "unseen"
    assert nodes["geometry"]["type"] == "strand"
    assert result["periods"] == ["2021-T1", "2023-T1"]
    assert result["timeline"]["2021-T1"] == {"division": 0.325}
    assert result["timeline"]["2023-T1"] == {"division": 0.325, "ratios": 0.25}
    assert {"source": "division", "target": "fractions", "type": "requires"} in result["edges"]
    assert {"source": "area", "target": "spatial-reasoning", "type": "shows"} in result["edges"]
    strong = {n["id"]: n["state"] for n in graph.learner_graph("lrn_b", db_path=db_path)["nodes"]}
    assert strong["shapes-2d"] == "strong" and strong["addition"] == "shaky"


def test_disposition_skill_never_becomes_a_struggle(db_path):
    with db.connect(db_path) as conn:
        for i, (year, term, score) in enumerate([(2022, 3, 0.2), (2023, 1, 0.3), (2023, 2, 0.1)]):
            conn.execute("INSERT INTO evidence (id, learner_id, kind, year, term, period_ord, grade, skill_id, "
                         "score, source_ref, recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (f"evd_p{i}", "lrn_e", "observation", year, term, db.period_ord(year, term), 1,
                          "persistence", score, f"test:p{i}", db.now_iso()))
    assert graph.find_patterns("lrn_e", db_path=db_path)["patterns"] == []
    with db.connect(db_path) as conn:
        conn.execute("UPDATE evidence SET score = 0.9 WHERE id LIKE 'evd_p%'")
    patterns = graph.find_patterns("lrn_e", db_path=db_path)["patterns"]
    assert [(p["kind"], p["scope_id"]) for p in patterns] == [("strength", "persistence")]

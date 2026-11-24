"""Tests for the agent's deterministic parts. No model and no MCP server needed."""

from types import SimpleNamespace

from athar.agent import workflow
from athar.agent.language import looks_like

QUIZ = """# Quiz sheet

Learner: Learner A-17

| Item | Question | Marks | Out of |
|------|----------|-------|--------|
| 1 | Simplify 12:18 | 1 | 2 |
| 2 | Share 40 in 3:5 | 0 | 3 |
| 3 | Explain | - | 2 |
"""


def test_table_row_count_ignores_header_and_rule():
    assert workflow._table_row_count(QUIZ) == 3
    assert workflow._table_row_count("No table here.") == 0


def test_other_learners_detected():
    learner = {"alias": "Learner A-17"}
    assert not workflow._other_learners_in(QUIZ, learner)
    assert workflow._other_learners_in(QUIZ + "\nLearner T-20 was absent.", learner)


def test_score_is_computed_from_copied_marks():
    row = workflow.EvidenceRow(kind="quiz_item", marks=1, out_of=2, quote="Simplify 12:18")
    assert row.score == 0.5
    assert workflow.EvidenceRow(kind="quiz_item", marks=None, out_of=2, quote="x").score is None
    # Marks above the maximum are a misreading: no score rather than a wrong one.
    assert workflow.EvidenceRow(kind="quiz_item", marks=5, out_of=2, quote="x").score is None


def test_language_check_catches_a_neighbouring_language():
    swahili = ("Mtoto wako anafanya vizuri sana katika jiometri na kazi za maumbo. Matokeo yake ya uwiano "
               "yamekuwa ya chini, na hii inaweza kuwa inatokana na mada ya kugawanya ya darasa la tatu.")
    xhosa = ("Umsombululo wakho kwi-Geometry kunye nokuzibona kwisithuba ubonisa ukuba uyazi kakuhle. "
             "Oku kubonisa ukuba uhlala unenkcubeko ekwenzeni oku.")
    english = "Your child does well in geometry and the work has been strong for several terms."
    assert looks_like(swahili, "sw")
    assert not looks_like(xhosa, "sw")
    assert not looks_like(english, "sw")
    assert looks_like(english, "en")
    assert looks_like("يُظهر عمل طفلك في الهندسة نتائج قوية.", "ar")
    assert not looks_like(english, "ar")


def _pack():
    return SimpleNamespace(label=lambda concept_id, lang="en": concept_id.replace("-", " ").title())


def _traced(target, root, confidence=0.7, evidence=("e1", "e2", "e3")):
    return {"target": {"concept_id": target, "label": target, "mean": 0.3, "n": 4},
            "root": {"concept_id": root, "label": root, "grade": 3, "mean": 0.3, "n": 5, "period": "2021-T1"},
            "path": [target, root], "context": [{"type": "absence", "absent_days": 17}],
            "unrecorded_prerequisites_of_root": [], "evidence_ids": list(evidence), "confidence": confidence}


def test_two_topics_with_the_same_root_give_one_finding():
    analyses = {"roots": {"ratio-concept": _traced("ratio-concept", "division-basic", 0.7),
                          "percentages": _traced("percentages", "division-basic", 0.6)},
                "patterns": {"patterns": []}, "what_worked": {"approaches": []}}
    candidates, questions = workflow._candidates(analyses, _pack())
    assert [c["kind"] for c in candidates] == ["root_cause"]
    assert candidates[0]["concept_ids"] == ["ratio-concept", "division-basic"]   # the more confident one
    assert candidates[0]["evidence_ids"] == ["e1", "e2", "e3"]                   # copied from the tool
    assert questions == []


def test_weak_or_missing_roots_become_open_questions_not_findings():
    no_root = {"target": {"concept_id": "fraction-concept", "label": "Fractions", "mean": 0.3, "n": 6},
               "root": None, "reason": "Fractions is low, but there are no records for Division.",
               "evidence_ids": ["e1"], "confidence": 0.0}
    analyses = {"roots": {"fraction-concept": no_root, "ratio-concept": _traced("ratio-concept", "division-basic", 0.2)},
                "patterns": {"patterns": []}, "what_worked": {"approaches": []}}
    candidates, questions = workflow._candidates(analyses, _pack())
    assert candidates == []
    assert len(questions) == 2
    assert "no records" in questions[0]


def test_root_over_a_hole_in_the_record_becomes_a_question():
    uncertain = {**_traced("percentages", "fraction-concept", 0.35), "root_is_certain": False,
                 "reason": "Percentages is low. The difficulty may begin earlier: there are no records for Division."}
    analyses = {"roots": {"percentages": uncertain}, "patterns": {"patterns": []}, "what_worked": {"approaches": []}}
    candidates, questions = workflow._candidates(analyses, _pack())
    assert candidates == []
    assert questions == [uncertain["reason"]]


def test_same_evidence_is_one_claim():
    def strength(label, ids, confidence):
        return {"kind": "strength", "scope": "strand", "scope_id": label, "label": label, "periods": ["a", "b", "c"],
                "mean": 0.9, "n_items": len(ids), "evidence_ids": ids, "confidence": confidence, "concept_ids": []}
    geometry = strength("geometry", [f"e{i}" for i in range(22)], 0.85)
    spatial = strength("spatial-reasoning", [f"e{i}" for i in range(19)], 0.83)      # a subset of geometry's rows
    number = strength("number", [f"n{i}" for i in range(10)], 0.7)
    analyses = {"roots": {}, "patterns": {"patterns": [geometry, spatial, number]}, "what_worked": {"approaches": []}}
    candidates, _ = workflow._candidates(analyses, _pack())
    assert [c["facts"]["in"] for c in candidates] == ["geometry", "number"]


def test_a_note_may_not_add_numbers():
    source = "Results in geometry averaged 91% across five terms. Division averaged 33% in 2021."
    assert workflow._numbers_not_in("Your child's geometry results averaged 91%.", source) == []
    assert workflow._numbers_not_in("Practise for 5 minutes each day; geometry is at 91%.", source) == ["5"]
    assert workflow._numbers_not_in("متوسط النتائج ٩١٪", source) == []          # Arabic-Indic digits are read too


def test_what_worked_needs_more_wins_than_losses():
    def approach(improved, not_improved):
        return {"approach_id": "x", "label": "Hands-on objects", "improved": improved, "not_improved": not_improved,
                "mean_gain": 0.2, "instances": [{"concept_id": "volume", "evidence_ids": ["e1", "e2"]}]}
    base = {"roots": {}, "patterns": {"patterns": []}}
    assert workflow._candidates({**base, "what_worked": {"approaches": [approach(3, 0)]}}, _pack())[0][0]["kind"] == "what_worked"
    assert workflow._candidates({**base, "what_worked": {"approaches": [approach(1, 0)]}}, _pack())[0] == []
    assert workflow._candidates({**base, "what_worked": {"approaches": [approach(2, 4)]}}, _pack())[0] == []


def test_a_handover_note_must_not_be_written_to_a_parent():
    to_parent = "Your child demonstrates strong potential but struggles with ratio comparisons."
    assert workflow._speaks_to_wrong_reader(to_parent, "teacher_handover")
    assert not workflow._speaks_to_wrong_reader(to_parent, "guardian")
    assert not workflow._speaks_to_wrong_reader("This learner's ratio results have been low.", "teacher_handover")


def test_a_shortened_alias_is_still_the_same_learner():
    # Found by running a teacher note by hand: the model read "Learner C-31" as "C-31"
    # and the whole note was refused as belonging to someone else.
    assert workflow._same_learner("C-31", "Learner C-31")
    assert workflow._same_learner("learner c-31", "Learner C-31")
    assert workflow._same_learner(None, "Learner C-31")
    assert not workflow._same_learner("C-13", "Learner C-31")
    assert not workflow._same_learner("Learner A-17", "Learner C-31")
    assert not workflow._same_learner("Amina", "Learner C-31")


def test_grade_comes_from_enrolment_when_the_document_gives_none():
    learner = {"start_year": 2021, "start_grade": 3}
    assert workflow._grade_in(learner, 2025) == 7
    assert workflow._grade_in(learner, 2021) == 3
    assert workflow._grade_in({"grade_now": 6}, 2025) == 6
    assert workflow._grade_in({}, 2025) is None


def test_load_learner_takes_the_current_grade_from_the_latest_record():
    """The learner row has no current grade. Without one, the model is offered every topic in the pack."""
    import asyncio

    class Hub:
        def __init__(self, items):
            self.items = items

        async def call(self, tool, **kwargs):
            assert tool == "get_learner_timeline"
            periods = [{"period": "2025-T1", "items": self.items}] if self.items else []
            return {"learner": {"alias": "Learner A-17", "start_grade": 3}, "periods": periods}

    for items, expected in (([{"grade": 6}], 6), ([], 3), ([{"grade": 0}], 3)):
        workflow.RESOURCES["run_test"] = {"hub": Hub(items), "llm": None, "usage": None}
        try:
            out = asyncio.run(workflow.load_learner({"run_id": "run_test", "learner_id": "lrn_x"}))
        finally:
            workflow.RESOURCES.pop("run_test")
        assert out["learner"]["grade_now"] == expected


# ---------------------------------------------------------------- asking for a missing record

class _Pack:
    """The two things the loop needs from a curriculum pack."""
    def __init__(self):
        self.concepts = {"decimals": SimpleNamespace(grade=5), "division": SimpleNamespace(grade=3),
                         "place-value": SimpleNamespace(grade=2)}

    def label(self, concept_id, lang=None):
        return concept_id.replace("-", " ").title()


class _LoopHub:
    """Stands in for the MCP server: remembers calls and serves record requests."""
    db_path = None

    def __init__(self, requests=None, refuse=False):
        self.requests, self.calls, self.refuse = list(requests or []), [], refuse

    async def call(self, tool, **kwargs):
        self.calls.append((tool, kwargs))
        if tool == "get_record_requests":
            wanted = kwargs.get("request_ids")
            return {"requests": [r for r in self.requests if wanted is None or r["request_id"] in wanted]}
        if tool == "request_record":
            if self.refuse:
                raise workflow.ToolError("The question was rejected: label on a child")
            return {"request_id": "req_1", "status": "open", "warnings": []}
        raise AssertionError(tool)


def _loop(node, hub, state, monkeypatch):
    import asyncio
    monkeypatch.setattr(workflow, "load_pack", lambda _pack_id: _Pack())
    workflow.RESOURCES["run_loop"] = {"hub": hub, "llm": None, "usage": None}   # no model: wording falls back
    try:
        return asyncio.run(node({"run_id": "run_loop", "learner_id": "lrn_x", "learner": {"pack_id": "p"}, **state}))
    finally:
        workflow.RESOURCES.pop("run_loop")


GAP = {"roots": {"decimals": {"prerequisites_missing_in_record": ["division"]},
                 "fractions": {"prerequisites_missing_in_record": ["division", "place-value"]},
                 "angles": {"prerequisites_missing_in_record": []}}}


def test_record_gaps_lists_each_missing_topic_once():
    assert workflow._record_gaps(GAP) == [{"concept_id": "division", "about": "decimals"},
                                          {"concept_id": "place-value", "about": "fractions"}]
    assert workflow._record_gaps({"roots": {}}) == [] and workflow._record_gaps({}) == []


def test_agent_asks_a_teacher_when_a_record_is_missing(monkeypatch):
    hub = _LoopHub()
    out = _loop(workflow.ask_for_records, hub, {"analyses": GAP}, monkeypatch)
    assert out["open_request"] == {"request_id": "req_1", "concept_id": "division", "about": "decimals"}
    assert out["request_ids"] == ["req_1"]
    tool, sent = hub.calls[-1]
    assert tool == "request_record" and sent["concept_id"] == "division" and sent["about_concept_id"] == "decimals"
    assert "Division" in sent["question"] and "?" in sent["question"]          # the template, with no model
    assert not workflow.guard.check_statement(sent["question"])
    assert workflow._after_ask(out) == "teacher_gate_records"


def test_agent_does_not_ask_again_or_without_end(monkeypatch):
    answered = [{"request_id": "req_0", "concept_id": "division", "status": "no_record"},
                {"request_id": "req_9", "concept_id": "place-value", "status": "provided"}]
    hub = _LoopHub(answered)
    out = _loop(workflow.ask_for_records, hub, {"analyses": GAP}, monkeypatch)
    assert out["open_request"] is None and "Not asked again" in out["steps"][0]["note"]
    assert [tool for tool, _ in hub.calls] == ["get_record_requests"]
    assert workflow._after_ask(out) == "compose_findings"

    hub = _LoopHub()
    capped = _loop(workflow.ask_for_records, hub, {"analyses": GAP, "request_ids": ["req_a", "req_b"]}, monkeypatch)
    assert capped["open_request"] is None and "open question" in capped["steps"][0]["note"]
    assert "request_record" not in [tool for tool, _ in hub.calls]

    nothing = _loop(workflow.ask_for_records, _LoopHub(), {"analyses": {"roots": {}}}, monkeypatch)
    assert nothing == {"open_request": None}


def test_a_refused_question_does_not_stop_the_run(monkeypatch):
    out = _loop(workflow.ask_for_records, _LoopHub(refuse=True), {"analyses": GAP}, monkeypatch)
    assert out["open_request"] is None and out["steps"][0]["ok"] is False


def test_gate_passes_the_teachers_answer_on(monkeypatch):
    answered = {"request_id": "req_1", "concept_id": "division", "status": "provided", "answer_text": "Q1 1 out of 2",
                "answered_by_name": "Jean"}
    out = _loop(workflow.teacher_gate_records, _LoopHub([answered]),
                {"open_request": {"request_id": "req_1", "concept_id": "division", "about": "decimals"}}, monkeypatch)
    assert out["open_request"]["status"] == "provided" and out["open_request"]["about"] == "decimals"


def test_a_supplied_record_goes_round_again_and_no_record_does_not(monkeypatch):
    request = {"request_id": "req_1", "concept_id": "division", "about": "decimals", "answered_by_name": "Jean"}
    given = _loop(workflow.read_answer, _LoopHub(), {"open_request": {
        **request, "status": "provided", "answer_text": "Q1 1 out of 2", "answer_year": 2022, "answer_term": 2}}, monkeypatch)
    assert given["document_text"] == "Q1 1 out of 2" and given["inbox_file"] == "teacher_answer_req_1.txt"
    assert given["answer_hint"] == {"concept_id": "division", "year": 2022, "term": 2}
    assert given["open_request"] is None and "Jean supplied" in given["steps"][0]["note"]
    assert workflow._after_answer(given) == "extract_evidence"

    none = _loop(workflow.read_answer, _LoopHub(), {"open_request": {**request, "status": "no_record"}}, monkeypatch)
    assert none["document_text"] == "" and none["recorded"] == [] and "will not be asked again" in none["steps"][0]["note"]
    assert workflow._after_answer(none) == "ask_for_records"


def test_the_graph_has_the_loop_back_to_reading():
    drawn = workflow.build_graph().compile().get_graph()
    edges = {(e.source, e.target) for e in drawn.edges}
    assert {("investigate", "ask_for_records"), ("ask_for_records", "teacher_gate_records"),
            ("ask_for_records", "compose_findings"), ("teacher_gate_records", "read_answer"),
            ("read_answer", "extract_evidence"), ("read_answer", "ask_for_records")} <= edges


def test_one_open_question_per_hole_in_the_record():
    """Five topics that all run into the same missing record are one question for the teacher, not five."""
    def traced(topic):
        return {"root": {"concept_id": "fractions", "label": "Fractions"}, "root_is_certain": False,
                "prerequisites_missing_in_record": ["division"], "reason": f"{topic} is low. No records for division."}
    analyses = {"roots": {t: traced(t) for t in ("decimals", "ratio", "percentages")}}
    analyses["roots"]["area"] = {"root": {"concept_id": "length", "label": "Length"}, "root_is_certain": False,
                                 "prerequisites_missing_in_record": ["units"], "reason": "Area is low. No records for units."}
    candidates, questions = workflow._candidates(analyses, _Pack())
    assert candidates == []
    assert questions == ["decimals is low. No records for division.", "Area is low. No records for units."]


def test_coverage_check_picks_clearly_low_topics():
    """At most two topics, lowest first, only with enough scored items, never one already traced."""
    from athar.agent.workflow import _clearly_low
    item = lambda concept, score: {"concept_id": concept, "score": score}
    timeline = {"periods": [{"period": "2025-T1", "items": [
        *[item("a", 0.2)] * 3, *[item("b", 0.35)] * 4, *[item("c", 0.1)] * 2, *[item("d", 0.45)] * 5,
        *[item("e", 0.3)] * 3, item(None, 0.0), item("a", None)]}]}
    assert _clearly_low(timeline, skip=set()) == ["a", "e"]
    assert _clearly_low(timeline, skip={"a"}) == ["e", "b"]
    assert _clearly_low({"periods": []}, skip=set()) == []


def test_arabic_wording_uses_the_arabic_topic_names():
    """With the school's language set to Arabic, names in the facts and the fallback wording are Arabic."""
    from athar import guard
    from athar.agent.language import looks_like
    from athar.agent.workflow import _template_question, _template_statement, in_language
    from athar.curriculum import load_pack
    pack = load_pack("egypt-maths")
    some = next(iter(pack.concepts))
    english = pack.label(some, "en")
    candidate = {"kind": "strength", "facts": {"in": english, "terms": ["2021-T1", "2021-T2", "2021-T3"],
                                               "average": 0.91, "items": 12, "topics": [english]}}
    assert in_language(candidate, pack, "en") is candidate
    arabic = in_language(candidate, pack, "ar")
    assert arabic["lang"] == "ar" and arabic["facts"]["in"] == pack.label(some, "ar") == arabic["facts"]["topics"][0]
    text = _template_statement(arabic)
    assert looks_like(text, "ar") and "91%" in text and "12" in text
    root = {"kind": "root_cause", "lang": "ar", "facts": {"struggling_with": "النسبة", "possible_root": "القسمة",
                                                         "root_average": 0.27, "root_period": "2023-T2"}}
    said = _template_statement(root)
    assert "قد ترجع إلى القسمة" in said and "27%" in said and "2023-T2" in said
    asked = _template_question("النسبة", "القسمة", 5, "ar")
    assert "؟" in asked and looks_like(asked, "ar")
    assert not guard.check_statement(said) and not guard.check_statement(asked) and not guard.check_statement(text)

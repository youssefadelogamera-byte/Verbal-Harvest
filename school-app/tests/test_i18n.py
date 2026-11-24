"""The Arabic dictionaries on the server, and the printable report in Arabic."""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path

import pytest

from athar import i18n, report, review, tools
from athar.curriculum import current_lang


def sample_reports() -> list[dict]:
    """Two hand-made reports that between them reach every sentence the report can write."""
    explained = {
        "facts": ["Results in Ratios and proportion are low now: 28% over 4 records.",
                  "Ratios and proportion builds on Division as sharing and grouping, through Fractions of a whole.",
                  "18 days of absence were recorded in 2021-T2.",
                  "A sentence <no dictionary> will ever hold."],
        "series": [{"period": "2021-T2", "mean": 0.25, "records": 2}, {"period": "2023-T1", "mean": 0.25, "records": 2},
                   {"period": "2023-T3", "mean": 0.9, "records": 1}],
        "chain": [{"id": "division", "label": "Division as sharing and grouping", "grade": 3, "mean": 0.25, "records": 2,
                   "first_period": "2021-T2"},
                  {"id": "fractions", "label": "Fractions of a whole", "grade": 4, "mean": None, "records": 0,
                   "first_period": None},
                  {"id": "ratios", "label": "Ratios & proportion", "grade": 5, "mean": 0.275, "records": 4,
                   "first_period": "2023-T1"}],
        "days_absent": 18, "records": 5}
    records = [
        {"id": "evd_a03", "period": "2021-T2", "kind": "quiz_item", "topic": "Division as sharing and grouping",
         "score": 0.3, "absent_days": None, "text": None, "language": "en", "source": "test:evd_a03"},
        {"id": "evd_a05", "period": "2021-T2", "kind": "attendance", "topic": "", "score": None, "absent_days": 18,
         "text": None, "language": "en", "source": "test:evd_a05"},
        {"id": "evd_a06", "period": "2022-T1", "kind": "attendance", "topic": "", "score": None, "absent_days": None,
         "text": None, "language": "en", "source": "test:evd_a06"},
        {"id": "evd_a13", "period": "2023-T3", "kind": "observation", "topic": "Ratios & proportion", "score": None,
         "absent_days": None, "text": "يجد صعوبة في مقارنة الكميات", "language": "ar", "source": "test:evd_a13"},
        {"id": "evd_a14", "period": "2023-T3", "kind": "assignment", "topic": "Ratios & proportion", "score": 0.5,
         "absent_days": None, "text": "Shows <working>", "language": "en", "source": "test:evd_a14"},
        {"id": "evd_a15", "period": "2023-T3", "kind": "project", "topic": "Ratios & proportion", "score": 1.0,
         "absent_days": None, "text": None, "language": "en", "source": "test:evd_a15"},
        {"id": "evd_a16", "period": "2023-T3", "kind": "oral", "topic": "Ratios & proportion", "score": 0.0,
         "absent_days": None, "text": None, "language": "en", "source": "test:evd_a16"},
    ]
    full = {
        "strands": [
            {"id": "number", "label": "Number", "subject": "maths", "subject_label": "Mathematics", "records": 9, "mean": 0.41},
            {"id": "geometry", "label": "Geometry and measurement of shapes", "subject": "maths",
             "subject_label": "Mathematics", "records": 3, "mean": 0.92},
            {"id": "reading", "label": "Reading", "subject": "language", "subject_label": "Language", "records": 0, "mean": None},
            {"id": "writing", "label": "Writing", "subject": "language", "subject_label": "Language", "records": 1, "mean": 0.6}],
        "learner": {"learner_id": "lrn_a", "alias": "Learner A-01", "name": "Salma O'Neil", "home_language": "ar",
                    "grade_now": 5, "curriculum": "Mini mathematics, grades 1 to 6 (test pack)"},
        "span": {"records": 13, "terms": 6, "days_absent": 20, "first_period": "2020-T1", "last_period": "2023-T3"},
        "findings": [
            {"explain": {"facts": ["3 records across 2 terms, from 2021-T1 to 2021-T2.", "They average 90%."],
                         "series": [{"period": "2021-T1", "mean": 0.88, "records": 2}], "chain": [], "days_absent": 0,
                         "records": 3},
             "id": "fnd_1", "kind": "strength", "statement": "Geometry results stayed high for four terms.",
             "teacher": "Amina Okafor", "decided_at": "2024-02-03T09:10:11+00:00", "edited": False, "note": None,
             "records": records[:1], "records_total": 14},
            {"explain": explained, "id": "fnd_2", "kind": "root_cause",
             "statement": "Ratio items trace back to <b>division</b>, first met in a term with 18 days absent.",
             "teacher": "Jean D'Arc", "decided_at": "2024-02-04T09:10:11+00:00", "edited": True,
             "note": "Checked with the class book & the register.", "records": records, "records_total": 7},
            {"explain": None, "id": "fnd_3", "kind": "struggle", "statement": "Results on ratio items stayed low.",
             "teacher": None, "decided_at": None, "edited": False, "note": None, "records": [], "records_total": 0},
            {"explain": {"facts": [], "series": [], "chain": [], "days_absent": 0, "records": 0}, "id": "fnd_4",
             "kind": "what_worked", "statement": "Gains followed units taught with visual models.", "teacher": "Jean D'Arc",
             "decided_at": "2024-02-05T09:10:11+00:00", "edited": False, "note": None, "records": records[4:5],
             "records_total": 1},
            {"id": "fnd_5", "kind": "other_kind", "statement": "A kind the report has no title for.", "teacher": "Jean D'Arc",
             "decided_at": "2024-02-05T09:10:11+00:00", "edited": False, "note": None, "records": [], "records_total": 0}],
        "notes": [
            {"audience": "guardian", "language": "ar", "text": "ابنتكم تتقدم جيدا في الهندسة.", "decided_at": "2024-02-06T08:00:00+00:00",
             "teacher": "Amina Okafor"},
            {"audience": "teacher_handover", "language": "en", "text": "Start with division before <ratios>.",
             "decided_at": None, "teacher": None},
            {"audience": "school_office", "language": "fr", "text": "Une note.", "decided_at": "2024-02-06T08:00:00+00:00",
             "teacher": "Jean D'Arc"}],
        "gaps": [{"topic": "Volume of cuboids", "answered": True, "teacher": "Jean D'Arc", "answered_at": "2024-01-09T08:00:00+00:00"},
                 {"topic": "Area <of> rectangles", "answered": True, "teacher": None, "answered_at": None},
                 {"topic": "Counting to 100", "answered": False, "teacher": None, "answered_at": None}],
        "waiting": 3,
        "generated_at": "2024-02-07T10:22:33+00:00",
    }
    bare = {
        "strands": [{"id": "number", "label": "Number", "subject": None, "subject_label": None, "records": 2, "mean": 0.25}],
        "learner": {"learner_id": "lrn_e", "alias": "Learner E-05", "name": "Learner E-05", "home_language": "en",
                    "grade_now": 1, "curriculum": "Mini mathematics, grades 1 to 6 (test pack)"},
        "span": {"records": 0, "terms": 0, "days_absent": 0, "first_period": None, "last_period": None},
        "findings": [], "notes": [], "gaps": [], "waiting": 1, "generated_at": "2024-02-07T10:22:33+00:00",
    }
    return [full, bare]


# ---------------------------------------------------------------- reading a page the way a reader does

AR_REPORT = Path(i18n.__file__).parent / "web" / "static" / "ar-report.json"
ENGLISH_SAMPLES_SHA256 = "bebfe3f25ba1217f0c60db98eb3fb46c7a13c43e762fdfe8b6d6e6a57e87bf72"
LATIN = re.compile(r"[A-Za-z]{3,}")
CODES = re.compile(r"\b\d{2,4}-T\d\b|\b[A-Z]-\d+\b")       # term codes such as 2023-T2, record codes such as A-01
MARKS = dict.fromkeys(map(ord, "\u202b\u202c\u2066\u2069"))     # direction marks: not text


def data_strings(data) -> set[str]:
    """Every string that is data and so stays as written: names, statements, a teacher's words, topic labels.
    The kind of a finding or record and the audience of a note are left out, because the report words those."""
    found: set[str] = set()

    def walk(value, key=None):
        if isinstance(value, dict):
            for k, v in value.items():
                if k not in ("facts", "kind", "audience"):
                    walk(v, k)
        elif isinstance(value, list):
            for v in value:
                walk(v, key)
        elif isinstance(value, str) and len(value) > 2:      # a language code such as "ar" is no word
            found.add(value[:140] if key == "text" else value)
            if key == "label":
                found.update(report._wrap(value))          # a strand label is drawn on up to two lines
            if key in ("name", "alias"):
                found.update(value.split())                # the picture shows a first name or the record code
    walk(data)
    return found


def read_page(page: str, data, also: tuple[str, ...] = ()) -> tuple[list[str], list[str]]:
    """What is left in Latin letters once data is taken out: (the report's own text, sentences from explain.py).
    It reads the visible text and the aria-labels, and skips the style sheet and the record id cells."""
    known = sorted(data_strings(data) | set(also), key=len, reverse=True)

    def leftover(piece: str) -> str | None:
        piece = html.unescape(piece).translate(MARKS)
        for value in known:
            piece = piece.replace(value, " ")
        return piece.strip() if LATIN.search(CODES.sub(" ", piece)) else None

    page = re.sub(r"<style>.*?</style>", "", page, flags=re.DOTALL)
    page = re.sub(r'<td class="id">.*?</td>', "", page, flags=re.DOTALL)
    facts = [li for ul in re.findall(r'<div class="why">.*?<ul>(.*?)</ul>', page, flags=re.DOTALL)
             for li in re.findall(r"<li>(.*?)</li>", ul, flags=re.DOTALL)]
    page = re.sub(r'(<div class="why">.*?)<ul>.*?</ul>', r"\1", page, flags=re.DOTALL)
    pieces = re.findall(r'aria-label="([^"]*)"', page) + re.split(r"<[^>]+>", page)
    return ([left for left in map(leftover, pieces) if left], [left for left in map(leftover, facts) if left])


@pytest.fixture
def no_logo(monkeypatch):
    monkeypatch.setattr(report, "_logo", lambda: "")      # the wordmark holds the Latin word "Athar"


@pytest.fixture
def dictionaries(tmp_path, monkeypatch):
    """A static folder of our own, so these tests do not depend on the wording that ships."""
    monkeypatch.setattr(i18n, "STATIC_DIR", tmp_path)
    i18n.reset()
    yield tmp_path
    i18n.reset()


def _write(folder: Path, name: str, exact=None, patterns=None) -> None:
    (folder / name).write_text(json.dumps({"exact": exact or {}, "patterns": patterns or [], "fragments": {"Term": "x"}},
                                          ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- i18n.tr

def test_tr_looks_up_exact_strings_then_patterns_and_leaves_the_rest(dictionaries):
    _write(dictionaries, "ar-report.json", {"Records": "السجلات"},
           [{"re": "^Followed (\\S+) to (\\S+)\\.$", "ar": "من $1 إلى $2."},
            {"re": "^(?<n>\\d+)% of \\$(\\d+)$", "ar": "$$$2: $<n>% ($&) $9"},
            {"re": "^broken (", "ar": "never"}, {"re": "^Records$", "ar": "exact comes first"}])
    assert i18n.tr("Records", "ar") == "السجلات"
    assert i18n.tr("  Records\n", "ar") == "  السجلات\n"                      # matched trimmed, spaces kept
    assert i18n.tr("Followed 2020-T1 to 2023-T3.", "ar") == "من 2020-T1 إلى 2023-T3."
    assert i18n.tr("40% of $5", "ar") == "$5: 40% (40% of $5) $9"            # JavaScript's $1, $<name>, $& and $$
    assert i18n.tr("Followed a b to c.", "ar") == "Followed a b to c."         # a pattern must match the whole string
    assert i18n.tr("Unknown sentence.", "ar") == "Unknown sentence." and i18n.tr("", "ar") == ""
    assert i18n.tr("Term", "ar") == "Term"                                     # fragments are for the page, not the server
    assert i18n.tr("Records") == "Records" and i18n.tr("Records", "en") == "Records"
    token = current_lang.set("ar")
    try:
        assert i18n.tr("Records") == "السجلات" and i18n.tr("Records", "en") == "Records"
    finally:
        current_lang.reset(token)


def test_tr_reads_the_dictionaries_in_order_and_skips_missing_or_broken_files(dictionaries):
    assert i18n.tr("Records", "ar") == "Records"                               # no dictionary at all does not raise
    (dictionaries / "ar-report.json").write_text("{ not json", encoding="utf-8")
    (dictionaries / "ar.json").write_text('["a list"]', encoding="utf-8")
    _write(dictionaries, "ar-server.json", {"Records": "من الخادم"}, [{"re": "^(\\d+) days$", "ar": "$1 يوم"}])
    assert i18n.tr("Records", "ar") == "Records"                               # loaded once: the files are not read again
    i18n.reset()
    assert i18n.tr("Records", "ar") == "من الخادم" and i18n.tr("3 days", "ar") == "3 يوم"
    _write(dictionaries, "ar-report.json", {"Records": "من التقرير"})
    _write(dictionaries, "ar.json", {"Records": "من الصفحة", "Sign in": "تسجيل الدخول"})
    i18n.reset()
    assert i18n.tr("Records", "ar") == "من التقرير" and i18n.tr("3 days", "ar") == "3 يوم"
    assert i18n.tr("Sign in", "ar") == "تسجيل الدخول"


def test_the_report_dictionary_is_well_formed():
    words = json.loads(AR_REPORT.read_text(encoding="utf-8"))
    assert words["exact"] and words["patterns"]
    for entry in words["patterns"]:
        groups = re.compile(i18n.python_regex(entry["re"])).groups              # every pattern compiles in Python
        assert entry["re"].startswith("^") and entry["re"].endswith("$")
        assert all(int(n) <= groups for n in re.findall(r"\$(\d+)", entry["ar"])), entry
    values = list(words["exact"].values()) + [entry["ar"] for entry in words["patterns"]]
    for value in values:
        assert not set(value) & set("\u0640—–"), value                  # no tatweel, em dash or en dash
        assert not LATIN.search(re.sub(r"</?strong>", "", value)), value
    assert all(key == " ".join(key.split()) for key in words["exact"])


# ---------------------------------------------------------------- the report in English and in Arabic

def test_english_report_is_exactly_what_it_was_before_arabic(no_logo):
    """The hash pins the English report. It was taken again when the colours changed to those of Learning International Schools. If you change
    the English wording or the look on purpose, render the samples again and replace it."""
    pages = "".join(report.render_html(data) for data in sample_reports())
    assert hashlib.sha256(pages.encode("utf-8")).hexdigest() == ENGLISH_SAMPLES_SHA256
    assert "".join(report.render_html(data, lang="en") for data in sample_reports()) == pages
    assert pages.count('<html lang="en"><head>') == 2 and "[dir=rtl]" not in pages and "\u202b" not in pages and "\u2066" not in pages


def test_arabic_report_is_right_to_left_and_worded_in_arabic(no_logo):
    full, bare = sample_reports()
    page = report.render_html(full, lang="ar")
    assert current_lang.get() == "en"                                           # the language is put back afterwards
    assert page.startswith('<!doctype html>\n<html lang="ar" dir="rtl">')
    for expected in ("<h2>ما تظهره السجلات</h2>", "<h2>ما اعتمده المدرسون</h2>", "<h2>الرسائل والمذكرات</h2>",
                     "<h2>ما لا تستطيع السجلات أن تبينه</h2>", "<h1>تقرير التعلم: Salma O&#x27;Neil</h1>",
                     "بداية الصعوبة المحتملة", "هذه ليست مقارنة مع أي تلميذ آخر", "<th>رقم السجل</th>", "بدأت هنا",
                     "تم التعديل والاعتماد بواسطة Jean D&#x27;Arc بتاريخ 2024-02-04.", "عدد السجلات التي يستند إليها: 7.",
                     "لا توجد سجلات لموضوع <strong>Area &lt;of&gt; rectangles</strong>.", "طباعة أو حفظ كملف"):
        assert expected in page, expected
    # Data stays as it was written, and is still escaped.
    assert "Ratio items trace back to &lt;b&gt;division&lt;/b&gt;" in page and "<b>division</b>" not in page
    assert "Checked with the class book &amp; the register." in page and "ابنتكم تتقدم جيدا في الهندسة." in page
    # Right to left: Arabic fonts, no spaced-out or upper-cased Arabic, charts keep their own direction,
    # the chain's arrow points left, and a term code is kept in one piece.
    for rule in ("[dir=rtl] body{font-family:'Segoe UI',Tahoma,'Noto Sans Arabic',Arial", "letter-spacing:0;text-transform:none",
                 "[dir=rtl] svg{direction:ltr}", '[dir=rtl] .arrow::after{content:" \\2190"}', "[dir=rtl] th{"):
        assert rule in page, rule
    assert "<td>\u20662021-T2\u2069</td>" in page and ">\u202bتلميذ\u202c</text>" in page and ">\u202bلا يوجد\u202c</text>" in page
    assert 'aria-label="النتائج حسب الترم: \u20662021-T2\u2069 25%، ' in page
    assert "<script" not in page and "http://" not in page and "—" not in page and "–" not in page

    ours, facts = read_page(page, full, also=("oral", "other_kind", "school_office"))
    assert ours == []                                                           # nothing of the report's own is left in English
    assert "A sentence <no dictionary> will ever hold." in facts               # an unknown sentence is shown, not dropped
    ours, facts = read_page(report.render_html(bare, lang="ar"), bare)
    assert ours == [] and facts == []
    assert "لا توجد سجلات مؤرخة حتى الآن." in report.render_html(bare, lang="ar")
    # The helper does notice English when it is there.
    ours, facts = read_page(report.render_html(full), full, also=("oral", "other_kind", "school_office"))
    assert len(ours) > 40 and len(facts) == 6


def test_arabic_report_from_the_records(db_path, no_logo):
    made = tools.propose_finding(
        learner_id="lrn_a", kind="root_cause", evidence_ids=["evd_a03", "evd_a04", "evd_a05"],
        statement="Ratio items trace back to division, first met in a term with 18 days absent.",
        concept_ids=["ratios", "division"], path=["ratios", "fractions", "division"], confidence=0.67, db_path=db_path)
    review.decide_finding(made["finding_id"], "approved", "tch_jean", note="Checked with the class book.", db_path=db_path)
    english = report.build("lrn_a", db_path=db_path)
    token = current_lang.set("ar")
    try:
        data = report.build("lrn_a", db_path=db_path)
        page = report.render_html(data)
    finally:
        current_lang.reset(token)
    assert {k: v for k, v in data.items() if k != "generated_at"} == {k: v for k, v in english.items() if k != "generated_at"}
    assert '<html lang="ar" dir="rtl">' in page and "تم الاعتماد بواسطة Jean Dupont بتاريخ" in page and "evd_a03" in page
    assert "<td>أيام الغياب: 18</td>" in page and "بداية الصعوبة المحتملة" in page
    ours, _facts = read_page(page, data)
    assert ours == []          # sentences from explain.py may still be English while their dictionary is being written


def test_every_arabic_dictionary_is_well_formed():
    """The page reads these files as they are. A broken pattern would be skipped in silence, so check here."""
    import json
    from pathlib import Path

    import athar
    static = Path(athar.__file__).parent / "web" / "static"
    for name in ("ar.json", "ar-server.json", "ar-report.json"):
        data = json.loads((static / name).read_text(encoding="utf-8"))
        assert set(data) <= {"exact", "patterns", "fragments"}, name
        for entry in data.get("patterns", []):
            re.compile(entry["re"])
            assert entry["ar"].strip(), (name, entry["re"])
        values = [*data.get("exact", {}).values(), *data.get("fragments", {}).values(), *(p["ar"] for p in data.get("patterns", []))]
        assert values and all(isinstance(v, str) and v.strip() for v in values), name
        assert not any(mark in v for v in values for mark in ("\u0640", "\u2014", "\u2013")), name
        assert all(len(key) >= 4 for key in data.get("fragments", {})), name

"""A made-up family, for looking around and for pictures.

`athar family-demo` puts the app in family mode with an invented parent and three invented children:

- one with three school years of results and a difficulty that began two grades earlier,
- one with three years of results and an area that stays strong,
- one who has just been added, with too few marks to say anything about.

The marks are written through the same doors a parent uses (`family.add_results`, `family.add_note`), so the
pages show exactly what a real family would see. Nothing here is about a real child, and no model is used.
"""

from __future__ import annotations

import random
from typing import Any

from . import audit, db, family, story
from .config import get_settings
from .curriculum import Pack, load_pack

ACTOR = "demo-setup"
SUBJECTS = {"maths": {"en": "Maths", "ar": "الرياضيات"}, "sci": {"en": "Science", "ar": "العلوم"},
            "eng": {"en": "English", "ar": "اللغة الإنجليزية"}, "ara": {"en": "Arabic", "ar": "اللغة العربية"},
            "soc": {"en": "Social Studies", "ar": "الدراسات الاجتماعية"}}
PAPERS = ({"en": "monthly test", "ar": "اختبار الشهر"}, {"en": "end of term exam", "ar": "امتحان آخر الترم"})
WORDS = {
    "en": {"parent": "Mona", "children": ("Salma", "Youssef", "Laila"),
           "notes": (("She understands fractions when we cut real things, but loses marks in the written steps.",
                      "We went back to the grade 5 pages for ten minutes a day. She was quicker by the second week."),
                     ("He explains science experiments out loud very well. Writing the answer down takes him longer.",),
                     ()),
           "approved": "Recorded by the demo setup, not by a real parent."},
    "ar": {"parent": "منى", "children": ("سلمى", "يوسف", "ليلى"),
           "notes": (("بتفهم الكسور لما بنقسم حاجات حقيقية، بس بتخسر درجات في الخطوات المكتوبة.",
                      "رجعنا لصفحات الصف الخامس عشر دقايق كل يوم. بقت أسرع من تاني أسبوع."),
                     ("بيشرح تجارب العلوم بصوت عالي كويس جدا. كتابة الإجابة بتاخد منه وقت أطول.",),
                     ()),
           "approved": "سُجّل ضمن إعداد العرض التجريبي، وليس بقرار ولي أمر حقيقي."},
}


def subject_of(concept_id: str) -> str:
    """The subject a topic belongs to, read from the start of its id (maths ids start with the grade)."""
    head = concept_id.split("-")[0]
    return "maths" if head[:1] == "g" and head[1:].isdigit() else head


def _chain(pack: Pack, subject: str, grade: int) -> list[str]:
    """A run of topics in one subject where each needs the one before, ending in `grade` and starting as many
    grades earlier as the map allows. This is where the made-up difficulty is planted."""
    def back(cid: str) -> list[str]:
        best: list[str] = []
        for need in sorted(pack.concepts[cid].requires):
            earlier = pack.concepts.get(need)
            if earlier and subject_of(need) == subject and earlier.grade < pack.concepts[cid].grade:
                found = back(need)
                if len(found) > len(best) or (len(found) == len(best) and found and found[0] < best[0]):
                    best = found
        return [*best, cid]

    ends = sorted(c.id for c in pack.concepts.values()
                  if c.grade == grade and subject_of(c.id) == subject and (c.term or 1) == 1)
    chains = [back(cid) for cid in ends]
    return max(chains, key=lambda c: (pack.concepts[c[-1]].grade - pack.concepts[c[0]].grade, len(c)), default=[])


def _papers(pack: Pack, rng: random.Random, grade: int, term: int, subject: str, level: float,
            low: set[str], lang: str) -> list[tuple[str, list[dict]]]:
    """Two papers on the same few topics (a test and an exam), so each topic has more than one mark behind it."""
    taught = sorted(c.id for c in pack.concepts.values()
                    if c.grade == grade and subject_of(c.id) == subject and (c.term or 1) == term)
    planted = [c for c in taught if c in low]
    rest = [c for c in taught if c not in low]
    wanted = 6 if level >= 0.9 else 3        # the strong subject gets more topics, so a whole area shows each term
    topics = [*planted, *rng.sample(rest, min(len(rest), max(0, wanted - len(planted))))]
    out = []
    for paper in PAPERS:
        lines = []
        for cid in topics:
            out_of = rng.choice((5, 10))
            share = rng.uniform(0.2, 0.38) if cid in low else min(1.0, max(0.3, rng.gauss(level, 0.07)))
            lines.append({"topic_id": cid, "mark": round(share * out_of), "out_of": out_of})
        if lines:
            title = f"{SUBJECTS[subject][lang]}: {paper[lang]}"
            out.append((title, lines))
    return out


def build(language: str | None = None, seed: int = 21, db_path=None) -> dict[str, Any]:
    """Create the made-up family. Refuses when the family already has children of its own."""
    lang = language or ("ar" if get_settings().language == "ar" else "en")
    words = WORDS[lang]
    if family.own_children_ids(db_path):
        return {"skipped": "This family already has children. The made-up family is only for an empty family record."}
    token = audit.current_actor.set(ACTOR)
    try:
        who = family.choose("family", words["parent"], db_path=db_path)["guardian"]
        year = family.school_year()
        rng = random.Random(seed)
        with db.connect(db_path) as conn:       # the curriculum the records on this computer are on
            other = db.one(conn, "SELECT pack_id FROM learners LIMIT 1")
        pack = load_pack(other["pack_id"] if other else get_settings().demo_pack)
        first, top = pack.grades
        # name index, grade now, years of records, subjects with their usual level, where the difficulty is planted
        plan = (
            (0, min(top, first + 3), 3, {"maths": 0.66, "sci": 0.8, "ara": 0.78, "eng": 0.7, "soc": 0.74}, "maths"),
            (1, min(top, first + 2), 3, {"sci": 0.93, "maths": 0.74, "ara": 0.7, "eng": 0.62}, None),
            (2, first, 0, {"maths": 0.7}, None),
        )
        out: dict[str, Any] = {"parent": who["name"], "children": [], "proposed": 0, "approved": 0, "waiting": 0,
                               "open_questions": 0}
        for index, grade_now, years, levels, hard in plan:
            child = family.add_child(words["children"][index], grade_now, db_path=db_path)
            low = set(_chain(pack, hard, grade_now)) if hard else set()
            saved = 0
            if years == 0:      # just added: one short paper, too little to read anything into
                title, lines = _papers(pack, rng, grade_now, 1, "maths", 0.7, set(), lang)[0]
                saved += family.add_results(child["learner_id"], lines[:2] + lines[:2], title=title, grade=grade_now,
                                            year=year, term=1, db_path=db_path)["saved"]
            for back in range(years - 1, -1, -1):
                grade = grade_now - back
                if grade < first:
                    continue
                for term in range(1, (1 if back == 0 else pack.terms) + 1):     # this year has only begun
                    for subject, level in levels.items():
                        for title, lines in _papers(pack, rng, grade, term, subject, level, low, lang):
                            saved += family.add_results(child["learner_id"], lines, title=title, grade=grade,
                                                        year=year - back, term=term, db_path=db_path)["saved"]
            for text in words["notes"][index]:
                family.add_note(child["learner_id"], text, db_path=db_path)
            if years:
                with db.connect(db_path) as conn:
                    learner = db.one(conn, "SELECT id, alias, pack_id FROM learners WHERE id = ?", (child["learner_id"],))
                story.propose_for(learner, ("strength",), who["id"], words["approved"], out, db_path)
            out["children"].append({"code": child["code"], "grade": grade_now, "marks": saved,
                                    "planted_difficulty": sorted(low)})
    finally:
        audit.current_actor.reset(token)
    return out

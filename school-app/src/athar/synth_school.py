# ruff: noqa: C408, B023  (dict() keeps row builders readable; closures are called inside their loop)
"""A synthetic school on any curriculum pack. Everything here is made up: no real learners, no real school.

`synth.py` builds the small reference cohort and is tied to the generic packs. This generator reads whatever
pack it is given (its grades, its terms, its prerequisite links) and plants patterns by walking the
pack's own graph, so it works for a national curriculum without naming any topic in code.

The school year is written as the calendar year it starts in: 2025 means 2025/26. Past years are
complete. The current year stops part way through term 1, so there is a term in progress to add to.

Planted patterns (written to ground_truth.json):
  root_gap         a topic missed in a term with many absences; later topics that need it stay low
  unknown_root     the same, but the term the topic was taught has no records at all
  strand_strength  one area of the subject is clearly secure over several terms
  what_worked      topics taught with one approach are followed by better results
  no_pattern       steady results, nothing to find
  new_arrival      joined this year: too little data to say anything
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import random
from pathlib import Path
from typing import Any

from . import db
from .config import ROOT, get_settings
from .synth import _clip, _Ids, _load_pack, _load_templates, _topo_order

SCHOOL_NAME = "Al-Nahda Demonstration School (synthetic)"
CURRENT_YEAR = 2026           # school year 2026/27, term 1 in progress
PAST_YEARS = 3
CURRENT_TERM_SHARE = 0.4      # how much of the current term has been taught so far
CREATED_AT = "2023-09-01T08:00:00+00:00"

# Invented names. They are not real people. Names usual in Saudi Arabia, and a few teachers from abroad, as an
# international school has.
TEACHERS = ["Noura Al-Qahtani", "Faisal Al-Harbi", "Reem Al-Otaibi", "Abdullah Al-Ghamdi", "Hessa Al-Dosari",
            "Turki Al-Shehri"]
# A school with several subjects has teachers for each stage: primary, then the grades above.
MORE_TEACHERS = ["Sarah Mitchell", "Omar Al-Zahrani", "Lama Al-Mutairi", "Daniel Hughes", "Amal Al-Juhani",
                 "Khalid Al-Subaie", "Maha Al-Anazi", "Yousef Al-Shammari"]
FIRST_NAMES = [
    "Abdulrahman", "Lulwa", "Faisal", "Joud", "Saud", "Ghala", "Nawaf", "Danah", "Rakan", "Shahad", "Turki", "Lamar",
    "Mohammed", "Jana", "Abdulaziz", "Rimas", "Sultan", "Hala", "Bandar", "Wasan", "Fahad", "Layan", "Majed", "Reemas",
    "Khalid", "Taif", "Meshari", "Sarah", "Yazeed", "Ruba", "Hamad", "Nouf", "Saleh", "Aljawhara", "Ziyad", "Haya",
    "Mansour", "Deema", "Omar", "Leen", "Talal", "Maryam", "Nasser", "Bayan", "Waleed", "Atheer", "Ibrahim", "Razan",
]
FAMILY_INITIALS = "AQHGDSMZJTBN"
# The same invented people, written in Arabic, for a school whose language is Arabic.
SCHOOL_NAME_AR = "مدرسة النهضة التجريبية (بيانات غير حقيقية)"
TEACHERS_AR = ["نورة القحطاني", "فيصل الحربي", "ريم العتيبي", "عبدالله الغامدي", "حصة الدوسري", "تركي الشهري"]
MORE_TEACHERS_AR = ["سارة ميتشل", "عمر الزهراني", "لمى المطيري", "دانيال هيوز", "أمل الجهني", "خالد السبيعي",
                    "مها العنزي", "يوسف الشمري"]
FIRST_NAMES_AR = [
    "عبدالرحمن", "لولوة", "فيصل", "جود", "سعود", "غلا", "نواف", "دانة", "راكان", "شهد", "تركي", "لمار",
    "محمد", "جنى", "عبدالعزيز", "ريماس", "سلطان", "هلا", "بندر", "وسن", "فهد", "ليان", "ماجد", "ريماز",
    "خالد", "طيف", "مشاري", "سارة", "يزيد", "ربى", "حمد", "نوف", "صالح", "الجوهرة", "زياد", "هيا",
    "منصور", "ديمة", "عمر", "لين", "طلال", "مريم", "ناصر", "بيان", "وليد", "أثير", "إبراهيم", "رزان",
]
FAMILY_INITIALS_AR = "أقحغدسمزجتبن"
WHAT_WORKS_AR = [
    "أبدأ باستخدام {approach} قبل أي عمل كتابي، ويشرح كل طالبين إجابتهما لبعضهما.",
    "تمهيد قصير في بداية كل حصة، ثم {approach}. وأحتفظ بملف لكل طالب كسجل لعمله.",
    "{approach}، مع أمثلة من الحياة اليومية ومن الرياضة. ومن ينهي مبكراً يساعد زميله.",
    "{approach} في مجموعات صغيرة بينما يعمل الباقون من السبورة. وأصحح ثمانية دفاتر في اليوم.",
]
WANTS_HELP_AR = [
    "إيجاد وقت لمتابعة عمل كل طالب في فصل فيه أكثر من خمسة وعشرين طالباً.",
    "معرفة ما درسه الطالب قبل أن يصل إلى فصلي.",
    "تدريس {strand} لطلاب فاتهم الصف السابق.",
    "توضيح مستوى الطالب لأسرته بكلمات بسيطة.",
]
WORDS = {
    "en": {"question": "{topic}: question {k}", "homework": "Homework task: {topic}",
           "project": "End-of-year performance task: {topic}", "absent": "Absent {n} days this term",
           "taught": "Taught with: {approach}", "the_topic": "the topic", "languages": "Arabic, English",
           "default_approach": "Worked examples", "the_subject": "the subject"},
    "ar": {"question": "{topic}: السؤال {k}", "homework": "واجب: {topic}",
           "project": "مهمة أداء آخر السنة: {topic}", "absent": "غياب {n} يوم في هذا الفصل الدراسي",
           "taught": "طريقة التدريس: {approach}", "the_topic": "الموضوع", "languages": "العربية والإنجليزية",
           "default_approach": "أمثلة محلولة", "the_subject": "المادة"},
}
WHAT_WORKS = [
    "Starting with {approach} before any written work. Pairs explain their answer to each other.",
    "A short warm-up every lesson, then {approach}. I keep one copybook per learner as a record.",
    "{approach}, with examples from daily life and from sport. Fast finishers help a neighbour.",
    "{approach} in small groups while the rest work from the board. I mark eight copybooks a day.",
]
WANTS_HELP = [
    "Finding time to see each learner's work with more than twenty-five in the class.",
    "Knowing what a learner covered before they reached my class.",
    "Teaching {strand} to learners who missed the earlier grade.",
    "Showing a family where their child is stuck, in plain words.",
]


def _term_dates(year: int, term: int, terms: int) -> tuple[dt.date, dt.date]:
    """A school year that starts in late August, as in Saudi Arabia. Two terms: to mid January, then to mid June.
    Three terms (a British-style year): to mid December, January to late March, April to mid June."""
    if terms == 2:
        return (dt.date(year, 8, 24), dt.date(year + 1, 1, 15)) if term == 1 else (dt.date(year + 1, 1, 25), dt.date(year + 1, 6, 15))
    return {1: (dt.date(year, 8, 24), dt.date(year, 12, 12)), 2: (dt.date(year + 1, 1, 4), dt.date(year + 1, 3, 26)),
            3: (dt.date(year + 1, 4, 5), dt.date(year + 1, 6, 15))}[term]


def generate_school(db_path: Path | str | None = None, seed: int = 11, pack_id: str = "cambridge-school",
                    n_learners: int = 40, out_dir: Path | str | None = None, lang: str | None = None) -> dict[str, Any]:
    """`lang`: the language the made-up names, notes and labels are written in (the school's language
    by default). The numbers are the same in either language."""
    lang = lang or get_settings().language
    words = WORDS["ar" if lang == "ar" else "en"]
    named = lambda item: item["label"].get(lang) or item["label"]["en"]
    rng = random.Random(seed)
    ids = _Ids(rng)
    out = Path(out_dir) if out_dir else ROOT / "data"
    inbox, samples = out / "inbox", out / "samples"
    for folder in (out, inbox, samples):
        folder.mkdir(parents=True, exist_ok=True)

    pack = _load_pack(pack_id)
    concepts = _topo_order(pack["concepts"])
    by_id = {c["id"]: c for c in concepts}
    label = lambda cid: named(by_id[cid])
    approach_ids = [a["id"] for a in pack["approaches"]]
    approach_label = {a["id"]: named(a) for a in pack["approaches"]}
    strand_label = {s["id"]: named(s) for s in pack["strands"]}
    strand_subject = {s["id"]: s.get("subject", pack["subject"]) for s in pack["strands"]}
    subject_of = lambda cid: strand_subject[by_id[cid]["strand"]]
    subjects = list(dict.fromkeys(subject_of(c["id"]) for c in concepts))
    subject_label = {s["id"]: named(s) for s in pack.get("subjects") or []}
    templates = _load_templates()
    terms = int(pack.get("terms", 3))
    g_lo, g_hi = pack["grades"]
    first_year = CURRENT_YEAR - PAST_YEARS
    children: dict[str, list[str]] = {c["id"]: [] for c in concepts}
    for c in concepts:
        for r in c["requires"]:
            children[r].append(c["id"])

    # ---- schedule: the pack says which term a topic belongs to; topics without a term are spread evenly
    schedule: dict[int, dict[int, list[str]]] = {}
    term_of: dict[str, int] = {}
    for g in range(g_lo, g_hi + 1):
        schedule[g] = {t: [c["id"] for c in concepts if c["grade"] == g and c.get("term") == t] for t in range(1, terms + 1)}
        loose = [c["id"] for c in concepts if c["grade"] == g and not c.get("term")]
        for i, cid in enumerate(loose):
            schedule[g][1 + (i * terms) // max(1, len(loose))].append(cid)
        for t, cids in schedule[g].items():
            term_of.update({cid: t for cid in cids})

    def periods_of(start_year: int) -> list[tuple[int, int]]:
        return [(y, t) for y in range(start_year, CURRENT_YEAR + 1) for t in range(1, terms + 1)
                if y < CURRENT_YEAR or t == 1]

    def taught(grade: int, year: int, term: int) -> list[str]:
        cids = schedule.get(grade, {}).get(term, [])
        if year == CURRENT_YEAR and cids:                               # the term in progress, subject by subject
            keep: set[str] = set()
            for subject in subjects:
                own = [cid for cid in cids if subject_of(cid) == subject]
                keep.update(own[:max(1, round(len(own) * CURRENT_TERM_SHARE))] if own else [])
            return [cid for cid in cids if cid in keep]
        return cids

    # ---- learners: spread over the grades; each has as much history as the map covers
    specs: list[dict[str, Any]] = []
    used: set[str] = set()
    for i in range(n_learners):
        grade_now = g_lo + i % (g_hi - g_lo + 1)
        start_year = max(first_year, CURRENT_YEAR - (grade_now - g_lo))
        while True:
            alias = f"Learner {rng.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}-{rng.randint(1, 99):02d}"
            if alias not in used:
                used.add(alias)
                break
        specs.append(dict(alias=alias, grade_now=grade_now, start_year=start_year,
                          start_grade=grade_now - (CURRENT_YEAR - start_year), case="mild",
                          name=(f"{FIRST_NAMES_AR[i % len(FIRST_NAMES_AR)]} {FAMILY_INITIALS_AR[(i * 5 + i // len(FIRST_NAMES_AR)) % len(FAMILY_INITIALS_AR)]}."
                                if lang == "ar" else
                                f"{FIRST_NAMES[i % len(FIRST_NAMES)]} {FAMILY_INITIALS[(i * 5 + i // len(FIRST_NAMES)) % len(FAMILY_INITIALS)]}."),
                          ability=round(rng.uniform(0.58, 0.78), 3), tilt_sd=0.04, noise_sd=0.04,
                          missing=set(), sparse=set(), plant={}))

    def grade_in(spec: dict, year: int) -> int:
        return spec["start_grade"] + (year - spec["start_year"])

    def span(spec: dict) -> set[str]:
        """Topics this learner has been taught so far."""
        return {cid for (y, t) in periods_of(spec["start_year"]) for cid in taught(grade_in(spec, y), y, t)}

    def descendants(cid: str, within: set[str]) -> list[str]:
        seen, queue = [], list(children[cid])
        while queue:
            cur = queue.pop(0)
            if cur in within and cur not in seen:
                seen.append(cur)
                queue.extend(children[cur])
        return seen

    # ---- plant patterns by walking the pack's graph
    long_history = [s for s in specs if s["start_year"] == first_year]
    rng.shuffle(long_history)
    plan = ["root_gap", "root_gap", "root_gap", "unknown_root", "strand_strength", "strand_strength", "strand_strength",
            "what_worked", "what_worked", "no_pattern", "no_pattern"]
    for spec, case in zip(long_history, plan, strict=False):
        seen = span(spec)
        first_topics = [cid for t in range(1, terms + 1) for cid in taught(spec["start_grade"], first_year, t)]
        if case in ("root_gap", "unknown_root"):
            options = [(cid, descendants(cid, seen)) for cid in first_topics]
            options = [(cid, d) for cid, d in options if 2 <= len(d) <= 9]
            if not options:
                continue
            root, later = max(options, key=lambda o: (len({by_id[x]["grade"] for x in o[1]}), -len(o[1]), o[0]))
            spec.update(case=case, ability=0.72, tilt_sd=0.02, plant={"root": root, "later": later,
                                                                     "period": (first_year, term_of[root])})
            if case == "unknown_root":
                spec["missing"].add((first_year, term_of[root]))
        elif case == "strand_strength":
            counts: dict[str, set] = {}
            for (y, t) in periods_of(spec["start_year"]):
                for cid in taught(grade_in(spec, y), y, t):
                    counts.setdefault(by_id[cid]["strand"], set()).add((y, t))
            wide = sorted(st for st, ps in counts.items() if len(ps) >= 3)
            if wide:
                spec.update(case=case, ability=0.62, tilt_sd=0.0, plant={"strand": rng.choice(wide)})
        elif case == "what_worked":
            spec.update(case=case, ability=0.55, tilt_sd=0.0, plant={"approach": approach_ids[len(specs) % len(approach_ids)]})
        else:
            spec.update(case=case, ability=0.66, tilt_sd=0.0, noise_sd=0.03)
    arrivals = [s for s in specs if s["case"] == "mild" and s["grade_now"] >= g_lo + 2]
    if arrivals:                                                        # joined this year from another school
        arrivals[0].update(case="new_arrival", start_year=CURRENT_YEAR, start_grade=arrivals[0]["grade_now"])
    mild = [s for s in specs if s["case"] == "mild"]
    for k, spec in enumerate(mild):
        past = [p for p in periods_of(spec["start_year"]) if p[0] < CURRENT_YEAR][1:]
        if past and k % 7 == 3:
            spec["missing"].add(rng.choice(past))
        spec["sparse"] = {p for p in past if p not in spec["missing"] and rng.random() < 0.15}
    strands = sorted({c["strand"] for c in concepts})
    for spec in specs:
        spec["tilt"] = {st: (rng.gauss(0, spec["tilt_sd"]) if spec["tilt_sd"] else 0.0) for st in strands}

    # ---- teachers and teaching units: one unit per (year, grade, topic) some learner met
    multi = len(subjects) > 1
    staff = (TEACHERS_AR, MORE_TEACHERS_AR) if lang == "ar" else (TEACHERS, MORE_TEACHERS)
    # A long span (Years 1 to 11) has three stages: primary, lower secondary, and the exam years. Otherwise two.
    stage_tops = [6, 9] if g_hi - g_lo >= 8 else [g_lo + 2]
    per = len(stage_tops) + 1
    names = (staff[0] + staff[1])[:per * len(subjects)] if multi else staff[0]
    if multi and len(names) < per * len(subjects):
        raise ValueError(f"This generator has names for at most {len(staff[0] + staff[1]) // per} subjects.")
    teacher_ids = [ids.new("tch") for _ in names]
    teacher_subjects = ({tid: [subjects[i // per]] for i, tid in enumerate(teacher_ids)} if multi
                        else {tid: [pack["subject"]] for tid in teacher_ids})
    teacher_name = dict(zip(teacher_ids, names, strict=True))

    def teacher_of(subject: str, grade: int, year: int) -> str:
        if multi:                                                        # one teacher per stage and subject
            return teacher_ids[per * subjects.index(subject) + sum(grade > top for top in stage_tops)]
        if grade == g_lo + 2 and year < CURRENT_YEAR:                    # one staff change, as schools have
            return teacher_ids[-1]
        return teacher_ids[(grade - g_lo) % (len(teacher_ids) - 1)]

    worked = {(y, grade_in(s, y)): s["plant"]["approach"] for s in specs if s["case"] == "what_worked"
              for y in range(s["start_year"], CURRENT_YEAR + 1)}
    units: dict[tuple[int, int, str], dict[str, Any]] = {}
    for (y, g) in sorted({(y, grade_in(s, y)) for s in specs for y in range(s["start_year"], CURRENT_YEAR + 1)}):
        for t in range(1, terms + 1):
            if y == CURRENT_YEAR and t > 1:
                continue
            term_base = rng.choice(approach_ids)
            for cid in taught(g, y, t):
                approach = term_base if rng.random() < 0.65 else rng.choice(approach_ids)
                special = worked.get((y, g))
                if special:                                             # the approach is used in the last term only
                    approach = special if t == terms else rng.choice([a for a in approach_ids if a != special])
                units[(y, g, cid)] = dict(id=ids.new("unt"), teacher_id=teacher_of(subject_of(cid), g, y), year=y, term=t,
                                          grade=g, concept_id=cid, approach_id=approach,
                                          note=words["taught"].format(approach=approach_label[approach]))

    def latent(spec: dict) -> dict[str, float]:
        gap_line, m = spec["ability"] - 0.15, {}
        for c in concepts:
            base = spec["ability"] + spec["tilt"].get(c["strand"], 0.0) + rng.gauss(0, spec["noise_sd"])
            gaps = [m[r] for r in c["requires"] if m[r] < gap_line]
            val = min(base, min(gaps) + 0.03) if gaps else base
            if spec["plant"].get("root") == c["id"]:
                val = 0.27
            if spec["plant"].get("strand") == c["strand"]:
                val = max(val, 0.91)
            if spec["case"] == "what_worked":
                unit = units.get((spec["start_year"] + c["grade"] - spec["start_grade"], c["grade"], c["id"]))
                if unit and unit["approach_id"] == spec["plant"]["approach"]:
                    val = min(0.93, val + 0.27)
            m[c["id"]] = _clip(val, 0.05, 0.97)
        return m

    # ---- evidence
    evidence: list[dict[str, Any]] = []
    learner_rows: list[dict[str, Any]] = []

    def stamp(year: int, term: int) -> tuple[str, int]:
        start, end = _term_dates(year, term, terms)
        if year == CURRENT_YEAR:
            end = start + dt.timedelta(days=45)
        late = year < CURRENT_YEAR and rng.random() < 0.08
        day = end + dt.timedelta(days=rng.randint(20, 90)) if late else start + dt.timedelta(days=rng.randint(0, (end - start).days))
        return f"{day.isoformat()}T{rng.randint(8, 14):02d}:{rng.choice([0, 15, 30, 45]):02d}:00", int(late)

    for spec in specs:
        lid = spec["id"] = ids.new("lrn")
        learner_rows.append(dict(id=lid, alias=spec["alias"], display_name=spec["name"], pack_id=pack_id,
                                 start_year=spec["start_year"], start_grade=spec["start_grade"], home_language="ar",
                                 created_at=CREATED_AT))
        mastery = spec["mastery"] = latent(spec)
        prev_mean: float | None = None
        for (y, t) in periods_of(spec["start_year"]):
            grade, topics = grade_in(spec, y), taught(grade_in(spec, y), y, t)
            if not topics or (y, t) in spec["missing"]:
                continue
            home, po, thin = teacher_of(subjects[0], grade, y), db.period_ord(y, t), (y, t) in spec["sparse"]

            def add(kind: str, ref: str, at: tuple[str, int] | None = None, topic: str | None = None, **kw: Any) -> None:
                recorded_at, late = at or stamp(y, t)
                tid = teacher_of(subject_of(topic), grade, y) if topic else home
                if topic:
                    kw["concept_id"] = topic
                evidence.append(dict(dict(concept_id=None, skill_id=None, score=None, absent_days=None, raw_text=None,
                                          language=("ar" if lang == "ar" else "en"), unit_id=None, status="active"),
                                     id=ids.new("evd"), learner_id=lid, kind=kind, year=y, term=t, period_ord=po,
                                     grade=grade, teacher_id=tid, source_ref=ref, recorded_at=recorded_at,
                                     logged_late=late, **kw))

            for ci, cid in enumerate(topics, start=1):
                unit, at = units.get((y, grade, cid)), stamp(y, t)
                for k in range(1, (rng.randint(1, 2) if thin else rng.randint(3, 5)) + 1):
                    add("quiz_item", f"quiz:{y}-T{t}-{subject_of(cid)}-{ci:02d}#item{k}", at, topic=cid,
                        skill_id=(by_id[cid]["skills"] or [None])[0], score=round(_clip(rng.gauss(mastery[cid], 0.08)), 2),
                        raw_text=words["question"].format(topic=label(cid), k=k), unit_id=unit["id"] if unit else None)
            for subject in subjects:
                own = [cid for cid in topics if subject_of(cid) == subject]
                if own and not thin:
                    cid = rng.choice(own)
                    add("assignment", f"assignment:{y}-T{t}-{subject}-1", topic=cid,
                        score=round(_clip(rng.gauss(mastery[cid], 0.10)), 2), raw_text=words["homework"].format(topic=label(cid)),
                        unit_id=units[(y, grade, cid)]["id"])
                if own and t == terms and y < CURRENT_YEAR and not thin:
                    cid = rng.choice(own)
                    add("project", f"project:{y}-T{t}-{subject}-task", topic=cid, skill_id=(by_id[cid]["skills"] or [None])[0],
                        score=round(_clip(rng.gauss(mastery[cid], 0.10)), 2),
                        raw_text=words["project"].format(topic=label(cid)), unit_id=units[(y, grade, cid)]["id"])
            if spec["plant"].get("period") == (y, t):
                absent = 17
            elif spec["case"] == "mild" and rng.random() < 0.08:
                absent = rng.randint(10, 14)
            else:
                absent = rng.choice([0, 0, 1, 1, 2, 3, 4, 5]) if y < CURRENT_YEAR else rng.choice([0, 0, 1, 2])
            add("attendance", f"register:{y}-T{t}", absent_days=absent, raw_text=words["absent"].format(n=absent))

            lo, hi = min(topics, key=lambda x: mastery[x]), max(topics, key=lambda x: mastery[x])
            mean = sum(mastery[c] for c in topics) / len(topics)
            if mastery[lo] < 0.5:
                signal, target = "struggling", lo
            elif prev_mean is not None and mean - prev_mean > 0.1:
                signal, target = "improving", hi
            elif mastery[hi] > 0.85:
                signal, target = "strong", hi
            elif mastery[lo] < 0.6:
                signal, target = "needs_support", lo
            else:
                signal, target = "engaged", hi
            prev_mean = mean
            for n, (sig, cid) in enumerate([(signal, target)] + ([("absent_often", None)] if absent >= 10 else []), start=1):
                if cid is not None and rng.random() < 0.12:
                    cid = None                                           # the teacher did not say which topic
                # In an Arabic school every note is in Arabic. Otherwise about a third are.
                in_arabic = (rng.random() < 0.35 or lang == "ar") and "ar" in templates.get(sig, {})
                note_lang = "ar" if in_arabic else "en"
                text = rng.choice(templates.get(sig, {}).get(note_lang) or templates["engaged"]["en"])
                add("observation", f"note:{y}-T{t}-{n}", topic=cid, language=note_lang,
                    raw_text=text.replace("{concept}", label(cid) if cid else words["the_topic"]))

    # ---- write
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        for table in ("parent_sessions", "parent_learners", "parents", "settings", "class_teachers", "class_learners", "classes", "sessions", "accounts", "record_requests", "approvals", "summaries", "findings", "audit_log",
                      "evidence", "teaching_units", "learners", "teacher_profiles", "teachers"):
            conn.execute(f"DELETE FROM {table}")
        conn.executemany("INSERT INTO teachers (id, name, subjects) VALUES (?, ?, ?)",
                         [(tid, teacher_name[tid], db.jdump(teacher_subjects[tid])) for tid in teacher_ids])
        conn.executemany(
            "INSERT INTO learners (id, alias, display_name, pack_id, start_year, start_grade, home_language, created_at) "
            "VALUES (:id, :alias, :display_name, :pack_id, :start_year, :start_grade, :home_language, :created_at)", learner_rows)
        conn.executemany(
            "INSERT INTO teaching_units (id, teacher_id, year, term, grade, concept_id, approach_id, note) "
            "VALUES (:id, :teacher_id, :year, :term, :grade, :concept_id, :approach_id, :note)", list(units.values()))
        conn.executemany(
            "INSERT INTO evidence (id, learner_id, kind, year, term, period_ord, grade, concept_id, skill_id, score, "
            "absent_days, raw_text, language, source_ref, teacher_id, unit_id, recorded_at, logged_late, status) "
            "VALUES (:id, :learner_id, :kind, :year, :term, :period_ord, :grade, :concept_id, :skill_id, :score, "
            ":absent_days, :raw_text, :language, :source_ref, :teacher_id, :unit_id, :recorded_at, :logged_late, :status)",
            evidence)
        # One class per grade this year. Each subject's teacher for that grade takes the class.
        for g in range(g_lo, g_hi + 1):
            members = [spec["id"] for spec in specs if spec["grade_now"] == g]
            if not members:
                continue
            class_id = f"cls_{CURRENT_YEAR}_{g}a"
            conn.execute("INSERT INTO classes (id, name, grade, year, created_at) VALUES (?,?,?,?,?)",
                         (class_id, f"{g}A", g, CURRENT_YEAR, CREATED_AT))
            conn.executemany("INSERT INTO class_learners (class_id, learner_id) VALUES (?,?)",
                             [(class_id, lid) for lid in members])
            conn.executemany("INSERT OR IGNORE INTO class_teachers (class_id, teacher_id, subject) VALUES (?,?,?)",
                             [(class_id, teacher_of(subject, g, CURRENT_YEAR), subject) for subject in subjects])
        prof = random.Random(seed + 1000)
        for index, tid in enumerate(teacher_ids):
            used_rows = db.rows(conn, "SELECT approach_id, COUNT(*) AS n FROM teaching_units WHERE teacher_id = ? "
                                      "GROUP BY approach_id ORDER BY n DESC, approach_id", (tid,))
            ranked = [u["approach_id"] for u in used_rows]
            third = max(1, len(ranked) // 3)
            said = {a: "often" if i < third else "sometimes" if i < 2 * third else "rarely" for i, a in enumerate(ranked)}
            said.update({a: "rarely" for a in approach_ids if a not in said})
            areas = sorted({strand_label[by_id[r["concept_id"]]["strand"]] for r in db.rows(
                conn, "SELECT DISTINCT concept_id FROM teaching_units WHERE teacher_id = ?", (tid,))}) or [words["the_subject"]]
            works, wants = (WHAT_WORKS_AR, WANTS_HELP_AR) if lang == "ar" else (WHAT_WORKS, WANTS_HELP)
            answers = {"approaches": said, "languages": words["languages"], "class_size": str(44 + (index * 7) % 19),
                       "what_works": prof.choice(works).format(approach=approach_label[ranked[0]] if ranked else words["default_approach"]),
                       "wants_help_with": prof.choice(wants).format(strand=prof.choice(areas))}
            conn.execute("INSERT INTO teacher_profiles (teacher_id, answers, updated_at) VALUES (?, ?, ?)",
                         (tid, db.jdump(answers), CREATED_AT))
        by_kind = {r[0]: r[1] for r in conn.execute("SELECT kind, COUNT(*) FROM evidence GROUP BY kind")}

    # ---- ground truth, inbox and a sample marks sheet
    planted = []
    for spec in specs:
        if spec["case"] == "mild":
            continue
        plant = dict(spec["plant"])
        if "later" in plant:
            # The gap fades a little with each step away from the missed topic. Only the topics that are still
            # clearly low are listed as what an honest analysis should trace back.
            low = [cid for cid in plant["later"] if spec["mastery"][cid] < 0.42]
            plant["later"] = low or plant["later"][:1]
        if "period" in plant:
            plant["period"] = db.period_label(db.period_ord(*plant["period"]))
        planted.append({"learner_id": spec["id"], "alias": spec["alias"], "case": spec["case"], **plant})
    (out / "ground_truth.json").write_text(json.dumps(
        {"seed": seed, "pack_id": pack_id, "school": SCHOOL_NAME_AR if lang == "ar" else SCHOOL_NAME, "language": lang, "current_period": f"{CURRENT_YEAR}-T1",
         "note": "Synthetic data. Planted patterns are what an honest analysis should find.", "planted": planted},
        ensure_ascii=False, indent=2), encoding="utf-8")

    for old in list(inbox.iterdir()) + list(samples.iterdir()):
        if old.is_file():
            old.unlink()
    files = []
    focus = next((s for s in specs if s["case"] == "root_gap"), specs[0])
    grade = focus["grade_now"]
    ahead = [cid for cid in schedule[grade][1] if cid not in taught(grade, CURRENT_YEAR, 1)] or schedule[grade][1]
    topic = next((cid for cid in ahead if focus["plant"].get("root") in _ancestors(cid, by_id)), ahead[0])
    ahead = [cid for cid in ahead if subject_of(cid) == subject_of(topic)]
    subject_name = subject_label.get(subject_of(topic), subject_of(topic))
    code = focus["alias"].replace("Learner ", "")
    marks = [(n, words["question"].format(topic=label(topic), k=n), rng.choice([0, 0, 1, 1, 2]) if n != 4 else "-", rng.choice([2, 3]))
             for n in range(1, 7)]
    sheet_teacher = teacher_name[teacher_of(subject_of(topic), grade, CURRENT_YEAR)]
    if lang == "ar":
        lines = ["# كشف اختبار قصير (بيانات تجريبية غير حقيقية)", "", f"الطالب: {focus['alias']}", f"الصف: {grade}",
                 f"الفصل الدراسي: {CURRENT_YEAR}-T1", f"المعلم: {sheet_teacher}", f"المادة: {subject_name}",
                 f"الاختبار: {CURRENT_YEAR}-T1-{subject_of(topic)}-quiz ({label(topic)})",
                 "", "| رقم السؤال | السؤال | الدرجة | من |", "|------|----------|-------|--------|"]
        lines += [f"| {n} | {q} | {m} | {o} |" for n, q, m, o in marks] + ["", "السؤال 4 لم يُجب عنه."]
    lines_en = ["# Quiz sheet (synthetic)", "", f"Learner: {focus['alias']}", f"Grade: {grade}", f"Term: {CURRENT_YEAR}-T1",
             f"Teacher: {teacher_name[teacher_of(subject_of(topic), grade, CURRENT_YEAR)]}", f"Subject: {subject_name}",
             f"Quiz: {CURRENT_YEAR}-T1-{subject_of(topic)}-quiz ({label(topic)})",
             "", "| Item | Question | Marks | Out of |", "|------|----------|-------|--------|"]
    lines_en += [f"| {n} | {q} | {m} | {o} |" for n, q, m, o in marks] + ["", "Item 4 not attempted."]
    if lang != "ar":
        lines = lines_en
    name = f"quiz_sheet_{code}_{CURRENT_YEAR}-T1.md"
    (inbox / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
    files.append(name)
    other = next(s for s in specs if s["case"] == "mild")
    (inbox / "teacher_note_ar.txt").write_text(
        f"{other['alias']}: في الفصل الدراسي الأول من العام {CURRENT_YEAR} تحسّن الأداء في {label(taught(other['grade_now'], CURRENT_YEAR, 1)[0])}، "
        "لكن الغياب تكرّر وتأخّر تسليم الواجبات. يُفضَّل متابعة الحضور مع الأسرة واستخدام أدوات محسوسة في الحصة.\n",
        encoding="utf-8")
    files.append("teacher_note_ar.txt")
    (inbox / "README.md").write_text(
        "# Inbox (synthetic)\n\nEvery file here is made up by `athar.synth_school`. The learners are record codes, "
        "the teachers are fictional, and nothing refers to a real child or school.\n\n"
        f"Each file is about the term in progress, {CURRENT_YEAR}-T1.\n", encoding="utf-8")

    # A filled marks sheet for one grade, in the upload template's layout, on topics not taught yet this term.
    class_now = [s for s in specs if s["grade_now"] == grade]
    quiz_topics = (ahead * 5)[:5]
    with open(samples / f"marks-grade{grade}-{CURRENT_YEAR}-T1.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        from .imports import sheet_words
        sheet = sheet_words(lang)
        w.writerow([sheet["code"], sheet["name"]] + [f"{sheet['q']}{i}" for i in range(1, 6)])
        w.writerow([sheet["topic"], ""] + [label(cid) for cid in quiz_topics])
        w.writerow([sheet["out_of"], ""] + [2, 2, 3, 3, 4])
        for s in class_now:
            w.writerow([s["alias"].replace("Learner ", ""), s["name"]] + [
                round(_clip(rng.gauss(s["mastery"][cid], 0.12)) * top) for cid, top in zip(quiz_topics, [2, 2, 3, 3, 4], strict=True)])

    return {"school": SCHOOL_NAME, "pack_id": pack_id, "current_period": f"{CURRENT_YEAR}-T1",
            "subjects": subjects,
            "counts": {"teachers": len(teacher_ids), "learners": len(specs), "teaching_units": len(units), "evidence": len(evidence)},
            "evidence_by_kind": by_kind, "learners_by_grade": {g: sum(1 for s in specs if s["grade_now"] == g)
                                                                for g in range(g_lo, g_hi + 1)},
            "planted": [{"case": p["case"], "alias": p["alias"]} for p in planted],
            "inbox": files, "sample_marks_sheet": str(samples / f"marks-grade{grade}-{CURRENT_YEAR}-T1.csv"),
            "ground_truth": str(out / "ground_truth.json")}


def _ancestors(cid: str, by_id: dict[str, dict]) -> set[str]:
    seen: set[str] = set()
    queue = list(by_id[cid]["requires"])
    while queue:
        cur = queue.pop()
        if cur not in seen:
            seen.add(cur)
            queue.extend(by_id[cur]["requires"])
    return seen

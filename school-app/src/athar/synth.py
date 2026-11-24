# ruff: noqa: C408, B023  (dict() keeps row builders readable; closures are called inside their loop)
"""Synthetic data for Athar. Everything here is made up: no real learners, no real schools.

`generate()` writes learners, teachers, teaching units and evidence straight into the database, plus
`ground_truth.json` (the planted patterns, used by evals) and a few raw files in `inbox/` for the agent
to ingest later. It is deterministic for a given seed and does not import tools, graph or curriculum.

How the data stays coherent: every learner has a latent mastery per concept. A concept's mastery is
pulled down by a prerequisite that is clearly weak, so a missed foundation propagates forward. Quiz
scores are noisy draws around that mastery. The data is then made messy on purpose: late logging,
whole missing terms, sparse terms, untagged observations and a few rows needing review.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import random
from pathlib import Path
from typing import Any

import yaml

from . import db
from .config import ROOT, get_settings

BASE_YEAR = 2021
CREATED_AT = "2021-01-10T08:00:00+00:00"

TEACHERS = [
    "Amina Wanjiru",
    "Kwame Mensah",
    "Funmilayo Adeyemi",
    "Tesfaye Alemu",
    "Nadia Haddad",
    "Josephine Uwimana",
]

TERM_DATES = {  # (start month, start day, end month, end day)
    1: (1, 20, 4, 10),
    2: (5, 5, 8, 10),
    3: (9, 1, 12, 5),
}

# A whole school (`generate(school=True)`): more staff, each teaching a subject, each with a described
# way of teaching. Every name is fictional.
SCHOOL_NAME = "Demonstration School (synthetic)"
SCHOOL_LEARNERS = 36
EXTRA_TEACHERS = ["Ibrahim Diallo", "Thandiwe Nkosi", "Mariam El-Sayed", "Chinedu Okafor"]
STAFF_PER_SUBJECT = {"maths": 3, "language": 3, "science": 2, "technology": 2}
TEACHER_LANGUAGES = ["English, Swahili", "English, Arabic", "English, French", "English, Hausa",
                     "English, Amharic", "English, Kinyarwanda", "English, Wolof", "English, isiZulu",
                     "Arabic, English", "English, Igbo"]
CLASS_SIZES = ["38", "44", "52", "41", "60", "47", "55", "36", "49", "58"]
WHAT_WORKS = [
    "Starting with {approach} before any written work. Pairs explain their answer to each other.",
    "Short daily practice, then {approach} once a week. I keep one exercise book per learner as a record.",
    "{approach}, with examples from the market and the farm. Learners who finish early help a neighbour.",
    "{approach} in small groups while the rest work from the board. I mark five books a day.",
]
WANTS_HELP = [
    "Finding time to see each learner's work when the class is this large.",
    "Knowing what a learner covered before they reached my class.",
    "Teaching {strand} to learners who missed the earlier grade.",
    "Writing to families in their own language.",
]

# Invented names, so a teacher's screen reads like a class and not like a list of codes. They are not
# real children. Only a first name and an initial are made up, and only the teacher app shows them.
FIRST_NAMES = [
    "Amani", "Kofi", "Zainab", "Tendai", "Fatima", "Chidi", "Leila", "Sipho", "Aisha", "Kwabena", "Nomsa", "Youssef",
    "Wanjiku", "Emeka", "Mariam", "Thabo", "Halima", "Kagiso", "Salma", "Obinna", "Nia", "Tariq", "Adaeze", "Juma",
    "Hana", "Bongani", "Imani", "Karim", "Folake", "Mwangi", "Rania", "Sekou", "Zola", "Hassan", "Ama", "Idris",
    "Lindiwe", "Baraka", "Chiamaka", "Nour", "Kelechi", "Ayana", "Malik", "Thandeka", "Yaw", "Samira", "Dumisani",
    "Efua", "Khalid", "Neema", "Tunde", "Layla", "Sizwe", "Abena", "Rashid", "Makena", "Jabari", "Dalia", "Olu", "Zuri",
]
FAMILY_INITIALS = "KMOANDBSTWHJ"


def invented_name(index: int) -> str:
    """The name of the learner at this position: a first name and an initial, the same every time."""
    first = FIRST_NAMES[index % len(FIRST_NAMES)]
    return f"{first} {FAMILY_INITIALS[(index * 5 + index // len(FIRST_NAMES)) % len(FAMILY_INITIALS)]}."


def assign_names(db_path: Path | str | None = None) -> int:
    """Give every learner an invented display name, in the order they were created."""
    with db.connect(db_path) as conn:
        learners = db.rows(conn, "SELECT id FROM learners ORDER BY rowid")
        conn.executemany("UPDATE learners SET display_name = ? WHERE id = ?",
                         [(invented_name(i), row["id"]) for i, row in enumerate(learners)])
    return len(learners)


MILD_LANGS = ["ar", "sw", "fr", "am", "ha", "en"]
MILD_START_GRADES = [3, 4, 5, 4, 3, 5]

# Built-in fallback templates, used when packs/phrases/observations.yaml is missing.
FALLBACK_TEMPLATES: dict[str, dict[str, list[str]]] = {
    "struggling": {
        "en": [
            "Got stuck on the first step of {concept} and needed the worked example again.",
            "Mixed up the steps in {concept} and ran out of time.",
            "Found {concept} hard this term; answers were mostly guesses.",
        ]
    },
    "improving": {
        "en": [
            "Clearly more confident with {concept} than last term.",
            "Getting {concept} right more often; asked good questions.",
        ]
    },
    "strong": {
        "en": [
            "Finished {concept} quickly and helped a neighbour.",
            "Explained {concept} clearly to the group.",
        ]
    },
    "absent_often": {
        "en": [
            "Missed many lessons this term, so there are gaps in the work covered.",
            "Frequently absent; catching up on missed work has been difficult.",
        ]
    },
    "engaged": {
        "en": [
            "Took part well in {concept} and completed the class tasks.",
            "Steady work on {concept}, handed work in on time.",
        ]
    },
    "needs_support": {
        "en": [
            "Needs a little extra support with {concept}.",
            "Works carefully but slowly on {concept}; small-group time would help.",
        ]
    },
}


# --------------------------------------------------------------------------- helpers


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class _Ids:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.seen: set[str] = set()

    def new(self, prefix: str) -> str:
        while True:
            value = f"{prefix}_{self.rng.getrandbits(40):010x}"
            if value not in self.seen:
                self.seen.add(value)
                return value


def _load_pack(pack_id: str) -> dict[str, Any]:
    from .curriculum import read_pack_data

    return read_pack_data(get_settings().packs_dir / pack_id / "pack.yaml")


def _topo_order(concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable topological order: pack order, with prerequisites first."""
    by_id = {c["id"]: c for c in concepts}
    done: set[str] = set()
    out: list[dict[str, Any]] = []

    def visit(cid: str) -> None:
        if cid in done:
            return
        for r in by_id[cid]["requires"]:
            visit(r)
        done.add(cid)
        out.append(by_id[cid])

    for c in concepts:
        visit(c["id"])
    return out


def _load_templates() -> dict[str, dict[str, list[str]]]:
    templates = {sig: dict(langs) for sig, langs in FALLBACK_TEMPLATES.items()}
    path = get_settings().packs_dir / "phrases" / "observations.yaml"
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if isinstance(data, dict):
            for sig, langs in data.items():
                if isinstance(langs, dict):
                    for lang, items in langs.items():
                        if isinstance(items, list) and items:
                            templates.setdefault(sig, {})[lang] = [str(t) for t in items]
    return templates


def _stamp(rng: random.Random, year: int, term: int, late_rate: float = 0.08) -> tuple[str, int]:
    """recorded_at and logged_late for one record batch."""
    sm, sd, em, ed = TERM_DATES[term]
    start = dt.date(year, sm, sd)
    end = dt.date(year, em, ed)
    span = (end - start).days
    late = rng.random() < late_rate
    if late:
        day = end + dt.timedelta(days=rng.randint(25, 140))
    else:
        day = start + dt.timedelta(days=rng.randint(0, span))
    return f"{day.isoformat()}T{rng.randint(7, 16):02d}:{rng.choice([0, 15, 30, 45]):02d}:00", int(late)


# --------------------------------------------------------------------------- learner specs


def _build_specs(rng: random.Random, n_learners: int, years: int, by_id: dict[str, dict]) -> list[dict]:
    last_year = BASE_YEAR + years - 1
    planted = [
        dict(alias="Learner A-17", case="root_cause_strength", start_grade=3, start_year=BASE_YEAR,
             lang="sw", ability=0.72, tilt_sd=0.02),
        dict(alias="Learner B-04", case="what_worked", start_grade=4, start_year=BASE_YEAR,
             lang="en", ability=0.56, tilt_sd=0.0),
        dict(alias="Learner C-31", case="data_pattern_strength", start_grade=4, start_year=BASE_YEAR,
             lang="ha", ability=0.62, tilt_sd=0.0),
        dict(alias="Learner D-09", case="unknown_root", start_grade=3, start_year=BASE_YEAR,
             lang="fr", ability=0.68, tilt_sd=0.0),
        dict(alias="Learner E-22", case="too_little_data", start_grade=6, start_year=last_year,
             lang="am", ability=0.60, tilt_sd=0.0),
        dict(alias="Learner F-12", case="no_pattern", start_grade=4, start_year=BASE_YEAR,
             lang="en", ability=0.66, tilt_sd=0.0),
    ]
    if "literal-comprehension" in by_id and "problem-solving-multistep" in by_id:
        # All-subjects pack only: a reading gap in grade 3 that later shows up in maths word problems.
        planted.append(dict(alias="Learner R-08", case="cross_subject", start_grade=3, start_year=BASE_YEAR,
                            lang="sw", ability=0.74, tilt_sd=0.0))
    specs = [dict(p, mild=False) for p in planted]
    used = {s["alias"] for s in specs}
    letters = "GHJKLMNPRSTUVWXYZ"
    i = 0
    while len(specs) < n_learners:
        while True:
            alias = f"Learner {rng.choice(letters)}-{rng.randint(1, 99):02d}"
            if alias not in used:
                used.add(alias)
                break
        specs.append(dict(
            alias=alias, case="mild", mild=True,
            start_grade=MILD_START_GRADES[i % len(MILD_START_GRADES)], start_year=BASE_YEAR,
            lang=MILD_LANGS[i % len(MILD_LANGS)], ability=round(rng.uniform(0.58, 0.76), 3),
            tilt_sd=0.04,
        ))
        i += 1
    specs = specs[:n_learners]
    strands = sorted({c["strand"] for c in by_id.values()})
    for idx, s in enumerate(specs):
        s["tilt"] = {st: (rng.gauss(0, s["tilt_sd"]) if s["tilt_sd"] else 0.0) for st in strands}
        s["noise_sd"] = 0.03 if s["case"] == "no_pattern" else 0.04
        s["periods"] = []
        for y in range(s["start_year"], last_year + 1):
            for t in (1, 2, 3):
                if s["case"] == "too_little_data" and t == 1:
                    continue
                s["periods"].append((y, t))
        s["missing"] = set()
        s["sparse"] = set()
    # messy: whole missing terms for some mild learners, sparse terms for others
    mild = [s for s in specs if s["mild"]]
    for k, s in enumerate(mild):
        interior = s["periods"][2:-1]
        if k == 1 and interior:
            s["missing"] = {rng.choice(interior)}
        elif k == 2 and len(interior) > 3:
            s["missing"] = set(rng.sample(interior, 2))
        elif k == 3 and interior:
            s["missing"] = {rng.choice(interior)}
        for p in s["periods"]:
            if p not in s["missing"] and rng.random() < 0.2:
                s["sparse"].add(p)
    return specs


# --------------------------------------------------------------------------- generation


def _staff_school(db_path: Path | str | None, seed: int, pack_id: str) -> dict[str, Any]:
    """Turn the generated cohort into a staffed school: ten teachers, each teaching one subject, every
    teaching unit given to a teacher of its subject, and a described way of teaching for each teacher.
    It runs after the cohort is written and uses its own random stream, so the cohort itself is the
    same with or without it."""
    from .curriculum import load_pack

    rng = random.Random(seed + 1000)
    pack = load_pack(pack_id)
    subjects = list(pack.subjects) or [pack.subject]
    with db.connect(db_path) as conn:
        conn.executemany("INSERT INTO teachers (id, name, subjects) VALUES (?, ?, '[]')",
                         [(f"tch_{rng.getrandbits(40):010x}", name) for name in EXTRA_TEACHERS])
        roster = db.rows(conn, "SELECT id, name FROM teachers ORDER BY rowid")
        staff: dict[str, list[str]] = {subject: [] for subject in subjects}
        waiting = list(roster)
        for subject in subjects:                      # fill each subject's quota in turn
            for _ in range(STAFF_PER_SUBJECT.get(subject, 2)):
                if waiting:
                    staff[subject].append(waiting.pop(0)["id"])
        for extra, teacher in enumerate(waiting):     # anyone left joins a subject, round robin
            staff[subjects[extra % len(subjects)]].append(teacher["id"])
        subject_of = {tid: subject for subject, tids in staff.items() for tid in tids}
        conn.executemany("UPDATE teachers SET subjects = ? WHERE id = ?",
                         [(db.jdump([subject_of[t["id"]]]), t["id"]) for t in roster if t["id"] in subject_of])

        units = db.rows(conn, "SELECT id, year, grade, concept_id FROM teaching_units")
        moves = []
        for unit in units:
            concept = pack.concepts[unit["concept_id"]]
            team = staff.get(pack.strand_subject.get(concept.strand, subjects[0])) or [roster[0]["id"]]
            moves.append((team[(unit["grade"] + unit["year"]) % len(team)], unit["id"]))
        conn.executemany("UPDATE teaching_units SET teacher_id = ? WHERE id = ?", moves)
        conn.execute("UPDATE evidence SET teacher_id = (SELECT u.teacher_id FROM teaching_units u "
                     "WHERE u.id = evidence.unit_id) WHERE unit_id IS NOT NULL")

        # Each teacher's description follows what they recorded: the approach used most is "often".
        for index, teacher in enumerate(roster):
            used = db.rows(conn, "SELECT approach_id, COUNT(*) AS n FROM teaching_units WHERE teacher_id = ? "
                                 "GROUP BY approach_id ORDER BY n DESC, approach_id", (teacher["id"],))
            ranked = [u["approach_id"] for u in used]
            third = max(1, len(ranked) // 3)
            said = {a: "often" if i < third else "sometimes" if i < 2 * third else "rarely" for i, a in enumerate(ranked)}
            said.update({a: "rarely" for a in pack.approaches if a not in said})
            taught = db.rows(conn, "SELECT DISTINCT concept_id FROM teaching_units WHERE teacher_id = ?", (teacher["id"],))
            strands = sorted({pack.label(pack.concepts[t["concept_id"]].strand) for t in taught}) or ["the subject"]
            favourite = pack.label(ranked[0]) if ranked else "worked examples"
            answers = {"approaches": said, "languages": TEACHER_LANGUAGES[index % len(TEACHER_LANGUAGES)],
                       "class_size": CLASS_SIZES[index % len(CLASS_SIZES)],
                       "what_works": rng.choice(WHAT_WORKS).format(approach=favourite),
                       "wants_help_with": rng.choice(WANTS_HELP).format(strand=rng.choice(strands))}
            conn.execute("INSERT INTO teacher_profiles (teacher_id, answers, updated_at) VALUES (?, ?, ?)",
                         (teacher["id"], db.jdump(answers), CREATED_AT))
    return {"name": SCHOOL_NAME, "teachers": len(roster), "teachers_by_subject": {s: len(t) for s, t in staff.items()},
            "teaching_profiles": len(roster)}


def generate(
    db_path: Path | str | None = None,
    seed: int = 7,
    n_learners: int = 12,
    years: int = 4,
    pack_id: str | None = None,
    out_dir: Path | str | None = None,
    school: bool = False,
) -> dict[str, Any]:
    rng = random.Random(seed)
    ids = _Ids(rng)
    settings = get_settings()
    pack_id = pack_id or settings.default_pack
    out = Path(out_dir) if out_dir else ROOT / "data"
    out.mkdir(parents=True, exist_ok=True)
    inbox = out / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    pack = _load_pack(pack_id)
    concepts = _topo_order(pack["concepts"])
    by_id = {c["id"]: c for c in concepts}
    approach_ids = [a["id"] for a in pack["approaches"]]
    approach_label = {a["id"]: a["label"]["en"] for a in pack["approaches"]}
    templates = _load_templates()
    max_grade = pack["grades"][1]

    # ---- schedule: which concepts of a grade are taught in which term (same every year)
    schedule: dict[int, dict[int, list[str]]] = {}
    term_of: dict[str, int] = {}
    for g in range(pack["grades"][0], max_grade + 1):
        cs = [c["id"] for c in concepts if c["grade"] == g]
        size, extra = divmod(len(cs), 3)
        pos = 0
        schedule[g] = {}
        for t in (1, 2, 3):
            take = size + (1 if t <= extra else 0)
            schedule[g][t] = cs[pos:pos + take]
            pos += take
            for cid in schedule[g][t]:
                term_of[cid] = t

    specs = _build_specs(rng, n_learners, years, by_id)
    spec_by_case = {s["case"]: s for s in specs if not s["mild"]}
    if "unknown_root" in spec_by_case:  # the term the foundation was taught has no records at all
        spec_by_case["unknown_root"]["missing"].add((BASE_YEAR, term_of["division-basic"]))

    def grade_in(spec: dict, year: int) -> int:
        return spec["start_grade"] + (year - spec["start_year"])

    def teacher_index(grade: int, year: int) -> int:
        return (grade + (year - BASE_YEAR)) % len(TEACHERS)

    # ---- teachers
    teacher_ids = [ids.new("tch") for _ in TEACHERS]

    # ---- teaching units: one per (year, grade, concept) actually met by some learner
    pairs: set[tuple[int, int]] = set()
    for s in specs:
        for y in sorted({p[0] for p in s["periods"]}):
            g = grade_in(s, y)
            if g in schedule:
                pairs.add((y, g))
    b = spec_by_case.get("what_worked")
    b_pairs = {(y, grade_in(b, y)) for y in sorted({p[0] for p in b["periods"]})} if b else set()
    not_concrete = [a for a in approach_ids if a != "concrete_objects"]
    units: dict[tuple[int, int, str], dict[str, Any]] = {}
    for (y, g) in sorted(pairs):
        tidx = teacher_index(g, y)
        for t in (1, 2, 3):
            term_base = rng.choice(approach_ids)
            for cid in schedule[g][t]:
                approach = term_base if rng.random() < 0.65 else rng.choice(approach_ids)
                if (y, g) in b_pairs:
                    if t == 2:
                        approach = "concrete_objects"
                    elif approach == "concrete_objects":
                        approach = rng.choice(not_concrete)
                units[(y, g, cid)] = {
                    "id": ids.new("unt"), "teacher_id": teacher_ids[tidx], "year": y, "term": t,
                    "grade": g, "concept_id": cid, "approach_id": approach,
                    "note": f"Taught with: {approach_label[approach]}",
                }

    # ---- latent mastery
    def latent(spec: dict) -> dict[str, float]:
        ability = spec["ability"]
        case = spec["case"]
        gap_line = ability - 0.15
        m: dict[str, float] = {}
        for c in concepts:
            base = ability + spec["tilt"].get(c["strand"], 0.0) + rng.gauss(0, spec["noise_sd"])
            gaps = [m[r] for r in c["requires"] if m[r] < gap_line]
            val = min(base, min(gaps) + 0.03) if gaps else base
            # planted overrides
            if case == "root_cause_strength":
                if c["id"] == "division-basic":
                    val = 0.28
                if c["strand"] == "geometry":
                    val = max(val, 0.92)
            elif case == "unknown_root" and c["id"] == "division-basic":
                val = 0.30
            elif case == "cross_subject" and c["id"] == "literal-comprehension":
                val = 0.29
            elif case == "data_pattern_strength":
                if c["strand"] == "data" or {"working-with-data", "pattern-finding"} & set(c["skills"]):
                    val = max(val, 0.90)
            elif case == "what_worked":
                yr = spec["start_year"] + (c["grade"] - spec["start_grade"])
                u = units.get((yr, c["grade"], c["id"]))
                if u and u["approach_id"] == "concrete_objects":
                    val = min(0.93, val + 0.27)
            m[c["id"]] = _clip(val, 0.05, 0.97)
        return m

    # ---- rows
    teaching_rows = list(units.values())
    learner_rows: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    spec_state: dict[str, dict[str, Any]] = {}

    for spec in specs:
        lid = ids.new("lrn")
        spec["id"] = lid
        learner_rows.append({
            "id": lid, "alias": spec["alias"], "pack_id": pack_id, "start_year": spec["start_year"],
            "start_grade": spec["start_grade"], "home_language": spec["lang"], "created_at": CREATED_AT,
        })
        mastery = latent(spec)
        spec_state[lid] = {"mastery": mastery}
        seen_refs: set[str] = set()
        prev_mean: float | None = None

        def add(**kw: Any) -> None:
            ref = kw["source_ref"]
            if ref in seen_refs:
                return
            seen_refs.add(ref)
            kw.setdefault("concept_id", None)
            kw.setdefault("skill_id", None)
            kw.setdefault("score", None)
            kw.setdefault("absent_days", None)
            kw.setdefault("raw_text", None)
            kw.setdefault("language", "en")
            kw.setdefault("unit_id", None)
            kw.setdefault("status", "active")
            kw.update(id=ids.new("evd"), learner_id=lid)
            evidence.append(kw)

        for (y, t) in spec["periods"]:
            grade = grade_in(spec, y)
            if grade not in schedule or (y, t) in spec["missing"]:
                continue
            tidx = teacher_index(grade, y)
            tid = teacher_ids[tidx]
            term_concepts = schedule[grade][t]
            sparse = (y, t) in spec["sparse"]
            tiny = spec["case"] == "too_little_data"
            if tiny:
                term_concepts = term_concepts[:2]
            po = db.period_ord(y, t)

            def base_row(kind: str, **kw: Any) -> dict[str, Any]:
                at, late = _stamp(rng, y, t)
                return dict(kind=kind, year=y, term=t, period_ord=po, grade=grade, teacher_id=tid,
                            recorded_at=kw.pop("recorded_at", at), logged_late=kw.pop("logged_late", late), **kw)

            # quiz items
            for ci, cid in enumerate(term_concepts):
                c = by_id[cid]
                unit = units.get((y, grade, cid))
                stamp = _stamp(rng, y, t)
                n_items = rng.randint(1, 2) if (sparse or tiny) else rng.randint(3, 5)
                for k in range(1, n_items + 1):
                    score = round(_clip(rng.gauss(mastery[cid], 0.08)), 2)
                    add(**base_row(
                        "quiz_item", concept_id=cid, skill_id=(c["skills"][0] if c["skills"] else None),
                        score=score, raw_text=f"{c['label']['en']}: question {k}",
                        source_ref=f"quiz:{y}-T{t}-maths-{ci + 1:02d}#item{k}",
                        unit_id=unit["id"] if unit else None, recorded_at=stamp[0], logged_late=stamp[1]))
            term_mean = sum(mastery[c] for c in term_concepts) / len(term_concepts)

            # assignments and projects
            if not (sparse or tiny):
                for n in range(1, rng.randint(1, 2) + 1):
                    cid = rng.choice(term_concepts)
                    unit = units.get((y, grade, cid))
                    add(**base_row(
                        "assignment", concept_id=cid, score=round(_clip(rng.gauss(mastery[cid], 0.10)), 2),
                        raw_text=f"Take-home assignment {n}: {by_id[cid]['label']['en']}",
                        source_ref=f"assignment:{y}-T{t}-maths-{n}", unit_id=unit["id"] if unit else None))
                if t == 3:
                    cid = rng.choice(term_concepts)
                    unit = units.get((y, grade, cid))
                    skill = (by_id[cid]["skills"] or [rng.choice(["explaining-reasoning", "persistence-on-hard-problems"])])[0]
                    add(**base_row(
                        "project", concept_id=cid, skill_id=skill,
                        score=round(_clip(rng.gauss(mastery[cid], 0.10)), 2),
                        raw_text=f"End-of-year maths project: {by_id[cid]['label']['en']}",
                        source_ref=f"project:{y}-T3-maths-showcase", unit_id=unit["id"] if unit else None))

            # attendance
            if spec["case"] == "root_cause_strength" and y == spec["start_year"] and term_of["division-basic"] == t:
                absent = 17
            elif spec["mild"] and rng.random() < 0.10:
                absent = rng.randint(10, 14)
            elif spec["case"] in ("no_pattern", "data_pattern_strength"):
                absent = rng.randint(0, 3)
            else:
                absent = rng.choice([0, 1, 1, 2, 3, 4, 5, 6])
            if not tiny or t == 3:
                add(**base_row("attendance", absent_days=absent, raw_text=f"Absent {absent} days this term",
                               source_ref=f"register:{y}-T{t}"))

            # observations
            lo = min(term_concepts, key=lambda x: mastery[x])
            hi = max(term_concepts, key=lambda x: mastery[x])
            if mastery[lo] < 0.5:
                signal, target = "struggling", lo
            elif prev_mean is not None and term_mean - prev_mean > 0.1:
                signal, target = "improving", hi
            elif mastery[hi] > 0.85:
                signal, target = "strong", hi
            elif mastery[lo] < 0.6:
                signal, target = "needs_support", lo
            else:
                signal, target = "engaged", hi
            prev_mean = term_mean
            wanted = [(signal, target)]
            if absent >= 10:
                wanted.append(("absent_often", None))
            for n, (sig, cid) in enumerate(wanted, start=1):
                if tiny and t == 2:
                    continue
                if cid is not None and rng.random() < 0.12:
                    cid = None  # teacher did not say which topic
                lang_pick = rng.random()
                lang = spec["lang"] if (spec["lang"] != "en" and lang_pick < 0.4
                                        and spec["lang"] in templates.get(sig, {})) else "en"
                pool = templates.get(sig, {}).get(lang) or templates["engaged"]["en"]
                text = rng.choice(pool).replace("{concept}", by_id[cid]["label"]["en"] if cid else "the topic")
                add(**base_row("observation", concept_id=cid, raw_text=text, language=lang,
                               source_ref=f"note:{y}-T{t}-{n}"))

    # needs_review: a few mild-learner quiz rows tagged with a shorthand that is not in the pack
    mild_ids = {s["id"] for s in specs if s["mild"]}
    candidates = [i for i, e in enumerate(evidence)
                  if e["learner_id"] in mild_ids and e["kind"] == "quiz_item"]
    shorthand = ["fractions-adding", "mult-tables", "long-div"]
    for slot, i in enumerate(sorted(rng.sample(candidates, min(3, len(candidates))))):
        evidence[i]["concept_id"] = shorthand[slot % len(shorthand)]
        evidence[i]["unit_id"] = None
        evidence[i]["status"] = "needs_review"

    # ---- write to the database
    db.init_db(db_path)
    with db.connect(db_path) as conn:
        for table in ("parent_sessions", "parent_learners", "parents", "settings", "class_teachers", "class_learners", "classes", "sessions", "accounts", "record_requests", "approvals", "summaries", "findings", "audit_log",
                      "evidence",
                      "teaching_units", "learners", "teacher_profiles", "teachers"):
            conn.execute(f"DELETE FROM {table}")
        conn.executemany(
            "INSERT INTO teachers (id, name, subjects) VALUES (?, ?, ?)",
            [(tid, name, db.jdump(["maths"])) for tid, name in zip(teacher_ids, TEACHERS)])
        conn.executemany(
            "INSERT INTO learners (id, alias, pack_id, start_year, start_grade, home_language, created_at) "
            "VALUES (:id, :alias, :pack_id, :start_year, :start_grade, :home_language, :created_at)",
            learner_rows)
        conn.executemany(
            "INSERT INTO teaching_units (id, teacher_id, year, term, grade, concept_id, approach_id, note) "
            "VALUES (:id, :teacher_id, :year, :term, :grade, :concept_id, :approach_id, :note)",
            teaching_rows)
        conn.executemany(
            "INSERT INTO evidence (id, learner_id, kind, year, term, period_ord, grade, concept_id, skill_id, "
            "score, absent_days, raw_text, language, source_ref, teacher_id, unit_id, recorded_at, "
            "logged_late, status) VALUES (:id, :learner_id, :kind, :year, :term, :period_ord, :grade, "
            ":concept_id, :skill_id, :score, :absent_days, :raw_text, :language, :source_ref, :teacher_id, "
            ":unit_id, :recorded_at, :logged_late, :status)",
            evidence)
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("teachers", "learners", "teaching_units", "evidence")}
        late = conn.execute("SELECT COUNT(*) FROM evidence WHERE logged_late = 1").fetchone()[0]
        review = conn.execute("SELECT COUNT(*) FROM evidence WHERE status = 'needs_review'").fetchone()[0]
        null_obs = conn.execute(
            "SELECT COUNT(*) FROM evidence WHERE kind = 'observation' AND concept_id IS NULL").fetchone()[0]
        by_kind = {r[0]: r[1] for r in conn.execute("SELECT kind, COUNT(*) FROM evidence GROUP BY kind")}

    # ---- ground truth
    def rows_of(spec: dict, pred) -> list[dict]:
        return [e for e in evidence if e["learner_id"] == spec["id"] and pred(e)]

    def labels(rs: list[dict]) -> list[str]:
        return sorted({db.period_label(e["period_ord"]) for e in rs}, key=lambda s: (int(s[:4]), s[-1]))

    def root_path(spec: dict, target: str) -> list[str]:
        mastery = spec_state[spec["id"]]["mastery"]
        line = spec["ability"] - 0.15
        path = [target]
        cur = target
        while True:
            gaps = [r for r in by_id[cur]["requires"] if mastery[r] < line]
            if not gaps:
                return path
            cur = min(gaps, key=lambda r: mastery[r])
            path.append(cur)

    planted: dict[str, list[dict]] = {s["id"]: [] for s in specs}
    a = spec_by_case["root_cause_strength"]
    div_period = db.period_label(db.period_ord(a["start_year"], term_of["division-basic"]))
    a_path = root_path(a, "ratio-concept")
    a_mastery = spec_state[a["id"]]["mastery"]
    absence_rows = rows_of(a, lambda e: e["kind"] == "attendance" and e["absent_days"] and e["absent_days"] >= 15)
    planted[a["id"]] = [
        {"type": "root_cause", "target_concept": "ratio-concept", "also_affected": ["fraction-concept",
         "equivalent-fractions", "ratio-sharing"], "root_concept": a_path[-1], "path": a_path,
         "root_period": div_period, "context": "absence", "absent_days": 17,
         "root_evidence_kinds": ["quiz_item", "attendance"],
         "target_periods": labels(rows_of(a, lambda e: e["concept_id"] in ("ratio-concept", "ratio-sharing"))),
         "absence_evidence_ids": [e["id"] for e in absence_rows],
         "low_concepts_observed": sorted(
             c for c in {e["concept_id"] for e in rows_of(a, lambda e: e["kind"] == "quiz_item")}
             if c and c in by_id and a_mastery[c] < 0.5)},
        {"type": "strength", "scope": "strand", "scope_id": "geometry", "skill": "spatial-reasoning",
         "periods": labels(rows_of(a, lambda e: by_id.get(e["concept_id"] or "", {}).get("strand") == "geometry"))},
    ]
    if b:
        conc = sorted({e["concept_id"] for e in rows_of(b, lambda e: e["kind"] == "quiz_item")
                       if e["concept_id"] in by_id
                       and units.get((e["year"], e["grade"], e["concept_id"]), {}).get("approach_id") == "concrete_objects"})
        planted[b["id"]] = [{
            "type": "what_worked", "approach": "concrete_objects",
            "periods": labels(rows_of(b, lambda e: e["kind"] == "quiz_item" and e["term"] == 2)),
            "concepts": conc, "n_concepts": len(conc),
            "not_helpful_approaches": [x for x in approach_ids if x != "concrete_objects"],
            "note": "Scores rise in every term-2 unit taught with concrete objects, and stay lower with other approaches."}]
    c_spec = spec_by_case.get("data_pattern_strength")
    if c_spec:
        planted[c_spec["id"]] = [
            {"type": "strength", "scope": "strand", "scope_id": "data", "skill": "working-with-data",
             "periods": labels(rows_of(c_spec, lambda e: by_id.get(e["concept_id"] or "", {}).get("strand") == "data"))},
            {"type": "strength", "scope": "skill", "scope_id": "pattern-finding",
             "periods": labels(rows_of(c_spec, lambda e: e["skill_id"] == "pattern-finding"))}]
    d = spec_by_case.get("unknown_root")
    if d:
        d_period = db.period_label(db.period_ord(d["start_year"], term_of["division-basic"]))
        planted[d["id"]] = [{
            "type": "unknown_root", "target_concept": "fraction-concept", "root_concept": "division-basic",
            "missing_period": d_period, "expected_answer": "unknown",
            "target_periods": labels(rows_of(d, lambda e: e["concept_id"] == "fraction-concept")),
            "note": "Fractions are weak, the likely foundation was taught in a term with no records at all, "
                    "so the honest answer is that the cause is unknown."}]
    e_spec = spec_by_case.get("too_little_data")
    if e_spec:
        planted[e_spec["id"]] = [{
            "type": "too_little_data", "periods": labels(rows_of(e_spec, lambda e: True)),
            "n_evidence": len(rows_of(e_spec, lambda e: True)),
            "expected_answer": "not enough data to say anything"}]
    f_spec = spec_by_case.get("no_pattern")
    if f_spec:
        planted[f_spec["id"]] = [{"type": "no_pattern", "expected_answer": "no strength or struggle pattern"}]

    gt_path = out / "ground_truth.json"
    new_year = BASE_YEAR + years
    a_grade_new = grade_in(a, new_year)
    ar_spec = next((s for s in specs if s["lang"] == "ar" and s["mild"]), specs[-1])
    reg_specs = [a, ar_spec, specs[len(specs) // 2]]
    truth = {
        "seed": seed, "pack_id": pack_id,
        "note": "Synthetic data. Planted patterns are what an honest analysis should find.",
        "learners": [{"learner_id": s["id"], "alias": s["alias"], "planted": planted[s["id"]]} for s in specs],
        "inbox": {
            "quiz_sheet_A17_2025-T1.md": {"alias": a["alias"], "learner_id": a["id"], "period": f"{new_year}-T1",
                                          "expect": "low scores on ratio and proportion items"},
            "teacher_note_A17_sw.txt": {"alias": a["alias"], "learner_id": a["id"], "language": "sw"},
            "teacher_note_ar.txt": {"alias": ar_spec["alias"], "learner_id": ar_spec["id"], "language": "ar"},
            "register_2025-T1.csv": {"aliases": [s["alias"] for s in reg_specs], "period": f"{new_year}-T1"},
        },
    }
    with open(gt_path, "w", encoding="utf-8") as fh:
        json.dump(truth, fh, ensure_ascii=False, indent=2)

    # ---- inbox: raw files for a later ingest, each about a new term
    tname = TEACHERS[teacher_index(a_grade_new, new_year)]
    quiz_rows = [
        (1, "Simplify the ratio 12:18", "1", 2),
        (2, "Complete a table of equivalent ratios", "1", 2),
        (3, "Share 40 sweets in the ratio 3:5", "0", 3),
        (4, "Unit rate: price of one exercise book", "1", 2),
        (5, "Scale a recipe from 4 to 6 people", "0", 3),
        (6, "Are 3/4 and 9/12 in proportion? Explain", "-", 2),
        (7, "Use a map scale of 1:50 000", "1", 2),
    ]
    lines = [
        "# Quiz sheet (synthetic)", "",
        f"Learner: {a['alias']}", f"Grade: {a_grade_new}", f"Term: {new_year}-T1", f"Teacher: {tname}",
        f"Quiz: {new_year}-T1-maths-01 (ratios and proportion)", "",
        "| Item | Question | Marks | Out of |", "|------|----------|-------|--------|",
    ]
    lines += [f"| {n} | {q} | {m} | {o} |" for n, q, m, o in quiz_rows]
    lines += ["", "Item 6 not attempted. Marked late, after the holiday."]
    (inbox / f"quiz_sheet_A17_{new_year}-T1.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    (inbox / "teacher_note_A17_sw.txt").write_text(
        f"{a['alias']}, muhula wa kwanza {new_year}: bado anapata shida na uwiano na ulinganisho wa sehemu, "
        "hasa anapogawa kiasi katika sehemu zisizo sawa. Alifanya vizuri sana kwenye kazi ya jiometri na "
        "ulinganifu. Nitajaribu kutumia vitu halisi darasani wiki zijazo.\n", encoding="utf-8")
    (inbox / "teacher_note_ar.txt").write_text(
        f"{ar_spec['alias']}: في الفصل الأول من {new_year} تحسّن أداؤه في الكسور، لكنه غاب عن المدرسة "
        "أياماً كثيرة وسلّم الواجبات متأخراً. يحتاج إلى متابعة الحضور مع الأسرة ومسائل قصيرة بالأدوات "
        "المحسوسة.\n", encoding="utf-8")
    with open(inbox / f"register_{new_year}-T1.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["learner_alias", "year", "term", "days_open", "days_absent", "comment"])
        w.writerow([reg_specs[0]["alias"], new_year, 1, 58, 3, ""])
        w.writerow([reg_specs[1]["alias"], new_year, 1, 58, 11, "family travel, back in week 7"])
        w.writerow([reg_specs[2]["alias"], new_year, 1, 58, "", "register page missing"])
    (inbox / "README.md").write_text(
        "# Inbox (synthetic)\n\nEvery file here is made up by `athar.synth`. The learners are "
        "aliases, the teachers are fictional, and nothing refers to a real child or school.\n\n"
        f"Each file is about the new term {new_year}-T1, which is not in the database yet, so the agent "
        "can ingest it as fresh evidence.\n\n"
        "- `quiz_sheet_*.md`: item-level results, English markdown table\n"
        "- `teacher_note_A17_sw.txt`: a short teacher note in Swahili\n"
        "- `teacher_note_ar.txt`: a short teacher note in Arabic\n"
        "- `register_*.csv`: attendance for three learners, with a blank value on purpose\n",
        encoding="utf-8")

    assign_names(db_path)
    staffed = _staff_school(db_path, seed, pack_id) if school else None
    if staffed:
        counts["teachers"] = staffed["teachers"]
    total = counts["evidence"]
    return {
        "school": staffed,
        "counts": counts,
        "evidence_by_kind": by_kind,
        "logged_late": late,
        "logged_late_pct": round(100 * late / total, 1) if total else 0.0,
        "needs_review": review,
        "observations_without_concept": null_obs,
        "ground_truth": str(gt_path),
        "inbox": sorted(p.name for p in inbox.iterdir()),
        "planted": [{"case": s["case"], "learner_id": s["id"], "alias": s["alias"]} for s in specs if not s["mild"]],
        "missing_terms": {s["alias"]: [db.period_label(db.period_ord(*p)) for p in sorted(s["missing"])]
                          for s in specs if s["missing"]},
    }


if __name__ == "__main__":
    print(json.dumps(generate(), ensure_ascii=False, indent=2))

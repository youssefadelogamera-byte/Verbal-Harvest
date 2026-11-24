"""Getting records in: a marks sheet, a new learner, a document for the agent.

A marks sheet is one quiz. Learners go down the side, questions go across the top, and one row says
which topic each question tests. That topic row is the whole point: a single total cannot show which
topic a child is missing, a mark per question can.

    Learner code | Name      | Q1        | Q2        | Q3
    Topic        |           | <topic>   | <topic>   | <topic>
    Out of       |           | 2         | 3         | 2
    C-31         | Zainab H. | 1         | 3         | 0

No model reads a marks sheet. It is checked in plain code, shown to the teacher, and saved only when
the teacher confirms it and nothing in it is unclear. Names in the sheet are for the teacher's eyes:
they are not stored from an upload, and a learner is matched by record code only.
"""

from __future__ import annotations

import csv
import io
import re
import secrets
import time
from pathlib import Path
from typing import Any

from . import audit, db
from .curriculum import Pack, current_lang, load_pack

MAX_FILE_BYTES = 2_000_000
MAX_QUESTIONS = 60
DOCUMENT_TYPES = (".md", ".txt", ".csv")
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫", "01234567890123456789.")
_SKIP_MARKS = {"", "-", "–", "x", "na", "n/a", "abs", "absent", "غ", "غائب"}
_LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ"


def _norm(text: Any) -> str:
    return " ".join(str(text if text is not None else "").replace(" ", " ").split()).strip().lower()


def _number(text: Any) -> float | None:
    cleaned = str(text if text is not None else "").translate(_DIGITS).replace(",", ".").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _code(alias: str) -> str:
    return str(alias or "").replace("Learner ", "").strip().upper()


def _slug(text: str) -> str:
    """A short key made from a quiz name. Letters of any script are kept, so two quizzes named in Arabic
    do not end up with the same key."""
    return re.sub(r"[^\w]+", "-", _norm(text)).strip("-_")[:40] or "quiz"


def _quiz_ref(pack: Pack, year: int, term: int, grade: int, title: str, question: dict) -> str:
    """Where a saved mark came from. The same quiz uploaded twice gives the same key, so it is saved once.
    The subject and the grade are part of the key: 'Quiz 1' in Mathematics and 'Quiz 1' in Science are two quizzes."""
    topic = pack.concepts.get(question.get("topic_id") or "")
    subject = pack.strand_subject.get(topic.strand, "") if topic else ""
    return f"upload:{int(year)}-T{int(term)}:g{int(grade)}:{subject}:{_slug(title)}#q{question['n']}"


# ------------------------------------------------------------------ reading a file

def read_table(filename: str, data: bytes) -> list[list[str]]:
    """Rows of text cells from a .csv or .xlsx file."""
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("That file is too large for a marks sheet (the limit is 2 MB).")
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".xlsx":
        from openpyxl import load_workbook

        try:
            book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as exc:
            raise ValueError("That Excel file could not be read. Save it again as .xlsx or as CSV.") from exc
        sheet = book.worksheets[0]
        rows = [["" if cell is None else _cell_text(cell) for cell in row] for row in sheet.iter_rows(values_only=True)]
    elif suffix == ".csv":
        text = None
        for encoding in ("utf-8-sig", "cp1256", "latin-1"):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        sample = text[:2000]
        delimiter = ";" if sample.count(";") > sample.count(",") else "\t" if sample.count("\t") > sample.count(",") else ","
        rows = [list(row) for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    else:
        raise ValueError("Upload the marks template as an Excel file (.xlsx) or a CSV file.")
    return [[str(cell).strip() for cell in row] for row in rows if any(str(cell).strip() for cell in row)]


def _cell_text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


# ------------------------------------------------------------------ the template

def topics(pack: Pack, grade: int | None = None, term: int | None = None,
           subject: str | None = None) -> list[dict[str, Any]]:
    """Topics a question can be tagged with: the chosen grade first, then earlier grades."""
    found = [{"id": c.id, "label": pack.label(c.id), "grade": c.grade, "term": c.term,
              "strand": pack.label(c.strand), "subject": pack.strand_subject.get(c.strand)}
             for c in pack.concepts.values()]
    if subject:
        found = [t for t in found if t["subject"] == subject]
    if grade is not None:
        found = [t for t in found if t["grade"] <= grade]
    found.sort(key=lambda t: (-(t["grade"]), 0 if term is None or t["term"] in (None, term) else 1, t["term"] or 0))
    return found


# The words of the marks sheet, in the reader's language. A filled sheet is read in either language.
SHEET = {
    "en": {"code": "Learner code", "name": "Name", "q": "Q", "topic": "Topic", "out_of": "Out of",
           "marks": "Marks", "topics": "Topics", "columns": ["Topic", "Grade", "Term", "Area", "Topic id"],
           "pick": "Pick a topic from the list (see the Topics sheet).", "unknown": "Unknown topic"},
    "ar": {"code": "كود التلميذ", "name": "الاسم", "q": "س", "topic": "الموضوع", "out_of": "الدرجة من",
           "marks": "الدرجات", "topics": "الموضوعات", "columns": ["الموضوع", "الصف", "الترم", "المجال", "كود الموضوع"],
           "pick": "اختار موضوع من القائمة (شوف ورقة الموضوعات).", "unknown": "موضوع مش معروف"},
}
_CODE_ROW = ("learner", "كود")
_TOPIC_ROW = ("topic", "الموضوع")
_OUT_ROW = ("out of", "max", "الدرجة من", "من")


def sheet_words(lang: str | None = None) -> dict[str, Any]:
    return SHEET["ar" if (lang or current_lang.get()) == "ar" else "en"]


def template_rows(learners: list[dict[str, Any]], questions: int = 5, lang: str | None = None) -> list[list[str]]:
    w = sheet_words(lang)
    heads = [f"{w['q']}{i}" for i in range(1, questions + 1)]
    blank = [""] * questions
    rows = [[w["code"], w["name"], *heads], [w["topic"], "", *blank], [w["out_of"], "", *blank]]
    rows += [[_code(row["alias"]), row.get("name") or "", *blank] for row in learners]
    return rows


def template_csv(rows: list[list[str]]) -> bytes:
    out = io.StringIO()
    csv.writer(out, lineterminator="\r\n").writerows(rows)
    return ("﻿" + out.getvalue()).encode("utf-8")     # the mark lets Excel read Arabic names


def template_xlsx(rows: list[list[str]], topic_list: list[dict[str, Any]], lang: str | None = None) -> bytes:
    """The template as a workbook: a Marks sheet, and a Topics sheet the topic row picks from."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    w = sheet_words(lang)
    book = Workbook()
    sheet = book.active
    sheet.title = w["marks"]
    for row in rows:
        sheet.append(row)
    head, soft = PatternFill("solid", fgColor="2871F4"), PatternFill("solid", fgColor="E3E8F2")
    for cell in sheet[1]:
        cell.font, cell.fill = Font(bold=True, color="FFFFFF"), head
    for line in (2, 3):
        for cell in sheet[line]:
            cell.font, cell.fill = Font(bold=True), soft
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    sheet.column_dimensions["A"].width, sheet.column_dimensions["B"].width = 14, 24
    for col in range(3, len(rows[0]) + 1):
        sheet.column_dimensions[get_column_letter(col)].width = 26
    sheet.freeze_panes = "C4"
    listing = book.create_sheet(w["topics"])
    listing.append(w["columns"])
    if w is SHEET["ar"]:
        sheet.sheet_view.rightToLeft = listing.sheet_view.rightToLeft = True
    for cell in listing[1]:
        cell.font = Font(bold=True)
    for topic in topic_list:
        listing.append([topic["label"], topic["grade"], topic["term"] or "", topic["strand"], topic["id"]])
    listing.column_dimensions["A"].width, listing.column_dimensions["D"].width = 60, 34
    listing.column_dimensions["E"].width = 40
    if topic_list:
        pick = DataValidation(type="list", formula1=f"='{listing.title}'!$A$2:$A${len(topic_list) + 1}", allow_blank=True)
        pick.error, pick.errorTitle = w["pick"], w["unknown"]
        sheet.add_data_validation(pick)
        pick.add(f"C2:{get_column_letter(len(rows[0]))}2")
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


# ------------------------------------------------------------------ checking and saving a marks sheet

def check_marks(table: list[list[str]], *, title: str, year: int, term: int, grade: int,
                db_path=None, only: set[str] | None = None) -> dict[str, Any]:
    """Read a filled template. Nothing is saved. `problems` lists everything that is unclear; a sheet
    with problems cannot be saved, so a half-right sheet never becomes evidence."""
    title = " ".join(str(title or "").split())[:80]
    problems: list[str] = []
    if not title:
        problems.append("Give the quiz a name, for example 'Fractions quiz, week 6'.")
    if not 1 <= int(term) <= 3:
        problems.append("The term must be 1, 2 or 3.")
    with db.connect(db_path) as conn:
        learners = db.rows(conn, "SELECT id, alias, display_name, pack_id FROM learners")
        existing = {(row["learner_id"], row["source_ref"]) for row in db.rows(
            conn, "SELECT learner_id, source_ref FROM evidence WHERE source_ref LIKE ?",
            (f"upload:{int(year)}-T{int(term)}:g{int(grade)}:%",))}
    pack = load_pack(learners[0]["pack_id"] if learners else None)
    by_code = {_code(row["alias"]): row for row in learners}
    # A topic may be named in any language the map has: a sheet filled in Arabic is read in English mode too.
    by_label = {_norm(text): c.id for c in pack.concepts.values() for text in c.label.values()}

    def find_row(*starts: str) -> list[str] | None:
        return next((row for row in table if _norm(row[0]).startswith(starts)), None)

    header, topic_row, out_row = find_row(*_CODE_ROW), find_row(*_TOPIC_ROW), find_row(*_OUT_ROW)
    if header is None or topic_row is None or out_row is None:
        return {"ok": False, "questions": [], "learners": [], "new_rows": 0, "already_imported": 0, "blank": 0,
                "quiz": {"title": title, "year": year, "term": term, "grade": grade},
                "problems": [("This does not look like the marks template. It needs a 'Learner code' row, a 'Topic' row "
                              "and an 'Out of' row. Download a fresh template and fill that in.")]}
    columns = [i for i in range(2, len(header)) if header[i].strip()][:MAX_QUESTIONS]
    cell = lambda row, i: row[i].strip() if i < len(row) else ""
    questions = []
    for n, i in enumerate(columns, start=1):
        name, raw_topic, out_of = header[i].strip(), cell(topic_row, i), _number(cell(out_row, i))
        topic_id = raw_topic if raw_topic in pack.concepts else by_label.get(_norm(raw_topic))
        if not raw_topic:
            problems.append(f"{name}: no topic. Say which topic this question tests.")
        elif topic_id is None:
            problems.append(f"{name}: '{raw_topic}' is not a topic in the curriculum map. Pick one from the Topics sheet.")
        if out_of is None or out_of <= 0:
            problems.append(f"{name}: the 'Out of' mark is missing or is not a number above zero.")
        questions.append({"n": n, "name": name, "topic_id": topic_id, "topic": pack.label(topic_id) if topic_id else raw_topic,
                          "out_of": out_of})
    if not questions:
        problems.append("The sheet has no question columns.")
    rows_out, new_rows, already, blank, seen = [], 0, 0, 0, set()
    for row in table:
        if row in (header, topic_row, out_row) or not row[0].strip():
            continue
        code = _code(row[0])
        learner = by_code.get(code)
        if learner is None:
            problems.append(f"'{row[0]}' is not a learner record code in this school.")
            continue
        if only is not None and learner["id"] not in only:
            problems.append(f"{code} is not in one of your classes.")
            continue
        if code in seen:
            problems.append(f"{code} appears twice in the sheet.")
            continue
        seen.add(code)
        marks = []
        for q, i in zip(questions, columns, strict=True):
            raw = cell(row, i)
            if _norm(raw) in _SKIP_MARKS:
                marks.append(None)
                blank += 1
                continue
            mark = _number(raw)
            if mark is None:
                problems.append(f"{code}, {q['name']}: '{raw}' is not a mark.")
            elif mark < 0 or (q["out_of"] and mark > q["out_of"]):
                problems.append(f"{code}, {q['name']}: {raw} is outside 0 to {_cell_text(q['out_of'])}.")
            else:
                ref = _quiz_ref(pack, year, term, grade, title, q)
                if (learner["id"], ref) in existing:
                    already += 1
                else:
                    new_rows += 1
            marks.append(mark)
        rows_out.append({"learner_id": learner["id"], "code": code, "name": learner["display_name"] or learner["alias"],
                         "marks": marks})
    if not rows_out and not problems:
        problems.append("The sheet has no learner rows.")
    return {"ok": not problems, "quiz": {"title": title, "year": int(year), "term": int(term), "grade": int(grade)},
            "questions": questions, "learners": rows_out, "problems": problems[:40], "problem_count": len(problems),
            "new_rows": new_rows, "already_imported": already, "blank": blank}


def save_marks(table: list[list[str]], *, title: str, year: int, term: int, grade: int, teacher_id: str,
               filename: str = "", db_path=None, only: set[str] | None = None) -> dict[str, Any]:
    """Save a checked marks sheet as evidence: one row per learner per question, each tagged with its
    topic. Marks already saved from the same quiz are skipped, so uploading a sheet twice is harmless."""
    started = time.perf_counter()
    checked = check_marks(table, title=title, year=year, term=term, grade=grade, db_path=db_path, only=only)
    if not checked["ok"]:
        raise ValueError("The sheet still has problems: " + " ".join(checked["problems"][:3]))
    quiz = checked["quiz"]
    with db.connect(db_path) as conn:
        teacher = db.one(conn, "SELECT id FROM teachers WHERE id = ?", (teacher_id,))
        if teacher is None:
            raise ValueError("Only a named teacher can add records. Choose your name first.")
        learner = db.one(conn, "SELECT pack_id FROM learners LIMIT 1")
        pack = load_pack(learner["pack_id"] if learner else None)
        units = {row["concept_id"]: row["id"] for row in db.rows(
            conn, "SELECT id, concept_id FROM teaching_units WHERE year = ? AND grade = ?", (quiz["year"], quiz["grade"]))}
        saved, skipped, now = 0, 0, db.now_iso()
        for row in checked["learners"]:
            for q, mark in zip(checked["questions"], row["marks"], strict=True):
                if mark is None:
                    continue
                ref = _quiz_ref(pack, quiz["year"], quiz["term"], quiz["grade"], quiz["title"], q)
                if db.one(conn, "SELECT 1 AS yes FROM evidence WHERE learner_id = ? AND source_ref = ?",
                          (row["learner_id"], ref)):
                    skipped += 1
                    continue
                skills = pack.concepts[q["topic_id"]].skills
                conn.execute(
                    "INSERT INTO evidence (id, learner_id, kind, year, term, period_ord, grade, concept_id, skill_id, "
                    "score, raw_text, language, source_ref, teacher_id, unit_id, recorded_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (db.new_id("evd"), row["learner_id"], "quiz_item", quiz["year"], quiz["term"],
                     db.period_ord(quiz["year"], quiz["term"]), quiz["grade"], q["topic_id"], skills[0] if skills else None,
                     round(mark / q["out_of"], 3),
                     (f"{quiz['title']}: {q['name']} ({_cell_text(mark)} of {_cell_text(q['out_of'])})"),
                     "en", ref, teacher_id, units.get(q["topic_id"]), now))
                saved += 1
        out = {"saved": saved, "skipped_already_saved": skipped, "learners": len(checked["learners"]),
               "questions": len(checked["questions"]), "quiz": quiz}
        audit.write_row(conn, "import_marks", {"file": Path(filename or "").name[:120], **quiz,
                                               "topics": [q["topic_id"] for q in checked["questions"]]},
                        out, True, int((time.perf_counter() - started) * 1000), actor=f"teacher:{teacher_id}")
    return out


# ------------------------------------------------------------------ a new learner record

def add_learner(name: str, grade: int, year: int, home_language: str = "ar", actor: str = "system",
                db_path=None, class_id: str | None = None) -> dict[str, Any]:
    """Open a record for a learner. The record code (such as K-42) is what documents and the agent use.
    The name is shown to teachers only."""
    started = time.perf_counter()
    name = " ".join(str(name or "").split())
    if not 2 <= len(name) <= 60:
        raise ValueError("Give the learner's name as the class list shows it (2 to 60 characters).")
    with db.connect(db_path) as conn:
        other = db.one(conn, "SELECT pack_id FROM learners LIMIT 1")
        pack = load_pack(other["pack_id"] if other else None)
        if not pack.grades[0] <= int(grade) <= pack.grades[1]:
            raise ValueError(f"This curriculum covers grades {pack.grades[0]} to {pack.grades[1]}.")
        taken = {row["alias"] for row in db.rows(conn, "SELECT alias FROM learners")}
        for _ in range(500):
            alias = f"Learner {secrets.choice(_LETTERS)}-{secrets.randbelow(99) + 1:02d}"
            if alias not in taken:
                break
        else:
            raise ValueError("No free record code is left. Tell the person who looks after this system.")
        if class_id and db.one(conn, "SELECT id FROM classes WHERE id = ?", (class_id,)) is None:
            raise ValueError(f"Unknown class '{class_id}'.")
        learner_id = db.new_id("lrn")
        conn.execute("INSERT INTO learners (id, alias, display_name, pack_id, start_year, start_grade, home_language, "
                     "created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (learner_id, alias, name, pack.id, int(year), int(grade), str(home_language or "ar")[:8], db.now_iso()))
        if class_id:
            conn.execute("INSERT INTO class_learners (class_id, learner_id) VALUES (?,?)", (class_id, learner_id))
        out = {"learner_id": learner_id, "alias": alias, "code": _code(alias), "grade": int(grade), "class_id": class_id}
        # The audit log holds the record code, never the name.
        audit.write_row(conn, "add_learner", {"grade": int(grade), "year": int(year)}, out, True,
                        int((time.perf_counter() - started) * 1000), actor=actor)
    return {**out, "name": name}


# ------------------------------------------------------------------ a document for the agent

def save_document(folder: Path, filename: str, data: bytes) -> dict[str, Any]:
    """Put a quiz sheet or a teacher's note in the inbox, where the agent can be asked to read it.
    The agent reads rows from it when a teacher starts a run; saving the file adds no record."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename or "").name).strip("._") or "document"
    if Path(name).suffix.lower() not in DOCUMENT_TYPES:
        raise ValueError("The agent reads text files: .md, .txt or .csv.")
    if len(data) > 1_000_000:
        raise ValueError("That file is too large (the limit is 1 MB).")
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("That file is not plain text. Save it as UTF-8 text and try again.") from exc
    folder.mkdir(parents=True, exist_ok=True)
    target, n = folder / name, 1
    while target.exists():
        n += 1
        target = folder / f"{Path(name).stem}-{n}{Path(name).suffix}"
    target.write_bytes(data)
    return {"name": target.name, "bytes": len(data)}

"""Adding to the curriculum: more grades, or another subject, on top of the installed pack.

A school gives Athar the contents page of a book, or types the topics in. That makes a draft: a list of
topics, the area each belongs to, and which topic each one needs first. A named teacher checks every topic
and every link, and only then is the draft approved and laid over the installed curriculum.

Rules this module keeps:

- A model only reads and suggests. It turns a page into a list of topic names and proposes links. Plain
  code checks everything it returns: an id it names must be in the list it was given, a topic can only need
  a topic from the same grade or an earlier one, and anything that does not hold up is dropped.
- Nothing a model returned is used before a teacher approves it. Approving is not an MCP tool, so the
  agent cannot add to the curriculum or approve an addition.
- The installed pack is never rewritten. An addition is a row in the database, and it can be withdrawn
  as long as no record points at one of its topics.
- A contents page carries no learner data, and none is sent with it.
"""

from __future__ import annotations

import base64
import copy
import io
import json
import os
import re
import time
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import httpx

from . import audit, db
from .config import get_settings
from .curriculum import Pack, _additions, apply_addition, build_pack, current_lang, read_pack_data
from .photo import _plain, kind_of

MAX_FILE = 8 * 1024 * 1024
MAX_TEXT = 24_000           # characters of a document given to the model
MAX_TOPICS = 80
MAX_LINKS = 3               # "needs first" links on one topic
MAX_NEEDED_BY = 3           # later installed topics a model may hang on one new topic (a teacher may add more)
GRADES = (1, 12)
TEXT_TYPES = (".txt", ".md", ".csv")
_ARABIC = re.compile(r"[؀-ۿ]")
_TERM_WORDS = (("one", 1), ("two", 2), ("three", 3), ("first", 1), ("second", 2), ("third", 3), ("الأول", 1), ("الاول", 1), ("الثاني", 2), ("الثالث", 3))

READ_PROMPT = """Below is the contents page, or a list of topics, from a school book.
Subject: {subject}. Grade: {grade}.

List the topics taught, in the order they appear. Reply with JSON only, in this shape:
{{"topics": [{{"en": "the topic as a short name in English",
             "ar": "the topic as a short name in Arabic, copied from the page when the page is in Arabic",
             "term": the term it is taught in as a number, or null if the page does not say,
             "area": "the id of the AREA it fits best, or a short name for a new area if none fits",
             "skills": ["up to two ids from SKILLS that the topic clearly exercises, or an empty list"]}}]}}

Rules:
- One entry for each topic or lesson. A unit heading is not a topic, unless no lessons are listed under it.
- Leave out revision, tests, projects, the introduction, the index and page numbers.
- Do not add a topic that is not on the page. Do not explain. Keep each name under ten words, and keep a
  number or a range that is part of the name ("Numbers up to 10,000", not "Numbers").
- A heading such as "Term 2", "Second term", "الفصل الدراسي الثاني" or "الترم الثاني" gives the term of
  every topic under it, until the next such heading.
- Most topics exercise no particular skill: give an empty list unless the topic is plainly about that skill.
- Use only ids from AREAS and SKILLS. At most {limit} topics.

AREAS (id: name):
{areas}

SKILLS (id: name):
{skills}
"""

NEEDS_PROMPT = """These are topics from a school curriculum. Subject: {subject}.

For each NEW topic, name the topics a pupil must already have learned before it. Choose only from the
ids listed under NEW and EARLIER. Reply with JSON only, in this shape:
{{"needs": {{"N3": ["N1", "an-earlier-id"], "N4": []}}}}

Rules:
- Name the one topic the new one builds on most directly, usually the topic taught just before it in the
  same part of the subject. Name a second only when the new topic truly cannot be learned without both.
- An empty list is a good answer. The first topic of a new part of the subject often needs nothing.
- Do not give the same answer for most of the list. A basic topic such as reading numbers is not what
  every later topic "needs": name what comes directly before, not everything that came earlier.
- A new topic can only need a new topic that comes before it in the list.

NEW (id: name, grade, term):
{new}

EARLIER (id: name, grade):
{earlier}
"""

NEEDED_BY_PROMPT = """These are topics from a school curriculum. Subject: {subject}.

The NEW topics were just added for grade {grade}. The LATER topics are already taught in later grades.
For each LATER topic, name the NEW topics a pupil must already have learned before it. Reply with JSON
only, in this shape:
{{"needs": {{"a-later-id": ["N2"], "another-later-id": []}}}}

Rules:
- Name a new topic only when the later topic continues it directly: the same idea, taken one step further.
- Most later topics need none of the new ones. Leave those out. When in doubt, leave it out.
- At most one new topic for each later topic. Use only the ids listed below.

NEW (id: name):
{new}

LATER (id: name, grade):
{later}
"""


# ------------------------------------------------------------------ reading a file

def text_of_file(filename: str, data: bytes) -> str:
    """The words of an uploaded file. Plain text, a Word file or an Excel sheet. A PDF is not read here:
    a photo or a screenshot of the contents page is, by the model."""
    if not data:
        raise ValueError("That file is empty.")
    if len(data) > MAX_FILE:
        raise ValueError("That file is too large (the limit is 8 MB).")
    kind = Path(filename or "").suffix.lower()
    if kind in TEXT_TYPES:
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("That file is not plain text. Save it as UTF-8 text and try again.") from exc
    if kind == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                root = ElementTree.fromstring(archive.read("word/document.xml"))
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
            raise ValueError("That Word file could not be opened. Paste the list of topics in instead.") from exc
        word = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        lines = ["".join(t.text or "" for t in paragraph.iter(word + "t")) for paragraph in root.iter(word + "p")]
        return "\n".join(line for line in lines if line.strip())
    if kind == ".xlsx":
        from openpyxl import load_workbook
        try:
            book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as exc:
            raise ValueError("That Excel file could not be opened. Paste the list of topics in instead.") from exc
        lines = []
        for sheet in book.worksheets:
            for row in sheet.iter_rows(values_only=True):
                cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
                if cells:
                    lines.append(" | ".join(cells))
        return "\n".join(lines)
    if kind == ".pdf":
        raise ValueError("Athar does not read PDF files here. Take a screenshot or a photo of the contents page and "
                         "upload that, or paste the list of topics in.")
    raise ValueError("Use a text file (.txt, .md, .csv), a Word file (.docx), an Excel file (.xlsx), or a photo of "
                     "the contents page (JPEG or PNG).")


def _clip(text: Any, limit: int = 120) -> str:
    return " ".join(str(text or "").split())[:limit]


def _both(en: Any, ar: Any = "") -> dict[str, str]:
    """A label in both languages from whatever was given. One name in Arabic letters is the Arabic name;
    the English one then repeats it, because every topic must have a name to fall back on."""
    en, ar = _clip(en), _clip(ar)
    if en and not ar and _ARABIC.search(en):
        ar = en
    if ar and not en:
        en = ar
    return {"en": en, "ar": ar} if ar else {"en": en}


def parse_lines(text: str, terms: int) -> list[dict[str, Any]]:
    """Topics typed or pasted by a person, one on each line, with no model. A line such as "Term 2" or
    "الترم الثاني" sets the term for the lines under it. A line that starts with # names the area for the
    lines under it. "English name | الاسم بالعربي" gives both names."""
    topics, term, area = [], None, ""
    for raw in str(text or "").splitlines():
        line = re.sub(r"^[\s\-*•·•]+|^\s*\d+[.)\-:]\s*", "", raw).strip()
        if not line:
            continue
        if raw.lstrip().startswith("#"):
            area = _clip(raw.lstrip("# \t"), 60)
            continue
        plain = _plain(line)
        named = re.fullmatch(r"(?:term|semester|الترم|الفصل الدراسي)\s*(\d|[^\d\s]+)", plain)
        if named:
            word = named.group(1)
            found = int(word) if word.isdigit() else next((n for w, n in _TERM_WORDS if _plain(w) == word), None)
            if found and 1 <= found <= terms:
                term = found
                continue
        first, _, second = line.partition("|")
        names = _both(first, second) if second.strip() else _both(line)
        if second.strip() and _ARABIC.search(first) and not _ARABIC.search(second):
            names = _both(second, first)
        topics.append({**names, "term": term, "area": area, "skills": []})
    return topics


# ------------------------------------------------------------------ the model reads and suggests

def _ask(prompt: str, *, image: bytes | None = None, model: str | None = None, max_tokens: int = 6000) -> dict[str, Any]:
    """One question to the model, answered as JSON. Raises ValueError in plain words when it cannot answer."""
    settings = get_settings()
    content: Any = prompt
    if image is not None:
        kind = kind_of(image)
        content = [{"type": "text", "text": prompt},
                   {"type": "image_url", "image_url": {"url": f"data:{kind};base64," + base64.b64encode(image).decode("ascii")}}]
    body: dict[str, Any] = {"model": model or settings.llm_model, "temperature": 0, "max_tokens": max_tokens,
                            "messages": [{"role": "user", "content": content}]}
    if os.environ.get("ATHAR_LLM_REASONING", "none") != "default":
        body["reasoning_effort"] = os.environ.get("ATHAR_LLM_REASONING", "none")
    try:
        reply = httpx.post(f"{settings.llm_base_url.rstrip('/')}/chat/completions", json=body, timeout=600,
                           headers={"Authorization": f"Bearer {settings.llm_api_key}"})
    except httpx.HTTPError as exc:
        raise ValueError("The model did not answer. Start it and try again, or type the topics in.") from exc
    if reply.status_code == 503:
        raise ValueError("The model is still starting. Wait a minute and try again.")
    if reply.status_code >= 400:
        raise ValueError("The model could not read that. If it is a photo, the model may not be one that can see "
                         "pictures. Paste the list of topics in instead.")
    try:
        text = reply.json()["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ValueError("The model did not return anything Athar could read. Type the topics in instead.") from exc
    match = re.search(r"\{.*\}", text.split("</think>")[-1], flags=re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        raise ValueError("The model did not return anything Athar could read. Type the topics in instead.")   # noqa: TRY004
    return data


def _menu(items: list[tuple[str, str]]) -> str:
    return "\n".join(f"{item_id}: {name}" for item_id, name in items) or "(none)"


def read_topics(pack: Pack, subject: dict, grade: int, *, text: str = "", image: bytes | None = None,
                model: str | None = None) -> list[dict[str, Any]]:
    """Ask the model for the topics on a page. Returns raw entries; `clean` checks them."""
    areas = [(sid, " / ".join(sorted(set(label.values())))) for sid, label in pack.strands.items()
             if pack.strand_subject.get(sid) == subject["id"]]
    skills = [(sid, label.get("en", sid)) for sid, label in pack.skills.items() if pack.skill_kinds.get(sid) == "thinking"]
    prompt = READ_PROMPT.format(subject=subject["label"].get("en"), grade=grade, limit=MAX_TOPICS,
                                areas=_menu(areas), skills=_menu(skills))
    if image is None:
        prompt += "\nTHE PAGE:\n" + text[:MAX_TEXT]
    found = _ask(prompt, image=image, model=model).get("topics")
    return [t for t in found if isinstance(t, dict)] if isinstance(found, list) else []


def _ids(value: Any) -> list[str]:
    return [str(v) for v in value if isinstance(v, (str, int))] if isinstance(value, list) else []


def suggest_links(pack: Pack, subject: dict, grade: int, topics: list[dict[str, Any]], *,
                  model: str | None = None) -> None:
    """Ask the model which topic each new one needs first, and which later installed topics need a new one.
    Writes `needs` and `needed_by` on the topics. Only ids from the lists it was shown are kept, and
    `clean` checks the order of grades afterwards."""
    if not topics:
        return
    numbered = {f"N{i + 1}": topic for i, topic in enumerate(topics)}
    same = [c for c in pack.concepts.values() if pack.strand_subject.get(c.strand) == subject["id"]]
    earlier = sorted((c for c in same if grade - 3 <= c.grade <= grade), key=lambda c: (-c.grade, c.term or 0, c.id))[:120]
    name = subject["label"].get("en")
    new = "\n".join(f"{n}: {t['en']}, grade {t['grade']}, term {t['term']}" for n, t in numbered.items())
    answer = _ask(NEEDS_PROMPT.format(subject=name, new=new, earlier="\n".join(
        f"{c.id}: {c.label.get('en')}, grade {c.grade}" for c in earlier) or "(none)"), model=model, max_tokens=3000)
    known = {c.id for c in earlier}
    order = list(numbered)
    needs = answer.get("needs") if isinstance(answer.get("needs"), dict) else {}
    for n, topic in numbered.items():
        before = set(order[:order.index(n)])
        # A model tends to chain each topic to the one before it. Across two areas of the subject that is
        # almost never a real dependency, so such a suggestion is dropped; a teacher can still add the link.
        picked = [i for i in _ids(needs.get(n)) if i in known or (i in before and numbered[i]["area"] == topic["area"])]
        topic["needs"] = [numbered[i]["key"] if i in numbered else i for i in dict.fromkeys(picked)][:MAX_LINKS]
    _drop_shortcuts(topics)
    later = sorted((c for c in same if c.grade == grade + 1), key=lambda c: (c.term or 0, c.id))[:60]
    if not later:
        return
    answer = _ask(NEEDED_BY_PROMPT.format(subject=name, grade=grade,
                                          new="\n".join(f"{n}: {t['en']}" for n, t in numbered.items()),
                                          later="\n".join(f"{c.id}: {c.label.get('en')}, grade {c.grade}" for c in later)),
                  model=model, max_tokens=3000)
    needs = answer.get("needs") if isinstance(answer.get("needs"), dict) else {}
    later_ids = {c.id for c in later}
    for later_id, wanted in needs.items():
        if later_id not in later_ids:
            continue
        for n in list(dict.fromkeys(i for i in _ids(wanted) if i in numbered))[:1]:
            numbered[n].setdefault("needed_by", []).append(later_id)
    for topic in topics:                                   # the earliest later topics are the direct continuations
        order = {c.id: i for i, c in enumerate(later)}
        topic["needed_by"] = sorted(topic.get("needed_by") or [], key=lambda cid: order[cid])[:MAX_NEEDED_BY]


def drop_blanket_skills(topics: list[dict[str, Any]]) -> None:
    """A skill a model put on nearly every topic says nothing about any of them, so it is taken off all."""
    if len(topics) < 4:
        return
    for skill in {s for t in topics for s in t["skills"]}:
        if sum(skill in t["skills"] for t in topics) > 0.7 * len(topics):
            for topic in topics:
                topic["skills"] = [s for s in topic["skills"] if s != skill]


def _drop_shortcuts(topics: list[dict[str, Any]]) -> None:
    """Among the new topics, a link that only repeats a longer path says nothing: if C needs B and B needs A,
    then "C needs A" is taken out. Plain graph logic, and it keeps a suggestion list short enough to check."""
    needs = {t["key"]: [r for r in t.get("needs") or []] for t in topics}

    def reaches(start: str, goal: str, skip: tuple[str, str]) -> bool:
        stack, seen = [start], set()
        while stack:
            at = stack.pop()
            for nxt in needs.get(at, []):
                if (at, nxt) == skip or nxt in seen:
                    continue
                if nxt == goal:
                    return True
                seen.add(nxt)
                stack.append(nxt)
        return False

    for topic in topics:
        key = topic["key"]
        for ref in list(needs[key]):
            if ref in needs and reaches(key, ref, (key, ref)):
                needs[key].remove(ref)
        topic["needs"] = needs[key]


# ------------------------------------------------------------------ plain-code checks

def _subject(pack: Pack, subject_id: str, new_subject: str) -> dict[str, Any]:
    if subject_id and subject_id in pack.subjects:
        return {"id": subject_id, "label": dict(pack.subjects[subject_id]), "new": False}
    name = _clip(new_subject, 60)
    if not name:
        raise ValueError("Choose the subject, or type the name of a new one.")
    for sid, label in pack.subjects.items():
        if _plain(name) in {_plain(v) for v in label.values()}:
            return {"id": sid, "label": dict(label), "new": False}
    return {"id": "", "label": _both(name), "new": True}


def clean(pack: Pack, draft: dict[str, Any], topics: list[Any], areas: list[Any] | None = None) -> dict[str, Any]:
    """Make topics and areas safe to store and to show, whoever wrote them: a model or the page. Everything
    is rebuilt from scratch. A link is kept only when both ends exist and the needed topic is not taught
    later than the one that needs it. Nothing is repaired by guessing."""
    subject, grade, terms = draft["subject"], int(draft["grade"]), pack.terms
    own = {sid: label for sid, label in pack.strands.items() if pack.strand_subject.get(sid) == subject["id"]}
    by_name = {_plain(text): sid for sid, label in own.items() for text in label.values()}
    new_areas: dict[str, dict[str, Any]] = {}

    def new_area(en: Any, ar: Any = "") -> str:
        label = _both(_clip(en, 60), _clip(ar, 60))
        if not label["en"]:
            return ""
        if _plain(label["en"]) in by_name:                 # it is one of the subject's own areas after all
            return by_name[_plain(label["en"])]
        for key, area in new_areas.items():
            if _plain(area["en"]) == _plain(label["en"]):
                return key
        key = f"a{len(new_areas) + 1}"
        new_areas[key] = {"key": key, "en": label["en"], "ar": label.get("ar", "")}
        return key

    def area_key(named: Any) -> str:
        named = _clip(named, 60)
        if not named or named in own:
            return named
        if named in given:                                  # an area made earlier in this draft, by its key
            if named not in mapped:
                mapped[named] = new_area(given[named].get("en"), given[named].get("ar"))
            return mapped[named]
        return new_area(named)

    given = {str(a.get("key")): a for a in (areas or []) if isinstance(a, dict) and a.get("key")}
    mapped: dict[str, str] = {}
    rename: dict[str, str] = {}
    out, seen = [], set()
    for raw in topics[:MAX_TOPICS * 2]:
        if not isinstance(raw, dict):
            continue
        label = _both(raw.get("en"), raw.get("ar"))
        if not label["en"] or _plain(label["en"]) in seen or len(out) >= MAX_TOPICS:
            continue
        seen.add(_plain(label["en"]))
        try:
            topic_grade = int(raw.get("grade") or grade)
            term = int(raw.get("term") or draft.get("term") or 1)
        except (TypeError, ValueError):
            topic_grade, term = grade, int(draft.get("term") or 1)
        area = area_key(raw.get("area"))
        key = f"t{len(out) + 1}"
        if raw.get("key"):
            rename[str(raw["key"])] = key
        out.append({"key": key, "en": label["en"], "ar": label.get("ar", ""),
                    "grade": min(max(topic_grade, GRADES[0]), GRADES[1]), "term": term if 1 <= term <= terms else 1,
                    "area": area, "skills": [s for s in dict.fromkeys(_ids(raw.get("skills"))) if s in pack.skills][:3],
                    "needs": _ids(raw.get("needs")), "needed_by": _ids(raw.get("needed_by")),
                    "from": "model" if raw.get("from") == "model" else "typed"})
    if not own and out and not any(t["area"] for t in out):
        general = new_area("General", "عام")                # a new subject needs at least one area
        for topic in out:
            topic["area"] = general
    fallback = next(iter(own), "") or next(iter(new_areas), "")
    by_key = {t["key"]: t for t in out}
    installed = {cid: c for cid, c in pack.concepts.items() if pack.strand_subject.get(c.strand) == subject["id"]}
    for topic in out:
        topic["area"] = topic["area"] or fallback
        at = (topic["grade"], topic["term"])
        needs = []
        for ref in dict.fromkeys(rename.get(r, r) for r in topic["needs"]):
            if ref in by_key and ref != topic["key"] and (by_key[ref]["grade"], by_key[ref]["term"]) <= at or ref in installed and installed[ref].grade <= topic["grade"]:
                needs.append(ref)
        topic["needs"] = needs[:MAX_LINKS]
        topic["needed_by"] = [ref for ref in dict.fromkeys(topic["needed_by"])
                              if ref in installed and installed[ref].grade >= topic["grade"]][:6]
    return {"topics": out, "areas": [a for a in new_areas.values() if any(t["area"] == a["key"] for t in out)]}


def build_addition(pack: Pack, row: dict[str, Any]) -> dict[str, Any]:
    """The draft as pack data: real ids for the subject, the new areas and the topics, and the links."""
    draft = row["data"]
    short = row["id"].split("_")[-1][:6]
    subject = dict(draft["subject"])
    if subject.get("new"):
        subject["id"] = f"add-{short}-subject"
    area_ids = {a["key"]: f"add-{short}-a{i + 1}" for i, a in enumerate(draft["areas"])}
    ids = {t["key"]: f"add-{short}-{i + 1:02d}" for i, t in enumerate(draft["topics"])}
    concepts, links = [], {}
    for topic in draft["topics"]:
        label = {"en": topic["en"], **({"ar": topic["ar"]} if topic.get("ar") else {})}
        concepts.append({"id": ids[topic["key"]], "label": label, "strand": area_ids.get(topic["area"], topic["area"]),
                         "grade": topic["grade"], "term": topic["term"],
                         "requires": [ids.get(ref, ref) for ref in topic["needs"]], "skills": list(topic["skills"]),
                         "source": f"added by the school ({row['id']})"})
        for later in topic["needed_by"]:
            links.setdefault(later, []).append(ids[topic["key"]])
    return {"subject": {"id": subject["id"], "label": subject["label"]},
            "strands": [{"id": area_ids[a["key"]], "label": {"en": a["en"], **({"ar": a["ar"]} if a.get("ar") else {})}}
                        for a in draft["areas"]],
            "concepts": concepts,
            "links": [{"concept": later, "requires": needed} for later, needed in links.items()]}


def check(pack: Pack, row: dict[str, Any], db_path=None) -> dict[str, Any]:
    """Would this draft fit the curriculum as it stands? Returns the addition, or raises in plain words."""
    draft = row["data"]
    if not draft["topics"]:
        raise ValueError("There is no topic to add yet.")
    if any(not t["area"] for t in draft["topics"]):
        raise ValueError("Choose an area for every topic.")
    addition = build_addition(pack, row)
    settings = get_settings()
    data = read_pack_data(Path(settings.packs_dir).resolve() / pack.id / "pack.yaml")
    for earlier in _additions(pack.id, Path(db_path or settings.db_path)):
        trial = copy.deepcopy(data)
        try:
            apply_addition(trial, earlier)
            build_pack(trial)
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
        data = trial
    try:
        apply_addition(data, addition)
        build_pack(data)
    except (ValueError, KeyError, TypeError) as exc:
        if "cycle" in str(exc):
            raise ValueError("Two topics need each other, directly or through other topics. Remove one of the "
                             "links and try again.") from exc
        raise ValueError(f"This cannot be added as it is: {exc}") from exc
    return addition


# ------------------------------------------------------------------ drafts and decisions

def _view(pack: Pack, row: dict[str, Any], names: dict[str, str] | None = None) -> dict[str, Any]:
    data = db.jload(row["data"], {}) if isinstance(row["data"], str) else row["data"]
    names = names or {}
    out = {"id": row["id"], "title": row["title"], "status": row["status"], "read_by": row["read_by"],
           "created_at": row["created_at"], "created_by": names.get(row["created_by"], row["created_by"]),
           "decided_at": row["decided_at"], "decided_by": names.get(row["decided_by"], row["decided_by"]),
           "subject": data.get("subject"), "grade": data.get("grade"), "term": data.get("term"),
           "topics": data.get("topics") or [], "areas": data.get("areas") or [], "note": data.get("note") or ""}
    out["links"] = sum(len(t["needs"]) + len(t["needed_by"]) for t in out["topics"])
    return out


def _names(conn) -> dict[str, str]:
    return {r["id"]: r["name"] for r in db.rows(conn, "SELECT id, name FROM teachers")}


def _row(conn, addition_id: str, status: str | None = None) -> dict[str, Any]:
    row = db.one(conn, "SELECT * FROM curriculum_additions WHERE id = ?", (addition_id,))
    if row is None:
        raise ValueError("That addition was not found.")
    if status and row["status"] != status:
        raise ValueError({"draft": "That draft has already been decided.",
                          "approved": "Only an approved addition can be withdrawn."}[status])
    row["data"] = db.jload(row["data"], {})
    return row


def menus(pack: Pack, subject_id: str | None = None) -> dict[str, Any]:
    """What the review page chooses from: the subject's own areas and topics, and the thinking skills."""
    lang_label = lambda label: {"en": label.get("en", ""), "ar": label.get("ar", "")}
    return {
        "areas": [{"id": sid, **lang_label(label)} for sid, label in pack.strands.items()
                  if pack.strand_subject.get(sid) == subject_id],
        "topics": [{"id": c.id, **lang_label(c.label), "grade": c.grade, "term": c.term}
                   for c in sorted(pack.concepts.values(), key=lambda c: (c.grade, c.term or 0, c.id))
                   if pack.strand_subject.get(c.strand) == subject_id],
        "skills": [{"id": sid, **lang_label(label)} for sid, label in pack.skills.items()
                   if pack.skill_kinds.get(sid) == "thinking"],
    }


def listing(pack: Pack, db_path=None) -> dict[str, Any]:
    """Every draft and every decided addition, newest first, without the discarded ones."""
    with db.connect(db_path) as conn:
        rows = db.rows(conn, "SELECT * FROM curriculum_additions WHERE pack_id = ? AND status != 'discarded' "
                             "ORDER BY created_at DESC, id", (pack.id,))
        names = _names(conn)
    live = {a["id"] for a in pack.additions}
    found = []
    for row in rows:
        view = _view(pack, row, names)
        view["in_use"] = row["id"] in live
        found.append({k: v for k, v in view.items() if k not in ("topics", "areas")} | {"topic_count": len(view["topics"])})
    return {"additions": found, "grades": list(GRADES), "terms": pack.terms,
            "subjects": [{"id": sid, "label": pack.label(sid)} for sid in pack.subjects]}


def create_draft(pack: Pack, *, title: str = "", subject_id: str = "", new_subject: str = "", grade: int, term: int = 0,
                 text: str = "", image: bytes | None = None, use_model: bool = False, model: str | None = None,
                 actor: str, db_path=None) -> dict[str, Any]:
    """Make a draft from typed lines, or from a page read by the model. Nothing is added to the curriculum."""
    if not GRADES[0] <= int(grade) <= GRADES[1]:
        raise ValueError(f"Choose a grade from {GRADES[0]} to {GRADES[1]}.")
    if not 0 <= int(term) <= pack.terms:
        raise ValueError(f"This curriculum has {pack.terms} terms in a year.")
    subject = _subject(pack, subject_id, new_subject)
    if image is not None:
        if kind_of(image) is None:
            raise ValueError("That picture is not one Athar can read. Use a JPEG or PNG picture.")
        if len(image) > MAX_FILE:
            raise ValueError("That picture is too large (the limit is 8 MB).")
        if not use_model:
            raise ValueError("A picture can only be read by the model. Turn that on, or type the topics in.")
    elif not str(text or "").strip():
        raise ValueError("Paste the list of topics, or choose a file or a picture of the contents page.")
    draft = {"subject": subject, "grade": int(grade), "term": int(term) or 1, "topics": [], "areas": [], "note": ""}
    started = time.perf_counter()
    if use_model:
        raw = read_topics(pack, subject, int(grade), text=text, image=image, model=model)
        for entry in raw:
            entry["from"] = "model"
            if int(term):
                entry["term"] = int(term)
        draft.update(clean(pack, draft, raw))
        drop_blanket_skills(draft["topics"])
        try:
            suggest_links(pack, subject, int(grade), draft["topics"], model=model)
        except ValueError:
            draft["note"] = "The model listed the topics but could not suggest links. Add them yourself below."
        draft.update(clean(pack, draft, draft["topics"], draft["areas"]))
        for topic in draft["topics"]:
            topic["from"] = "model"
    else:
        raw = parse_lines(text, pack.terms)
        if int(term):
            for entry in raw:
                entry["term"] = entry["term"] or int(term)
        draft.update(clean(pack, draft, raw))
    if not draft["topics"]:
        raise ValueError("No topic was found in that. Type the topics in, one on each line.")
    read_by = f"model:{model or get_settings().llm_model}" if use_model else "typed"
    title = _clip(title, 80) or (f"{subject['label']['ar']}، الصف {int(grade)}"
                                 if current_lang.get() == "ar" and subject["label"].get("ar")
                                 else f"{subject['label']['en']}, grade {int(grade)}")
    row = {"id": db.new_id("cur"), "pack_id": pack.id, "title": title, "status": "draft", "data": draft,
           "read_by": read_by, "created_by": actor, "created_at": db.now_iso(), "decided_by": None, "decided_at": None}
    with db.connect(db_path) as conn:
        conn.execute("INSERT INTO curriculum_additions (id, pack_id, title, status, data, read_by, created_by, created_at) "
                     "VALUES (?,?,?,?,?,?,?,?)", (row["id"], pack.id, title, "draft", db.jdump(draft), read_by, actor,
                                                 row["created_at"]))
        # The log holds what was asked and how much came back, never the page itself.
        audit.write_row(conn, "curriculum_draft", {"subject": subject["label"]["en"], "grade": int(grade), "read_by": read_by,
                                                   "picture": image is not None, "characters": len(text or "")},
                        {"id": row["id"], "topics": len(draft["topics"]),
                         "links": sum(len(t["needs"]) + len(t["needed_by"]) for t in draft["topics"])},
                        True, int((time.perf_counter() - started) * 1000), actor=f"teacher:{actor}")
        names = _names(conn)
    return {**_view(pack, row, names), "menus": menus(pack, subject["id"] if not subject["new"] else None)}


def get(pack: Pack, addition_id: str, db_path=None) -> dict[str, Any]:
    with db.connect(db_path) as conn:
        row = _row(conn, addition_id)
        names = _names(conn)
    subject = row["data"].get("subject") or {}
    return {**_view(pack, row, names), "menus": menus(pack, None if subject.get("new") else subject.get("id"))}


def save_draft(pack: Pack, addition_id: str, *, title: str = "", topics: list[Any], areas: list[Any] | None = None,
               actor: str, db_path=None) -> dict[str, Any]:
    """Store the teacher's edits to a draft. Everything sent is checked again in plain code."""
    with db.connect(db_path) as conn:
        row = _row(conn, addition_id, "draft")
        draft = row["data"]
        draft.update(clean(pack, draft, topics, areas))
        row["title"] = _clip(title, 80) or row["title"]
        conn.execute("UPDATE curriculum_additions SET title = ?, data = ? WHERE id = ?",
                     (row["title"], db.jdump(draft), addition_id))
        names = _names(conn)
    subject = draft["subject"]
    return {**_view(pack, row, names), "menus": menus(pack, None if subject.get("new") else subject.get("id"))}


def approve(pack: Pack, addition_id: str, *, teacher_id: str, checked: bool, db_path=None) -> dict[str, Any]:
    """A named teacher approves a draft, and from then on its topics are part of the curriculum here."""
    if not checked:
        raise ValueError("Tick the box to say you checked every topic and every link.")
    with db.connect(db_path) as conn:
        row = _row(conn, addition_id, "draft")
        teacher = db.one(conn, "SELECT id, name FROM teachers WHERE id = ?", (teacher_id,))
        if teacher is None:
            raise ValueError("Choose your name first, so the record shows who approved this.")
        addition = check(pack, row, db_path)
        now = db.now_iso()
        conn.execute("UPDATE curriculum_additions SET status = 'approved', approved = ?, decided_by = ?, decided_at = ? "
                     "WHERE id = ?", (db.jdump(addition), teacher_id, now, addition_id))
        audit.write_row(conn, "curriculum_approve", {"id": addition_id, "title": row["title"]},
                        {"topics": len(addition["concepts"]), "new_areas": len(addition["strands"]),
                         "links": sum(len(c["requires"]) for c in addition["concepts"]) + sum(
                             len(link["requires"]) for link in addition["links"])},
                        True, 0, actor=f"teacher:{teacher_id}")
    return {"id": addition_id, "status": "approved", "topics": len(addition["concepts"]), "approved_by": teacher["name"]}


def discard(addition_id: str, *, actor: str, db_path=None) -> dict[str, Any]:
    with db.connect(db_path) as conn:
        row = _row(conn, addition_id, "draft")
        conn.execute("UPDATE curriculum_additions SET status = 'discarded', decided_by = ?, decided_at = ? WHERE id = ?",
                     (actor, db.now_iso(), addition_id))
        audit.write_row(conn, "curriculum_discard", {"id": addition_id, "title": row["title"]}, {"discarded": True},
                        True, 0, actor=f"teacher:{actor}")
    return {"id": addition_id, "status": "discarded"}


def withdraw(addition_id: str, *, actor: str, db_path=None) -> dict[str, Any]:
    """Take an approved addition out again. Refused once any record or lesson points at one of its topics,
    because those records would then point at nothing."""
    with db.connect(db_path) as conn:
        row = _row(conn, addition_id, "approved")
        ids = [c["id"] for c in (db.jload(row["approved"], {}) or {}).get("concepts", [])]
        used = 0
        for start in range(0, len(ids), 200):
            part = ids[start:start + 200]
            marks = ",".join("?" * len(part))
            used += db.one(conn, f"SELECT COUNT(*) AS n FROM evidence WHERE concept_id IN ({marks})", tuple(part))["n"]
            used += db.one(conn, f"SELECT COUNT(*) AS n FROM teaching_units WHERE concept_id IN ({marks})", tuple(part))["n"]
        if used:
            raise ValueError(f"This cannot be withdrawn: {used} records already use its topics.")
        conn.execute("UPDATE curriculum_additions SET status = 'withdrawn', decided_by = ?, decided_at = ? WHERE id = ?",
                     (actor, db.now_iso(), addition_id))
        audit.write_row(conn, "curriculum_withdraw", {"id": addition_id, "title": row["title"]}, {"topics": len(ids)},
                        True, 0, actor=f"teacher:{actor}")
    return {"id": addition_id, "status": "withdrawn"}

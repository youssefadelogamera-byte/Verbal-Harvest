"""Reading a photo of a marked paper.

A parent takes a photo of a test with the marks written on it. The model on this computer looks at the photo
and lists each part that has its own mark, and which topic it seems to be about. Nothing is saved here: the
lines go back to the page, the parent checks each one against the paper, and only then saves them.

Rules this module keeps:

- The photo goes only to a model on this computer. A photo of a child's paper usually shows the child's
  name, and no name may leave the machine. If the model is somewhere else, reading is refused.
- The photo is not kept. It is read in memory and dropped.
- The model only reads. Plain code checks what it returned: a topic it names must be in the list it was
  given, a mark must fit inside its maximum, and the lines are compared with the total written on the paper.
"""

from __future__ import annotations

import base64
import json
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from . import audit
from .config import get_settings
from .curriculum import Pack

MAX_BYTES = 12 * 1024 * 1024
TYPES = {"image/jpeg": "jpeg", "image/png": "png", "image/webp": "webp"}
MAX_LINES = 30
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}

PROMPT = """This is a photo of a marked school paper. Find each question or part that has its own mark written on it.

Reply with JSON only, in this shape:
{"title": "the name of the test as printed, or an empty string",
 "lines": [{"about": "the heading of that question, copied letter for letter from the paper, in the paper's own language",
            "topic_id": "the id of the best matching topic from TOPICS, or null if none fits",
            "mark": the mark given, as a number,
            "out_of": the maximum for that part, as a number}],
 "total": {"mark": number, "out_of": number} or null if no total is written}

Rules:
- Copy each mark exactly as it is written. If you cannot read a mark, leave that line out. Never guess a mark.
- A mark belongs to the question it is written beside. A question with no mark beside it gets no line.
- Do not translate and do not describe: "about" is the printed heading, copied. If the paper is in Arabic, write Arabic.
- Do not include the total as a line.
- Choose topic_id only from TOPICS. If you are not sure, use null.
- Do not write the pupil's name, the teacher's name or the school's name anywhere in your reply.

TOPICS (id: name):
"""


def is_local(url: str) -> bool:
    """True when a model address is on this computer."""
    return (urlparse(url).hostname or "").lower() in _LOCAL_HOSTS


def kind_of(data: bytes) -> str | None:
    """The image type, read from the file's first bytes, not from what the browser says."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def topic_menu(pack: Pack, grade: int, subject: str | None) -> list[dict[str, Any]]:
    """Topics a paper of this grade and subject could be about: the grade itself and the two before, since
    a test often goes back over earlier work."""
    found = [c for c in pack.concepts.values() if grade - 2 <= c.grade <= grade
             and (not subject or pack.strand_subject.get(c.strand) == subject)]
    found.sort(key=lambda c: (-c.grade, c.term or 0, c.id))
    return [{"id": c.id, "label": pack.label(c.id), "labels": sorted(set(c.label.values()))} for c in found]


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")).replace(",", ".").strip())
    except ValueError:
        return None


def parse_reply(text: str) -> dict[str, Any]:
    """The model's reply as data. Models often wrap JSON in a code fence or add a sentence around it."""
    text = text.split("</think>")[-1]
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("The model did not return anything Athar could read. Try a clearer photo.")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError("The model did not return anything Athar could read. Try a clearer photo.") from exc
    return data          # the pattern above starts at a brace, so this is always an object


def _plain(text: str) -> str:
    """Text reduced for comparing: no marks on letters, one form of alef and of yaa, single spaces."""
    text = re.sub(r"[\u064b-\u0652\u0640]", "", str(text or "").lower())
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        text = text.replace(a, b)
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


def topic_in_words(about: str, menu: list[dict[str, Any]]) -> str | None:
    """The topic whose own name is printed in the question's heading, if exactly one is. Papers often print
    the topic's name, and matching the words is surer than a model's guess. The longest name wins."""
    heading = f" {_plain(about)} "
    found = [(len(_plain(label)), t["id"]) for t in menu for label in t["labels"]
             if len(_plain(label)) >= 5 and f" {_plain(label)} " in heading]
    if not found:
        return None
    longest = max(n for n, _ in found)
    best = {topic for n, topic in found if n == longest}
    return best.pop() if len(best) == 1 else None


def check(data: dict[str, Any], menu: list[dict[str, Any]]) -> dict[str, Any]:
    """Turn what the model returned into lines a parent can check. Plain code: anything that does not hold
    up is dropped or flagged, never repaired by guessing."""
    known = {t["id"]: t["label"] for t in menu}
    lines, dropped = [], 0
    for raw in (data.get("lines") or [])[:MAX_LINES]:
        if not isinstance(raw, dict):
            dropped += 1
            continue
        mark, out_of = _number(raw.get("mark")), _number(raw.get("out_of"))
        if mark is None or out_of is None or out_of <= 0 or not 0 <= mark <= out_of:
            dropped += 1                     # an unreadable or impossible mark is left out, not corrected
            continue
        about = " ".join(str(raw.get("about") or "").split())[:160]
        printed = topic_in_words(about, menu)                      # the name printed on the paper beats a guess
        topic = printed or (raw.get("topic_id") if raw.get("topic_id") in known else None)
        lines.append({"about": about, "topic_id": topic, "topic": known.get(topic), "mark": mark, "out_of": out_of,
                      "topic_from": "paper" if printed else "model" if topic else None})
    total = data.get("total") if isinstance(data.get("total"), dict) else None
    written = None
    if total:
        mark, out_of = _number(total.get("mark")), _number(total.get("out_of"))
        if mark is not None and out_of is not None and out_of > 0:
            written = {"mark": mark, "out_of": out_of}
    # A model sometimes lists the total as one more line. A line that equals the sum of all the others, or the
    # total written on the paper, is the total: it is taken out.
    if len(lines) >= 3:
        for i, line in enumerate(lines):
            rest = [x for j, x in enumerate(lines) if j != i]
            same = lambda a, b: abs(a - b) < 0.01
            is_sum = same(line["mark"], sum(x["mark"] for x in rest)) and same(line["out_of"], sum(x["out_of"] for x in rest))
            is_written = written and same(line["mark"], written["mark"]) and same(line["out_of"], written["out_of"])
            if is_sum or (is_written and line["out_of"] > max(x["out_of"] for x in rest)):
                written = written or {"mark": line["mark"], "out_of": line["out_of"]}
                lines = rest
                break
    summed = {"mark": sum(x["mark"] for x in lines), "out_of": sum(x["out_of"] for x in lines)}
    return {"title": " ".join(str(data.get("title") or "").split())[:80], "lines": lines, "dropped": dropped,
            "total_on_paper": written, "total_of_lines": summed,
            "totals_match": None if written is None else (abs(written["mark"] - summed["mark"]) < 0.01
                                                          and abs(written["out_of"] - summed["out_of"]) < 0.01),
            "without_topic": sum(1 for x in lines if x["topic_id"] is None)}


def read_paper(image: bytes, pack: Pack, grade: int, subject: str | None, *, model: str | None = None,
               actor: str = "guardian", db_path=None) -> dict[str, Any]:
    """Ask the model on this computer what is on the paper. Returns lines to check; saves nothing."""
    settings = get_settings()
    if not image:
        raise ValueError("Choose a photo first.")
    if len(image) > MAX_BYTES:
        raise ValueError("That photo is too large (the limit is 12 MB). Take it again at a lower quality.")
    kind = kind_of(image)
    if kind is None:
        raise ValueError("That file is not a photo Athar can read. Use a JPEG or PNG picture.")
    if not is_local(settings.llm_base_url):
        raise ValueError("A photo of a paper usually shows the child's name, so Athar reads photos only with a model "
                         "on this computer. The model set up here is on the internet. Type the result in instead.")
    menu = topic_menu(pack, grade, subject)
    if not menu:
        raise ValueError("There are no topics for that grade and subject.")
    prompt = PROMPT + "\n".join(f"{t['id']}: {' / '.join(t['labels'])}" for t in menu)
    body = {"model": model or settings.llm_model, "temperature": 0, "max_tokens": 1500, "reasoning_effort": "none",
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{kind};base64," + base64.b64encode(image).decode("ascii")}}]}]}
    started = time.perf_counter()
    try:
        reply = httpx.post(f"{settings.llm_base_url.rstrip('/')}/chat/completions", json=body, timeout=300,
                           headers={"Authorization": f"Bearer {settings.llm_api_key}"})
    except httpx.HTTPError as exc:
        raise ValueError("The model on this computer did not answer. Start it, then try again.") from exc
    if reply.status_code >= 400:
        raise ValueError("The model on this computer could not read the photo. It may not be a model that can see "
                         "pictures. Type the result in instead.")
    try:
        text = reply.json()["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ValueError("The model did not return anything Athar could read. Try a clearer photo.") from exc
    out = check(parse_reply(text), menu)
    out["seconds"] = round(time.perf_counter() - started, 1)
    # The log holds that a photo was read and how many lines came back, never the photo or its words.
    audit.log_call("read_paper_photo", {"bytes": len(image), "type": kind, "grade": grade, "subject": subject},
                   {"lines": len(out["lines"]), "dropped": out["dropped"], "totals_match": out["totals_match"]},
                   True, int(out["seconds"] * 1000), actor=actor, db_path=db_path)
    return out

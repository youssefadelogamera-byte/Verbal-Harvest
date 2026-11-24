"""Reading a photo of a marked paper: local model only, nothing saved, and plain code checks the result."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from athar import db, photo
from athar.curriculum import load_pack

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
REPLY = {"title": "November test", "total": {"mark": 12, "out_of": 20}, "lines": [
    {"about": "Q1 ratios", "topic_id": "ratios", "mark": 2, "out_of": 5},
    {"about": "Q2 fractions", "topic_id": "fractions", "mark": "٤", "out_of": 5},          # Arabic digit
    {"about": "Q3 something else", "topic_id": "not-in-the-list", "mark": 5, "out_of": 5},
    {"about": "Q4 division", "topic_id": "division", "mark": 1, "out_of": 5},
    {"about": "Q5 smudged", "topic_id": "ratios", "mark": 9, "out_of": 5},                 # impossible: left out
    {"about": "Q6 unreadable", "topic_id": "ratios", "mark": None, "out_of": 5}]}


class _Reply:
    def __init__(self, body, status=200):
        self._body, self.status_code = body, status

    def json(self):
        return self._body


def _answer(text: str):
    return _Reply({"choices": [{"message": {"content": text}}]})


@pytest.fixture()
def menu(db_path):
    return photo.topic_menu(load_pack("mini-maths"), 5, None)


def test_the_type_is_read_from_the_file_and_only_this_computer_counts_as_local():
    assert photo.kind_of(PNG) == "image/png" and photo.kind_of(JPEG) == "image/jpeg"
    assert photo.kind_of(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert photo.kind_of(b"%PDF-1.7 not a picture") is None and photo.kind_of(b"") is None
    assert photo.is_local("http://localhost:1234/v1") and photo.is_local("http://127.0.0.1:11812/v1")
    assert not photo.is_local("https://api.openai.com/v1") and not photo.is_local("http://192.168.1.20:1234/v1")
    assert not photo.is_local("https://localhost.example.com/v1")


def test_a_reply_wrapped_in_a_code_fence_is_still_read():
    fenced = "Here you go:\n```json\n" + json.dumps(REPLY) + "\n```"
    assert photo.parse_reply(fenced)["title"] == "November test"
    assert photo.parse_reply("<think>hmm</think>" + json.dumps(REPLY))["total"]["mark"] == 12
    for bad in ("I cannot see the image.", "{not json}"):
        with pytest.raises(ValueError, match="clearer photo"):
            photo.parse_reply(bad)


def test_plain_code_checks_what_the_model_said(menu):
    out = photo.check(REPLY, menu)
    assert [(x["topic_id"], x["mark"], x["out_of"]) for x in out["lines"]] == [
        ("ratios", 2.0, 5.0), ("fractions", 4.0, 5.0), (None, 5.0, 5.0), ("division", 1.0, 5.0)]
    assert out["dropped"] == 2                      # the impossible mark and the unreadable one are left out, not guessed
    assert out["without_topic"] == 1                # a topic that is not in the list is never accepted
    assert out["total_on_paper"] == {"mark": 12.0, "out_of": 20.0} and out["totals_match"] is True
    off = photo.check({**REPLY, "total": {"mark": 15, "out_of": 20}}, menu)
    assert off["totals_match"] is False
    assert photo.check({"lines": []}, menu)["totals_match"] is None
    assert photo.check({"lines": "nonsense", "total": 7}, menu)["lines"] == []


def test_a_photo_never_goes_to_a_model_on_the_internet(db_path, monkeypatch):
    sent = []
    monkeypatch.setattr(photo.httpx, "post", lambda *a, **k: sent.append(a) or _answer(json.dumps(REPLY)))
    pack = load_pack("mini-maths")
    monkeypatch.setenv("ATHAR_LLM_BASE_URL", "https://api.example.com/v1")
    with pytest.raises(ValueError, match="only with a model on this computer"):
        photo.read_paper(PNG, pack, 4, None)
    monkeypatch.setenv("ATHAR_LLM_BASE_URL", "http://localhost:1234/v1")
    with pytest.raises(ValueError, match="not a photo"):
        photo.read_paper(b"just some text, not a picture", pack, 4, None)
    with pytest.raises(ValueError, match="too large"):
        photo.read_paper(PNG + b"\x00" * photo.MAX_BYTES, pack, 4, None)
    assert sent == []                               # none of the refusals reached a model


def test_reading_saves_nothing_and_the_log_holds_no_picture(db_path, monkeypatch):
    seen = {}

    def fake_post(url, json=None, **kwargs):
        seen["url"], seen["body"] = url, json
        return _answer("```json\n" + __import__("json").dumps(REPLY) + "\n```")

    monkeypatch.setenv("ATHAR_LLM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setattr(photo.httpx, "post", fake_post)
    with db.connect() as conn:
        before = db.one(conn, "SELECT COUNT(*) AS n FROM evidence")["n"]
    out = photo.read_paper(JPEG, load_pack("mini-maths"), 5, None, actor="guardian:test")
    assert len(out["lines"]) == 4 and out["totals_match"] is True
    assert seen["url"] == "http://localhost:1234/v1/chat/completions"
    parts = seen["body"]["messages"][0]["content"]
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,") and "ratios" in parts[0]["text"]
    assert "name" in parts[0]["text"].lower()        # the model is told to leave names out
    with db.connect() as conn:
        assert db.one(conn, "SELECT COUNT(*) AS n FROM evidence")["n"] == before
        row = db.one(conn, "SELECT actor, input, output FROM audit_log WHERE tool = 'read_paper_photo'")
    assert row["actor"] == "guardian:test" and "base64" not in row["input"] + row["output"]
    assert "November" not in row["input"] + row["output"]


def test_a_model_that_cannot_see_or_is_off_gives_a_plain_message(db_path, monkeypatch):
    monkeypatch.setenv("ATHAR_LLM_BASE_URL", "http://localhost:1234/v1")
    pack = load_pack("mini-maths")
    monkeypatch.setattr(photo.httpx, "post", lambda *a, **k: _Reply({"error": "no vision"}, status=400))
    with pytest.raises(ValueError, match="could not read the photo"):
        photo.read_paper(PNG, pack, 4, None)

    def off(*a, **k):
        raise photo.httpx.ConnectError("refused")
    monkeypatch.setattr(photo.httpx, "post", off)
    with pytest.raises(ValueError, match="did not answer"):
        photo.read_paper(PNG, pack, 4, None)


def test_the_page_route_is_for_the_family_and_its_own_children(db_path, monkeypatch):
    from athar.web.app import app
    client = TestClient(app)
    monkeypatch.setenv("ATHAR_LLM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setattr(photo.httpx, "post", lambda *a, **k: _answer(json.dumps(REPLY)))
    send = lambda learner: client.post(f"/api/family/children/{learner}/photo", data={"grade": "5", "subject": ""},
                                       files={"file": ("paper.png", PNG, "image/png")})
    assert send("lrn_a").status_code == 400                     # nobody has chosen the family side yet
    client.post("/api/mode", json={"mode": "family", "name": "Mona Farouk"})
    child = client.post("/api/family/children", json={"name": "Salma", "grade": 5}).json()["learner_id"]
    assert send("lrn_a").status_code == 400                     # not this family's child
    got = send(child)
    assert got.status_code == 200 and len(got.json()["lines"]) == 4 and got.json()["dropped"] == 2
    with db.connect() as conn:
        assert db.one(conn, "SELECT COUNT(*) AS n FROM evidence WHERE learner_id = ?", (child,))["n"] == 0


def test_a_topic_named_on_the_paper_beats_the_models_guess_and_a_total_is_not_a_line():
    pack = load_pack("egypt-school")
    menu = photo.topic_menu(pack, 6, "maths")
    said = {"lines": [
        {"about": "السؤال الأول: الأعداد النسبية", "topic_id": "g6-number-line", "mark": 2, "out_of": 5},     # the model guessed wrong
        {"about": "السؤال الثاني: الأعداد الصحيحة وخط الأعداد", "topic_id": "g6-number-line", "mark": 4, "out_of": 5},
        {"about": "something with no topic name in it", "topic_id": "g6-absolute-value", "mark": 5, "out_of": 5},
        {"about": "المجموع", "topic_id": None, "mark": 11, "out_of": 15}]}                                     # the total, listed as a line
    out = photo.check(said, menu)
    assert [(x["topic_id"], x["topic_from"]) for x in out["lines"]] == [
        ("g6-rational-numbers", "paper"), ("g6-number-line", "paper"), ("g6-absolute-value", "model")]
    assert out["total_on_paper"] == {"mark": 11.0, "out_of": 15.0} and out["totals_match"] is True
    assert photo.topic_in_words("Q4: The water cycle", photo.topic_menu(pack, 5, "science")) == "sci-g5-water-cycle"
    assert photo.topic_in_words("a heading that names nothing", menu) is None

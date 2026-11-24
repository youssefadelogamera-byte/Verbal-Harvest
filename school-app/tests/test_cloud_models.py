"""Optional cloud models. Every key here is a made-up string: no test talks to a provider."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from athar import synth
from athar.agent import llm

FAKE = "test-only-not-a-real-key-" + "x" * 24


@pytest.fixture(autouse=True)
def no_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    llm._session_keys.clear()
    yield
    llm._session_keys.clear()


@pytest.fixture()
def world(tmp_path, monkeypatch):
    path = tmp_path / "athar.db"
    monkeypatch.setenv("ATHAR_DB", str(path))
    synth.generate(db_path=path, n_learners=6, out_dir=tmp_path / "out")
    monkeypatch.setattr(llm, "list_models", lambda provider="local", timeout=3.0: {
        "local": ["qwen3.5-9b"], "openai": ["gpt-test"], "anthropic": ["claude-test"]}[provider])
    from athar.web.app import app
    return TestClient(app), path


def test_a_key_is_kept_in_memory_and_never_comes_back(world):
    client, path = world
    before = {p["id"]: p for p in client.get("/api/models").json()["providers"]}
    assert [before[p]["ready"] for p in ("local", "openai", "anthropic")] == [True, False, False]
    assert before["openai"]["models"] == [] and before["openai"]["key_env"] == "OPENAI_API_KEY"

    saved = client.post("/api/providers/openai/key", json={"key": FAKE})
    assert saved.status_code == 200 and FAKE not in saved.text and saved.json()["key_source"] == "typed in this session"
    listing = client.get("/api/models")
    after = {p["id"]: p for p in listing.json()["providers"]}
    assert after["openai"]["ready"] and after["openai"]["models"] == ["gpt-test"] and FAKE not in listing.text

    # Not in the database, the audit log, or any file next to it.
    with sqlite3.connect(path) as conn:
        dump = "\n".join(conn.iterdump())
        logged = conn.execute("SELECT input, output FROM audit_log WHERE tool = 'set_model_key'").fetchall()
    assert FAKE not in dump and logged == [('{"provider": "openai"}', '{"kept": "in memory until the app stops"}')]
    assert not any(FAKE in f.read_text(encoding="utf-8", errors="ignore") for f in path.parent.rglob("*") if f.is_file() and f.suffix != ".db")

    assert client.delete("/api/providers/openai/key").json()["ready"] is False
    assert client.get("/api/models").json()["providers"][1]["ready"] is False


def test_key_rules(world):
    client, _ = world
    assert client.post("/api/providers/openai/key", json={"key": "short"}).status_code == 400
    assert client.post("/api/providers/openai/key", json={"key": "has a space " + "x" * 30}).status_code == 400
    assert client.post("/api/providers/local/key", json={"key": FAKE}).status_code == 400
    assert client.post("/api/providers/nobody/key", json={"key": FAKE}).status_code == 400
    assert llm.key_source("anthropic") is None


def test_a_key_from_the_environment_is_used_and_named_without_being_shown(world, monkeypatch):
    client, _ = world
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE)
    listing = client.get("/api/models")
    claude = next(p for p in listing.json()["providers"] if p["id"] == "anthropic")
    assert claude["ready"] and claude["key_source"] == "the ANTHROPIC_API_KEY environment variable"
    assert claude["models"] == ["claude-test"] and FAKE not in listing.text


def test_a_cloud_run_needs_a_key_and_a_model(world, monkeypatch):
    client, _ = world
    from athar.web import app as web
    started = []

    class Runner:
        def start(self, task):
            started.append(task)
            return {"run_id": "run_x", "status": "running"}
    monkeypatch.setattr(web, "_runner", lambda: Runner())
    lid = client.get("/api/learners").json()["learners"][0]["learner_id"]
    refused = client.post("/api/runs", json={"learner_id": lid, "provider": "openai", "model": "gpt-test"})
    assert refused.status_code == 400 and "No key" in refused.json()["error"] and not started
    assert client.post("/api/runs", json={"learner_id": lid, "provider": "elsewhere", "model": "m"}).status_code == 400
    llm.set_key("openai", FAKE)
    assert client.post("/api/runs", json={"learner_id": lid, "provider": "openai", "model": "gpt-test"}).status_code == 200
    assert started[0]["which_model"] == "openai" and started[0]["model"] == "gpt-test" and FAKE not in str(started)
    assert client.post("/api/runs", json={"learner_id": lid, "provider": "local"}).status_code == 200
    assert "which_model" not in started[1]


def test_run_record_refuses_an_unknown_provider_or_a_cloud_run_without_a_model(world):
    from athar.agent import runner
    client, _ = world
    lid = client.get("/api/learners").json()["learners"][0]["learner_id"]
    with pytest.raises(ValueError, match="Unknown model provider"):
        runner._new_record({"learner_id": lid, "which_model": "elsewhere"})
    with pytest.raises(ValueError, match="Choose a model"):
        runner._new_record({"learner_id": lid, "which_model": "anthropic"})


def test_chat_model_builds_the_right_client_for_each_provider():
    with pytest.raises(RuntimeError, match="No key for OpenAI"):
        llm.chat_model("openai", "gpt-test")
    llm.set_key("openai", FAKE)
    llm.set_key("anthropic", FAKE)
    assert type(llm.chat_model("openai", "gpt-test")).__name__ == "ChatOpenAI"
    assert type(llm.chat_model("anthropic", "claude-test")).__name__ == "ChatAnthropic"
    assert type(llm.chat_model("local")).__name__ == "ChatOpenAI"          # the local endpoint speaks the same protocol
    with pytest.raises(RuntimeError, match="Choose a model"):
        llm.chat_model("anthropic", None)
    with pytest.raises(RuntimeError, match="Unknown model provider"):
        llm.chat_model("elsewhere", "m")


def test_structured_output_and_reply_text_work_for_both_kinds_of_model():
    calls = []

    class ChatAnthropic:
        def with_structured_output(self, schema, **kwargs):
            calls.append(("claude", kwargs))

    class Other:
        def with_structured_output(self, schema, **kwargs):
            calls.append(("other", kwargs))
    llm.structured(ChatAnthropic(), dict)
    llm.structured(Other(), dict)
    assert calls == [("claude", {"include_raw": True}), ("other", {"method": "json_schema", "include_raw": True})]

    class Reply:
        def __init__(self, content):
            self.content = content
    assert llm.text_of(Reply("plain")) == "plain" and llm.text_of(Reply(None)) == ""
    assert llm.text_of(Reply([{"type": "text", "text": "two "}, {"type": "text", "text": "parts"}, {"type": "tool_use"}])) == "two parts"


def test_a_key_is_removed_from_any_error_text():
    llm.set_key("openai", FAKE)
    assert llm.scrub(f"AuthenticationError: bad key {FAKE} given") == "AuthenticationError: bad key [key hidden] given"
    assert llm.scrub("nothing secret") == "nothing secret"


def test_openai_listing_keeps_chat_models_only(monkeypatch):
    import httpx
    seen = {}

    class Reply:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": "gpt-test"}, {"id": "gpt-test-audio-preview"}, {"id": "text-embedding-3"}, {"id": "o3-test"},
                             {"id": "dall-e-9"}, {"id": "gpt-image-1"}]}

    def fake_get(url, **kwargs):
        seen.update(url=url, headers=kwargs["headers"])
        return Reply()
    monkeypatch.setattr(httpx, "get", fake_get)
    llm.set_key("openai", FAKE)
    assert llm.list_models("openai") == ["gpt-test", "o3-test"]
    assert seen["url"] == "https://api.openai.com/v1/models" and seen["headers"] == {"Authorization": f"Bearer {FAKE}"}
    llm.set_key("anthropic", FAKE)
    llm.list_models("anthropic")
    assert seen["url"].startswith("https://api.anthropic.com/v1/models") and seen["headers"]["x-api-key"] == FAKE
    llm.forget_key("anthropic")
    with pytest.raises(RuntimeError, match="No key"):
        llm.list_models("anthropic")

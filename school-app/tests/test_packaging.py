"""The offline Windows package: the launcher's decisions, without starting anything."""
import importlib.util
import socket
import subprocess
from pathlib import Path

import pytest

PACKAGING = Path(__file__).resolve().parents[1] / "packaging" / "windows"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"packaging_{name}", PACKAGING / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


launch = _load("launch")
download_model = _load("download_model")
build = _load("build")


def test_settings_reads_only_known_names_and_skips_comments(tmp_path):
    path = tmp_path / "settings.txt"
    path.write_text("# a comment\n\nOPENAI_API_KEY = made-up-key \n# ANTHROPIC_API_KEY=commented-out\n"
                    "ATHAR_LLM_BASE_URL=\"https://example.test/v1\"\nPATH=C:\\somewhere\nPYTHONPATH=evil\n"
                    "ATHAR_LLM_MODEL=\nnot a setting line\n", encoding="utf-8")
    assert launch.read_settings(path) == {"OPENAI_API_KEY": "made-up-key",
                                          "ATHAR_LLM_BASE_URL": "https://example.test/v1"}


def test_settings_file_may_be_missing(tmp_path):
    assert launch.read_settings(tmp_path / "settings.txt") == {}


def test_the_shipped_settings_file_sets_nothing():
    """Every line in the template is a comment, so a fresh package uses no key and no outside address."""
    assert launch.read_settings(PACKAGING / "files" / "settings.txt") == {}


def test_find_model_takes_the_largest_and_ignores_vision_addons_and_partial_downloads(tmp_path):
    assert launch.find_model(tmp_path / "missing") is None
    assert launch.find_model(tmp_path) is None
    (tmp_path / "mmproj-big.gguf").write_bytes(b"x" * 500)
    (tmp_path / "small.gguf").write_bytes(b"x" * 10)
    (tmp_path / "model.gguf").write_bytes(b"x" * 100)
    (tmp_path / "model.gguf.part").write_bytes(b"x" * 900)
    (tmp_path / "notes.txt").write_text("x" * 999)
    assert launch.find_model(tmp_path).name == "model.gguf"


def test_free_port_moves_past_a_port_in_use():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen(1)
        port = taken.getsockname()[1]
        assert not launch.port_is_free(port)
        assert launch.free_port(port) > port


def test_first_start_copies_the_school_once_and_never_overwrites(tmp_path):
    seed = tmp_path / "app" / "data"
    (seed / "inbox").mkdir(parents=True)
    (seed / "athar.db").write_text("seed")
    (seed / "inbox" / "note.txt").write_text("a note")
    assert launch.first_run_data(tmp_path) is True
    assert (tmp_path / "data" / "inbox" / "note.txt").read_text() == "a note"
    (tmp_path / "data" / "athar.db").write_text("the teacher's own work")
    assert launch.first_run_data(tmp_path) is False
    assert (tmp_path / "data" / "athar.db").read_text() == "the teacher's own work"


def test_app_environment_uses_only_the_package_and_this_computer(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "C:\\someone\\elses\\code")
    monkeypatch.setenv("PYTHONHOME", "C:\\another\\python")
    env = launch.child_env(tmp_path, {}, 8780, "http://127.0.0.1:11812/v1")
    assert env["PYTHONPATH"] == str(tmp_path / "app" / "src")
    assert "PYTHONHOME" not in env
    assert env["ATHAR_WEB_HOST"] == "127.0.0.1"
    assert env["ATHAR_DB"] == str(tmp_path / "data" / "athar.db")
    assert env["ATHAR_LLM_BASE_URL"] == "http://127.0.0.1:11812/v1"
    assert env["ATHAR_LLM_MODEL"] == launch.MODEL_NAME
    # The borrowed document reader runs from the package's own Python, never from a download.
    assert env["ATHAR_MARKITDOWN_CMD"] == str(tmp_path / "runtime" / "python" / "python.exe")
    assert env["ATHAR_MARKITDOWN_ARGS"] == "-S -m _markitdown_runner"
    assert env["HF_HUB_OFFLINE"] == "1"


def test_an_address_in_settings_replaces_the_local_model(tmp_path):
    settings = {"ATHAR_LLM_BASE_URL": "https://example.test/v1", "ATHAR_LLM_MODEL": "some/model",
                "ATHAR_LLM_API_KEY": "made-up-key", "ATHAR_WEB_PORT": "9000"}
    env = launch.child_env(tmp_path, settings, 9000, None)
    assert env["ATHAR_LLM_BASE_URL"] == "https://example.test/v1"
    assert env["ATHAR_LLM_MODEL"] == "some/model"
    assert env["ATHAR_LLM_REASONING"] == "default"   # hosted endpoints reject the local-only hint
    assert env["ATHAR_WEB_PORT"] == "9000"


def test_the_package_has_its_own_ports_beside_an_installed_athar():
    """The earlier package may still run on 8765 and 11811 on the same computer."""
    assert launch.APP_PORT == 8780
    assert launch.RUNNER_PORT == 11812
    for name in ("READ ME FIRST.txt", "settings.txt"):
        text = (PACKAGING / "files" / name).read_text(encoding="utf-8")
        assert "127.0.0.1:8780" in text
        assert "8765" not in text and "11811" not in text


def test_the_launcher_names_no_curriculum_pack(tmp_path, monkeypatch):
    monkeypatch.delenv("ATHAR_PACK", raising=False)
    assert "ATHAR_PACK" not in launch.child_env(tmp_path, {}, 8780, None)


def test_the_build_seeds_the_default_school_and_names_no_pack(tmp_path, monkeypatch):
    assert build.SEED_COMMAND[-1] == "seed"
    monkeypatch.setenv("ATHAR_PACK", "some-old-pack")
    monkeypatch.delenv("ATHAR_DEMO_PACK", raising=False)
    env = build.package_env(tmp_path)
    assert "ATHAR_PACK" not in env and "ATHAR_DEMO_PACK" not in env
    monkeypatch.setenv("ATHAR_DEMO_PACK", "egypt-maths")
    assert build.package_env(tmp_path)["ATHAR_DEMO_PACK"] == "egypt-maths"


def test_the_source_line_survives_a_repository_with_no_commit(tmp_path):
    assert build.source_state(tmp_path / "missing") == "not yet committed"
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    assert build.source_state(tmp_path) == "not yet committed"


def test_the_package_is_named_athar():
    assert build.NAME == "Athar"
    names = {p.name for p in (PACKAGING / "files").iterdir()}
    assert {"Start Athar.cmd", "Stop Athar.cmd"} <= names
    assert not any("Meska" in name for name in names)
    read_me = (PACKAGING / "files" / "READ ME FIRST.txt").read_text(encoding="utf-8")
    assert '"Start Athar"' in read_me and '"Stop Athar"' in read_me


def test_without_a_model_no_local_address_is_set(tmp_path, monkeypatch):
    monkeypatch.delenv("ATHAR_LLM_BASE_URL", raising=False)
    env = launch.child_env(tmp_path, {}, 8780, None)
    assert "ATHAR_LLM_BASE_URL" not in env


def test_the_model_runner_listens_on_this_computer_only_and_stays_offline(tmp_path):
    command = launch.runner_command(tmp_path, tmp_path / "m.gguf", 11812)
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert "--offline" in command and "--no-webui" in command
    assert command[command.index("--alias") + 1] == launch.MODEL_NAME


def test_stop_without_a_running_copy_is_quiet(tmp_path):
    said = []
    assert launch.stop_running(tmp_path, say=said.append) == 0
    assert "not running" in said[0]


def test_download_continues_a_partial_file(tmp_path, monkeypatch):
    whole = bytes(range(256)) * 40
    seen = {}

    class Reply:
        def __init__(self, data, status):
            self.data, self.status = data, status

        def read(self, n):
            block, self.data = self.data[:n], self.data[n:]
            return block

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=0):
        seen["range"] = request.get_header("Range")
        start = int(seen["range"].split("=")[1].rstrip("-")) if seen["range"] else 0
        return Reply(whole[start:], 206 if seen["range"] else 200)

    monkeypatch.setattr(download_model.urllib.request, "urlopen", fake_urlopen)
    target = tmp_path / "model.gguf"
    (tmp_path / "model.gguf.part").write_bytes(whole[:1000])

    class Quiet:
        def write(self, _):
            pass

        def flush(self):
            pass

    download_model.download("https://example.test/model.gguf", target, len(whole), out=Quiet())
    assert seen["range"] == "bytes=1000-"
    assert target.read_bytes() == whole
    assert not (tmp_path / "model.gguf.part").exists()
    assert download_model.sha256_of(target) == __import__("hashlib").sha256(whole).hexdigest()


def test_the_download_and_the_build_agree_on_the_model():
    assert download_model.MODEL_SHA256 == build.MODEL_SHA256
    assert download_model.MODEL_URL.startswith("https://huggingface.co/")
    assert download_model.MODEL_URL.endswith(download_model.MODEL_FILE)


def test_everything_the_build_fetches_is_pinned():
    for file_name, checksum in build.LLAMA.values():
        assert build.LLAMA_BUILD in file_name and len(checksum) == 64
    assert "==" in build.MARKITDOWN_MCP


@pytest.mark.parametrize("name", ["Start Athar.cmd", "Stop Athar.cmd", "Download the model.cmd"])
def test_the_start_files_use_only_the_python_in_the_package(name):
    text = (PACKAGING / "files" / name).read_text(encoding="utf-8")
    assert '"runtime\\python\\python.exe" -E -s' in text
    assert "http" not in text.lower()


def test_the_package_documents_have_no_dashes_and_no_key():
    for name in ("READ ME FIRST.txt", "settings.txt"):
        text = (PACKAGING / "files" / name).read_text(encoding="utf-8")
        assert "\u2014" not in text and "\u2013" not in text
        assert "sk-" not in text


def test_the_launcher_picks_a_chat_model_from_a_local_server(tmp_path, monkeypatch):
    """With no model file, a model program already running on this computer is used as it is."""
    assert launch.pick_model(["text-embedding-nomic", "qwen/qwen3.8-27b", "qwen3.5-9b"]) == "qwen3.5-9b"
    assert launch.pick_model(["text-embedding-nomic", "llama-3", "qwen3.5-9b-uncensored-x", "qwen/qwen3.8-27b"]) == "qwen/qwen3.8-27b"
    assert launch.pick_model(["text-embedding-nomic", "llama-3"]) == "llama-3"
    assert launch.pick_model(["text-embedding-nomic"]) is None and launch.pick_model([]) is None
    assert all(url.startswith("http://127.0.0.1:") for _, url in launch.LOCAL_SERVERS)      # this computer only
    monkeypatch.setattr(launch, "LOCAL_SERVERS", (("Nothing", "http://127.0.0.1:9/v1"),))
    assert launch.find_local_server(timeout=0.3) is None
    env = launch.child_env(tmp_path, {}, 8780, "http://127.0.0.1:1234/v1", "llama-3")
    assert env["ATHAR_LLM_MODEL"] == "llama-3" and env["ATHAR_LLM_BASE_URL"] == "http://127.0.0.1:1234/v1"


def test_the_model_is_offered_once_and_never_without_a_person_to_answer(tmp_path, monkeypatch):
    assert launch.wants_model("") and launch.wants_model("y") and launch.wants_model("  ")
    assert not launch.wants_model("n") and not launch.wants_model(" No ") and not launch.wants_model("لا")
    monkeypatch.delenv("ATHAR_NO_BROWSER", raising=False)
    monkeypatch.setattr(launch.sys, "stdin", None)                       # no window to type in: never ask, never download
    assert launch.offer_model(tmp_path) is False and not (tmp_path / "data" / "model-asked.txt").exists()

    class Keyboard:
        def isatty(self):
            return True
    calls = []
    monkeypatch.setattr(launch.sys, "stdin", Keyboard())
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    monkeypatch.setattr(launch.subprocess, "call", lambda *a, **k: calls.append(a))
    assert launch.offer_model(tmp_path) is False and calls == []          # said no: nothing is fetched
    assert (tmp_path / "data" / "model-asked.txt").exists()
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    assert launch.offer_model(tmp_path) is False and calls == []          # already asked once: not asked again


def test_the_runner_gets_the_part_that_reads_photos_when_it_is_there(tmp_path):
    model = tmp_path / "Qwen3.5-9B-Q4_K_M.gguf"
    model.write_bytes(b"x")
    assert launch.find_vision(tmp_path) is None
    assert "--no-mmproj" in launch.runner_command(tmp_path, model, 11812)
    vision = tmp_path / "mmproj-Qwen3.5-9B-BF16.gguf"
    vision.write_bytes(b"x")
    command = launch.runner_command(tmp_path, model, 11812)
    assert command[command.index("--mmproj") + 1] == str(vision) and "--no-mmproj" not in command
    assert launch.find_model(tmp_path) == model            # the add-on is never mistaken for the model itself


def test_the_guide_goes_into_the_folder_and_opens_without_the_app(tmp_path):
    import re

    build.add_guide(tmp_path)
    page = (tmp_path / "Guide" / "guide.html").read_text(encoding="utf-8")
    assert "\u2014" not in page and "\u2013" not in page
    assert "http://" not in page.replace("http://127.0.0.1:8780", "") and "https://" not in page   # nothing from the internet
    pictures = set(re.findall(r'src="(img/[^"]+)"', page))
    assert len(pictures) >= 20 and all((tmp_path / "Guide" / p).is_file() for p in pictures)
    assert {p.rsplit("-", 1)[1] for p in pictures} == {"en.png", "ar.png"}        # every picture in both languages
    films = set(re.findall(r'src="(video/[^"]+)"', page))
    assert films == {"video/athar-for-parents.mp4", "video/athar-for-teachers.mp4"}
    assert all((tmp_path / "Guide" / f).stat().st_size > 1_000_000 for f in films)
    for name, lang in build.GUIDE_LINKS.items():
        assert name.isascii()                    # an Arabic file name was lost by one unzip program
        assert f"Guide/guide.html?lang={lang}" in (tmp_path / name).read_text(encoding="utf-8")


def test_the_about_file_and_the_screenshots_go_into_the_folder(tmp_path):
    import re

    build.add_about(tmp_path)
    about = (tmp_path / "About Athar.md").read_text(encoding="utf-8")
    assert "for a parent" in about and "for a teacher" in about
    assert "\u2014" not in about and "\u2013" not in about
    pictures = re.findall(r"\]\((Screenshots/[^)]+)\)", about)
    assert len(pictures) >= 4 and all((tmp_path / p).is_file() for p in pictures)
    for lang in ("English", "Arabic"):
        assert len(list((tmp_path / "Screenshots" / lang).glob("*.png"))) >= 15
    assert all(p.name.isascii() for p in (tmp_path / "Screenshots").rglob("*"))


def test_the_read_me_has_no_stray_control_characters():
    text = (PACKAGING / "files" / "READ ME FIRST.txt").read_text(encoding="utf-8")
    assert not [c for c in text if ord(c) < 32 and c not in "\r\n\t"]
    assert "About Athar" in text and "Screenshots" in text


def test_the_arabic_about_page_shows_pictures_that_exist_and_matches_the_glossary():
    import re

    docs = PACKAGING.parents[1] / "docs"
    about = (docs / "ABOUT.ar.md").read_text(encoding="utf-8")
    assert "\u2014" not in about and "\u2013" not in about
    pictures = re.findall(r"\]\((screenshots/[^)]+)\)", about)
    assert len(pictures) >= 4 and all((docs / p).is_file() for p in pictures)
    assert "ولي الأمر" in about and "المدرس" in about and "النموذج" in about
    for name in ("ABOUT.ar.md", "GETTING-STARTED.ar.md"):
        assert "الموديل" not in (docs / name).read_text(encoding="utf-8")       # the glossary says النموذج

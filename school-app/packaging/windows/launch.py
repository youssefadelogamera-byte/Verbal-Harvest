"""Start Athar from the offline Windows package.

This file uses the standard library only. It is run by the Python that ships in the package:

    runtime\\python\\python.exe -E -s app\\launch.py          start
    runtime\\python\\python.exe -E -s app\\launch.py --stop   stop

What it does, in order:

1. First start only: copies the synthetic school from `app\\data` to `data`, the one folder the app writes to.
2. Reads `settings.txt`, if the person filled any of it in.
3. If a model file is in `models`, starts the bundled model runner (llama.cpp's server) on this computer
   only, first with the graphics card and, if that fails, on the processor.
4. Starts the teacher app on this computer only and opens it in the browser.
5. Waits. Closing the window, or Ctrl+C, stops both.

Nothing here reaches the internet. A model on the internet is used only if the person adds a key on the
Agent page or fills in `settings.txt`.
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

MODEL_NAME = "qwen3.5-9b"          # the name the app asks the runner for
APP_PORT = 8780
RUNNER_PORT = 11812
CONTEXT_TOKENS = 16384
# The only names read from settings.txt. Anything else in the file is ignored.
SETTINGS_KEYS = ("ATHAR_LLM_BASE_URL", "ATHAR_LLM_MODEL", "ATHAR_LLM_API_KEY", "ATHAR_LLM_REASONING",
                 "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ATHAR_WEB_PORT")
# Variables from the person's own shell that could point our Python at other code.
UNSAFE_ENV = ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONUSERBASE", "VIRTUAL_ENV")


def package_root() -> Path:
    """The extracted folder: this file sits in `<root>\\app`."""
    return Path(__file__).resolve().parent.parent


def read_settings(path: Path) -> dict[str, str]:
    """`NAME=value` lines from settings.txt. Lines starting with # and unknown names are ignored."""
    found: dict[str, str] = {}
    if not path.is_file():
        return found
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip().strip('"').strip("'")
        if name in SETTINGS_KEYS and value:
            found[name] = value
    return found


def find_model(models_dir: Path) -> Path | None:
    """The model file to load: the largest .gguf in `models`, leaving out vision add-ons and
    unfinished downloads."""
    if not models_dir.is_dir():
        return None
    files = [p for p in models_dir.glob("*.gguf") if not p.name.lower().startswith("mmproj")]
    return max(files, key=lambda p: p.stat().st_size) if files else None


# Model programs a person may already have running on this computer, and where they listen.
LOCAL_SERVERS = (("LM Studio", "http://127.0.0.1:1234/v1"), ("Ollama", "http://127.0.0.1:11434/v1"))


def pick_model(ids: list[str]) -> str | None:
    """Which of a server's models to use: the one the package is tested with if it is there, then any
    Qwen, then the first. Embedding models cannot chat and are left out."""
    chat = [i for i in ids if isinstance(i, str) and "embed" not in i.lower()]
    for wanted in (lambda i: i.lower() == MODEL_NAME, lambda i: MODEL_NAME in i.lower() and "uncensored" not in i.lower(),
                   lambda i: "qwen" in i.lower() and "uncensored" not in i.lower()):
        found = next((i for i in chat if wanted(i)), None)
        if found:
            return found
    return chat[0] if chat else None


def find_local_server(timeout: float = 1.5) -> tuple[str, str, str] | None:
    """(name, address, model) of a model program already running on this computer, or None.
    Only this computer is asked: nothing leaves it."""
    for name, url in LOCAL_SERVERS:
        try:
            with urllib.request.urlopen(url + "/models", timeout=timeout) as reply:
                listed = json.loads(reply.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, OSError, ValueError):
            continue
        model = pick_model([m.get("id") for m in listed.get("data") or [] if isinstance(m, dict)])
        if model:
            return name, url, model
    return None


def wants_model(answer: str) -> bool:
    """Enter alone means yes. Only a clear no, in English or Arabic, means no."""
    return answer.strip().lower() not in ("n", "no", "لا", "لأ")


def offer_model(root: Path) -> bool:
    """The first time there is no model at all, offer to fetch it, so a person who has never heard of
    LM Studio can still use the assistant. Asked once: the answer is remembered in the data folder.
    True when the model file is now there."""
    asked = root / "data" / "model-asked.txt"
    if asked.exists() or os.environ.get("ATHAR_NO_BROWSER") or not (sys.stdin and sys.stdin.isatty()):
        return False
    print("  The assistant needs a model, and there is none on this computer yet.")
    print("  Athar can download one now: two files, 6.1 GB in all, free and open. It then works with no internet.")
    print("  Everything else in Athar works without it, so you can also do this later")
    print("  with \"Download the model\" in this folder.\n")
    try:
        answer = input("  Download the model now? Press Enter for yes, or type n and Enter for later: ")
    except (EOFError, KeyboardInterrupt):
        return False
    asked.parent.mkdir(exist_ok=True)
    asked.write_text("The question about downloading the model was asked once. Delete this file to be asked again.\n",
                     encoding="utf-8")
    if not wants_model(answer):
        print("  Later, then. Starting without a model.\n")
        return False
    python = root / "runtime" / "python" / "python.exe"
    subprocess.call([str(python), "-E", "-s", "-u", str(root / "app" / "download_model.py")])
    return find_model(root / "models") is not None


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def free_port(preferred: int, tries: int = 30) -> int:
    """`preferred` if nothing is using it, otherwise the next free port after it."""
    for port in range(preferred, preferred + tries):
        if port_is_free(port):
            return port
    raise RuntimeError(f"No free port between {preferred} and {preferred + tries - 1}.")


def first_run_data(root: Path) -> bool:
    """Copy the synthetic school into `data` if it is not there yet. Returns True if it copied."""
    data = root / "data"
    if (data / "athar.db").is_file():
        return False
    shutil.copytree(root / "app" / "data", data, dirs_exist_ok=True)
    return True


def memory_gb() -> float | None:
    """Installed memory in GB, or None when it cannot be read (not Windows)."""
    try:
        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                        ("avail", ctypes.c_ulonglong), ("total_page", ctypes.c_ulonglong),
                        ("avail_page", ctypes.c_ulonglong), ("total_virtual", ctypes.c_ulonglong),
                        ("avail_virtual", ctypes.c_ulonglong), ("avail_extended", ctypes.c_ulonglong)]
        status = Status()
        status.length = ctypes.sizeof(Status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return status.total / 1024 ** 3
    except (AttributeError, OSError):
        return None


def child_env(root: Path, settings: dict[str, str], app_port: int, runner_url: str | None,
              model_name: str = MODEL_NAME) -> dict[str, str]:
    """The environment for the app. The person's own Python settings are removed so that only the
    Python and the libraries inside the package are used. No curriculum pack is named here: each
    learner in the data carries the pack it was generated on."""
    env = {k: v for k, v in os.environ.items() if k.upper() not in UNSAFE_ENV}
    python = root / "runtime" / "python" / "python.exe"
    env.update({
        "PYTHONPATH": str(root / "app" / "src"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONUTF8": "1",
        "ATHAR_DB": str(root / "data" / "athar.db"),
        "ATHAR_PACKS": str(root / "app" / "packs"),
        "ATHAR_WEB_HOST": "127.0.0.1",
        "ATHAR_WEB_PORT": str(app_port),
        # The document reader we borrow (markitdown) runs from the package, not from the internet.
        "ATHAR_MARKITDOWN_CMD": str(python),
        "ATHAR_MARKITDOWN_ARGS": "-S -m _markitdown_runner",
        # Libraries that would otherwise look online for files they already have.
        "HF_HUB_OFFLINE": "1",
        "DO_NOT_TRACK": "1",
    })
    if runner_url:
        env.update({"ATHAR_LLM_BASE_URL": runner_url, "ATHAR_LLM_MODEL": model_name,
                    "ATHAR_LLM_API_KEY": "local", "ATHAR_LLM_REASONING": "default"})
    for name, value in settings.items():
        if name != "ATHAR_WEB_PORT":
            env[name] = value
    if "ATHAR_LLM_BASE_URL" in settings and "ATHAR_LLM_REASONING" not in settings:
        # Hosted endpoints reject the "no reasoning" hint that a local runner accepts.
        env["ATHAR_LLM_REASONING"] = "default"
    return env


def answers(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as reply:
            return reply.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def wait_until(url: str, process: subprocess.Popen, seconds: float) -> bool:
    """True once `url` answers. False if the process stops first or time runs out."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        if answers(url):
            return True
        time.sleep(1.0)
    return False


def find_vision(models_dir: Path) -> Path | None:
    """The add-on file that lets the model see pictures, when it is in the models folder."""
    files = sorted(models_dir.glob("mmproj*.gguf")) if models_dir.is_dir() else []
    return files[0] if files else None


def runner_command(folder: Path, model: Path, port: int) -> list[str]:
    vision = find_vision(model.parent)
    return [str(folder / "llama-server.exe"), "--model", str(model), "--alias", MODEL_NAME,
            "--host", "127.0.0.1", "--port", str(port), "--ctx-size", str(CONTEXT_TOKENS),
            "--parallel", "1", "--reasoning", "off", "--no-webui", "--offline",
            *(["--mmproj", str(vision)] if vision else ["--no-mmproj"])]


def start_runner(root: Path, model: Path, port: int, say=print) -> tuple[subprocess.Popen, str] | None:
    """Start the model runner. Tries the graphics card build first, then the processor build."""
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    for name, label, wait in (("vulkan", "the graphics card", 240), ("cpu", "the processor", 600)):
        folder = root / "runtime" / "llama" / name
        if not (folder / "llama-server.exe").is_file():
            continue
        say(f"  Loading the model with {label}. This can take a minute or two...")
        log = open(logs / f"model-runner-{name}.log", "w", encoding="utf-8", errors="replace")  # noqa: SIM115
        process = subprocess.Popen(runner_command(folder, model, port), cwd=folder, stdout=log,
                                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        if wait_until(f"http://127.0.0.1:{port}/health", process, wait):
            return process, label
        stop(process)
        log.close()
        say(f"  That did not work with {label} (details in logs\\model-runner-{name}.log).")
    return None


def stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def state_file(root: Path) -> Path:
    return root / "logs" / "running.json"


def stop_running(root: Path, say=print) -> int:
    """Stop an Athar started earlier from this folder, using the process ids it wrote down."""
    path = state_file(root)
    if not path.is_file():
        say("Athar is not running from this folder.")
        return 0
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    for pid in state.get("pids", []):
        subprocess.run(["taskkill", "/PID", str(int(pid)), "/T", "/F"], capture_output=True, check=False)
    path.unlink(missing_ok=True)
    say("Athar has been stopped.")
    return 0


def main(argv: list[str]) -> int:
    root = package_root()
    if "--stop" in argv:
        return stop_running(root)
    (root / "logs").mkdir(exist_ok=True)
    print("\n  Athar\n  -----")

    # Already running from this folder? Then only open the browser.
    if state_file(root).is_file():
        try:
            earlier = json.loads(state_file(root).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            earlier = {}
        if earlier.get("url") and answers(earlier["url"]):
            print(f"  It is already running at {earlier['url']}")
            if not os.environ.get("ATHAR_NO_BROWSER"):
                webbrowser.open(earlier["url"])
            return 0
        state_file(root).unlink(missing_ok=True)

    if first_run_data(root):
        print("  First start: the synthetic school has been set up in the data folder.")
    settings = read_settings(root / "settings.txt")

    runner, runner_url, model_name = None, None, MODEL_NAME
    model = find_model(root / "models")
    if model is None and "ATHAR_LLM_BASE_URL" not in settings and find_local_server() is None and offer_model(root):
        model = find_model(root / "models")
    if "ATHAR_LLM_BASE_URL" in settings:
        print(f"  Model: the address in settings.txt ({settings['ATHAR_LLM_BASE_URL']}).")
    elif model is None and (found := find_local_server()):
        _, runner_url, model_name = found
        print(f"  Model: {model_name}, from {found[0]}, which is running on this computer.")
        print("  Keep it running while you use the agent. To choose another of its models, use the Agent page.")
    elif model is None:
        print("  No model file in the models folder, and no LM Studio or Ollama running on this computer.")
        print("  You can still use everything that needs no model (maps, review, reports).")
        print("  To get the model: run \"Download the model\". To use a model on the internet instead:")
        print("  open the Agent page, then \"Cloud models\", and add a key.")
    else:
        memory = memory_gb()
        if memory is not None and memory < 11:
            print(f"  Note: this computer has {memory:.0f} GB of memory. The model wants about 8 GB free,")
            print("  so it may be slow. A model on the internet (Agent page, Cloud models) is the other way.")
        port = free_port(RUNNER_PORT)
        started = start_runner(root, model, port)
        if started:
            runner, label = started
            runner_url = f"http://127.0.0.1:{port}/v1"
            print(f"  Model: {model.name}, running on this computer with {label}.")
        else:
            print("  The model could not be started on this computer. The rest of the app still works,")
            print("  and a model on the internet can be added on the Agent page under Cloud models.")

    app_port = free_port(int(settings.get("ATHAR_WEB_PORT", APP_PORT)))
    url = f"http://127.0.0.1:{app_port}"
    python = root / "runtime" / "python" / "python.exe"
    log = open(root / "logs" / "app.log", "w", encoding="utf-8", errors="replace")  # noqa: SIM115
    app = subprocess.Popen([str(python), "-s", "-m", "athar.cli", "serve"], cwd=root / "app",
                           env=child_env(root, settings, app_port, runner_url, model_name), stdout=log,
                           stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    try:
        if not wait_until(url + "/api/learners", app, 120):
            print("  The app did not start. Details are in logs\\app.log.")
            return 1
        state_file(root).write_text(json.dumps({
            "url": url, "pids": [p.pid for p in (app, runner) if p is not None] + [os.getpid()]}), encoding="utf-8")
        print(f"\n  Ready. Open this address in your browser:\n\n      {url}\n")
        print("  It works on this computer only. All data in it is synthetic.")
        print("  Keep this window open. Close it, or press Ctrl+C, to stop Athar.\n")
        if not os.environ.get("ATHAR_NO_BROWSER"):
            webbrowser.open(url)
        while app.poll() is None:
            if runner is not None and runner.poll() is not None:
                print("  The model runner stopped. See the logs folder. The app keeps running without it.")
                runner = None
            time.sleep(1.5)
        print("  The app stopped. Details are in logs\\app.log.")
        return app.returncode or 0
    except KeyboardInterrupt:
        print("\n  Stopping...")
        return 0
    finally:
        stop(app)
        stop(runner)
        log.close()
        state_file(root).unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

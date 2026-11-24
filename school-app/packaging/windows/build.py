"""Build the offline Windows package of Athar: one folder, zipped, that runs with no internet.

Run on Windows, from the repository root, with internet (the build fetches libraries; the result
needs none):

    uv run python packaging/windows/build.py --out C:/somewhere/outside/the/repo
    uv run python packaging/windows/build.py --out ... --model C:/path/Qwen3.5-9B-Q4_K_M.gguf

What goes into the folder `Athar`:

    Start Athar.cmd, Stop Athar.cmd, Download the model.cmd, READ ME FIRST.txt, settings.txt
    app/        this project's code, the curriculum packs, and a freshly generated synthetic school
    runtime/    a private copy of Python with every library, and llama.cpp's server (two builds)
    models/     the open-weights model file, when --model is given
    LICENSES/   the licence of each part

Two zips are written: one without the model, and one with it when --model is given.
Everything fetched is pinned to a version and, for the model runner, checked against a checksum.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
NAME = "Athar"

# llama.cpp's server, from its official releases. MIT licence.
LLAMA_BUILD = "b12359"
LLAMA_BASE = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_BUILD}/"
LLAMA = {
    "cpu": (f"llama-{LLAMA_BUILD}-bin-win-cpu-x64.zip",
            "837c1655e87df3b66989f4be33a792a1399c785bf259038dc75c900096683e69"),
    "vulkan": (f"llama-{LLAMA_BUILD}-bin-win-vulkan-x64.zip",
               "e8d18c6e4210cca87e7307c2ea78363ac8d158e4e1397358ec96ab70b53a0d5e"),
}
LLAMA_LICENSE = f"https://raw.githubusercontent.com/ggml-org/llama.cpp/{LLAMA_BUILD}/LICENSE"

# The document-conversion server we borrow (Microsoft's markitdown), pinned.
MARKITDOWN_MCP = "markitdown-mcp==0.0.1a7"

# The model the package is tested with. Apache 2.0, so it may be passed on.
MODEL_SHA256 = "cd76ec205963b3b33350093e6904d9de16c4e666fd104e1f632d25c7f15f2a13"
VISION_SHA256 = "330d17547bfdbcd0e7a0cb3f4b06b4ceeac0aaa1e449122d9d66ef957aeb74b3"
MODEL_SOURCE = "https://huggingface.co/lmstudio-community/Qwen3.5-9B-GGUF (base model: Qwen/Qwen3.5-9B)"

# Parts of the Python copy the app never uses.
PYTHON_SKIP = shutil.ignore_patterns("Scripts", "include", "libs", "tcl", "test", "idlelib", "tkinter",
                                     "turtledemo", "ensurepip", "__pycache__", "EXTERNALLY-MANAGED", "BUILD")


def say(text: str) -> None:
    print(f"[build] {text}", flush=True)


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    kwargs.setdefault("check", True)
    return subprocess.run([str(c) for c in command], **kwargs)  # noqa: PLW1510


def _make_writable_and_retry(function, path, _error) -> None:
    """Folders copied out of OneDrive carry a read-only mark that stops Windows deleting them."""
    os.chmod(path, 0o700)
    function(path)


def remove_tree(path: Path) -> None:
    """Delete a folder. Windows sometimes holds a file for a moment (antivirus, indexing), so retry."""
    for attempt in range(6):
        if not path.exists():
            return
        try:
            shutil.rmtree(path, onexc=_make_writable_and_retry)
        except OSError:
            if attempt == 5:
                raise
            time.sleep(2)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def fetch(url: str, target: Path, sha256: str | None = None) -> Path:
    if not target.is_file():
        say(f"fetching {url}")
        target.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, headers={"User-Agent": "athar-build"})
        with urllib.request.urlopen(request, timeout=120) as reply, target.open("wb") as fh:
            shutil.copyfileobj(reply, fh)
    if sha256 and sha256_of(target) != sha256:
        target.unlink()
        raise SystemExit(f"{target.name} does not match its checksum. It was removed; run the build again.")
    return target


def standalone_python() -> Path:
    """The folder of a self-contained CPython 3.12 that uv manages. Such a copy can be moved."""
    base = Path(run(["uv", "python", "dir"], capture_output=True, text=True).stdout.strip())
    homes = sorted((h for h in base.glob("cpython-3.12.*-windows-x86_64-none") if (h / "python312.dll").is_file()),
                   key=lambda h: [int(n) for n in h.name.split("-")[1].split(".")])
    if not homes:
        raise SystemExit("No uv-managed Python 3.12 found. Run: uv python install 3.12")
    return homes[-1]


def copy_python(stage: Path) -> Path:
    home = standalone_python()
    say(f"copying Python from {home}")
    target = stage / "runtime" / "python"
    shutil.copytree(home, target, ignore=PYTHON_SKIP)
    return target / "python.exe"


def install_libraries(python: Path, work: Path) -> None:
    say("installing the libraries into the package's own Python")
    requirements = work / "requirements.txt"
    run(["uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--no-hashes", "--format",
         "requirements-txt", "-o", requirements], cwd=REPO, capture_output=True)
    run(["uv", "pip", "install", "--python", python, "--break-system-packages", "--link-mode", "copy",
         "-r", requirements])
    # The borrowed document reader needs a newer `mcp` than the app, so it gets a folder of its own.
    say("installing the document reader into its own folder")
    run(["uv", "pip", "install", "--python", python, "--target", python.parents[1] / "markitdown",
         "--prerelease", "allow", "--link-mode", "copy", MARKITDOWN_MCP])
    shutil.rmtree(python.parent / "Scripts", ignore_errors=True)  # launchers there hold absolute paths


# Plain letters only: a file name in Arabic did not survive every unzip program.
GUIDE_LINKS = {"Guide (English).html": "en", "Guide (Arabic).html": "ar"}


def add_guide(stage: Path) -> None:
    """The guide with pictures, as plain files that open by double-click even when Athar is not running:
    the page and its pictures in `Guide`, and one file per language beside the start files that opens it."""
    shutil.copytree(REPO / "src" / "athar" / "web" / "static" / "guide", stage / "Guide")
    for name, lang in GUIDE_LINKS.items():
        (stage / name).write_text(
            '<!doctype html><meta charset="utf-8"><title>Athar</title>'
            f'<meta http-equiv="refresh" content="0; url=Guide/guide.html?lang={lang}">'
            f'<a href="Guide/guide.html?lang={lang}">Open the guide</a>\n', encoding="utf-8", newline="")


def add_about(stage: Path) -> None:
    """What Athar is and what it does for a parent and a teacher, with the pictures it shows, in English and Arabic."""
    shutil.copytree(REPO / "docs" / "screenshots", stage / "Screenshots")
    text = (REPO / "docs" / "ABOUT.md").read_text(encoding="utf-8").replace("](screenshots/", "](Screenshots/")
    (stage / "About Athar.md").write_text(text.replace("\r\n", "\n").replace("\n", "\r\n"), encoding="utf-8", newline="")


def copy_app(stage: Path) -> None:
    say("copying the app")
    app = stage / "app"
    skip = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(REPO / "src" / "athar", app / "src" / "athar", ignore=skip)
    shutil.copytree(REPO / "packs", app / "packs", ignore=skip)
    for name in ("launch.py", "download_model.py"):
        shutil.copy2(HERE / name, app / name)
    # Started as `python -S -m _markitdown_runner`; it is found through the app's source folder.
    shutil.copy2(HERE / "markitdown_runner.py", app / "src" / "_markitdown_runner.py")
    for path in (HERE / "files").iterdir():
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\n", "\r\n")
        (stage / path.name).write_text(text, encoding="utf-8", newline="")
    add_guide(stage)
    add_about(stage)
    (stage / "models").mkdir()
    (stage / "models" / "PUT THE MODEL FILE HERE.txt").write_text(
        "The model file goes in this folder: Qwen3.5-9B-Q4_K_M.gguf\r\n\r\n"
        "Run \"Download the model\" in the folder above, or copy the file here yourself.\r\n"
        "Any other .gguf chat model also works; the largest one in this folder is used.\r\n",
        encoding="utf-8", newline="")


def package_env(stage: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("PYTHON", "VIRTUAL_ENV", "ATHAR_", "UV_"))}
    env.update({"PYTHONPATH": str(stage / "app" / "src"), "PYTHONNOUSERSITE": "1", "PYTHONUTF8": "1",
                "ATHAR_DB": str(stage / "app" / "data" / "athar.db"), "ATHAR_PACKS": str(stage / "app" / "packs")})
    # The one project setting that is let through: which curriculum the synthetic school is built on.
    if os.environ.get("ATHAR_DEMO_PACK"):
        env["ATHAR_DEMO_PACK"] = os.environ["ATHAR_DEMO_PACK"]
    return env


# `athar seed` with no pack named: the project's own default (the setting ATHAR_DEMO_PACK) decides.
SEED_COMMAND = ("-s", "-m", "athar.cli", "seed")
STORY_COMMAND = ("-s", "-m", "athar.cli", "story")


def seed_school(stage: Path, python: Path) -> None:
    """Generate the synthetic school with the package's own Python. This is also the first test
    that the copied Python and its libraries work on their own."""
    say("generating the synthetic school")
    env = package_env(stage)
    app = stage / "app"
    run([python, *SEED_COMMAND], cwd=app, env=env, capture_output=True)
    run([python, *STORY_COMMAND], cwd=app, env=env, capture_output=True)
    tidy = ("import sqlite3, sys; c = sqlite3.connect(sys.argv[1]); "
            "c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.execute('PRAGMA journal_mode=DELETE'); "
            "print(c.execute('SELECT COUNT(*) FROM learners').fetchone()[0], 'learners'); c.close()")
    run([python, "-s", "-c", tidy, app / "data" / "athar.db"], env=env)
    for leftover in ("athar.db-wal", "athar.db-shm", "runs", "checkpoints.db"):
        path = app / "data" / leftover
        shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(missing_ok=True)


def compile_python(stage: Path, python: Path) -> None:
    """Compile ahead of time, so that the first start is quick and nothing needs to be written."""
    say("compiling")
    run([python, "-s", "-m", "compileall", "-q", "--invalidation-mode", "unchecked-hash",
         python.parent / "Lib", python.parents[1] / "markitdown", stage / "app"], env=package_env(stage), capture_output=True, check=False)


def add_llama(stage: Path, work: Path) -> None:
    for kind, (file_name, sha256) in LLAMA.items():
        archive = fetch(LLAMA_BASE + file_name, work / "downloads" / kind / file_name, sha256)
        target = stage / "runtime" / "llama" / kind
        target.mkdir(parents=True)
        with zipfile.ZipFile(archive) as zf:
            for item in zf.infolist():
                name = Path(item.filename).name
                # The server, the libraries it loads, and their licences. The other tools are left out.
                if name == "llama-server.exe" or name.lower().endswith(".dll") or name.upper().startswith("LICENSE"):
                    (target / name).write_bytes(zf.read(item))
        say(f"model runner ({kind}): {len(list(target.iterdir()))} files")


def add_licenses(stage: Path, work: Path, with_model: bool) -> None:
    out = stage / "LICENSES"
    out.mkdir()
    shutil.copy2(REPO / "LICENSE", out / "Athar (Apache 2.0).txt")
    shutil.copy2(stage / "runtime" / "python" / "LICENSE.txt", out / "Python.txt")
    shutil.copy2(fetch(LLAMA_LICENSE, work / "downloads" / "llama-LICENSE.txt"), out / "llama.cpp (MIT).txt")
    (out / "READ ME.txt").write_text(
        "What is in this folder and under which licence\r\n"
        "===============================================\r\n\r\n"
        "Athar, the app: Apache 2.0. See \"Athar (Apache 2.0).txt\".\r\n"
        "Python: Python Software Foundation licence. See \"Python.txt\".\r\n"
        f"llama.cpp, the model runner (build {LLAMA_BUILD}): MIT. See \"llama.cpp (MIT).txt\".\r\n"
        "Python libraries: each keeps its own licence file inside\r\n"
        "  runtime\\python\\Lib\\site-packages\\<name>.dist-info\r\n"
        + ("The model, Qwen3.5-9B (4-bit GGUF): Apache 2.0, the same text as \"Athar (Apache 2.0).txt\".\r\n"
           f"  Unchanged file from {MODEL_SOURCE}\r\n" if with_model else
           "The model is not in this package. \"Download the model\" fetches Qwen3.5-9B (Apache 2.0) from\r\n"
           f"  {MODEL_SOURCE}\r\n"),
        encoding="utf-8", newline="")


def _git(*arguments: str, repo: Path) -> str | None:
    """The output of a git command, or None when it fails (no git, not a repository, no commit yet)."""
    try:
        done = run(["git", *arguments], cwd=repo, capture_output=True, text=True, check=False)
    except OSError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def source_state(repo: Path = REPO) -> str:
    """Which state of the code was built: a commit, or the plain fact that there is none yet."""
    commit = _git("rev-parse", "--short", "HEAD", repo=repo)
    if not commit:
        return "not yet committed"
    return f"commit {commit}{' plus local changes' if _git('status', '--porcelain', repo=repo) else ''}"


def version_file(stage: Path, model: Path | None) -> None:
    (stage / "VERSION.txt").write_text(
        f"Athar offline package for Windows\r\nBuilt: {time.strftime('%Y-%m-%d')}\r\n"
        f"Source: Athar, {source_state()}.\r\n"
        f"Model runner: llama.cpp {LLAMA_BUILD}\r\nDocument reader: {MARKITDOWN_MCP}\r\n"
        f"Model: {model.name if model else 'not included'}\r\n", encoding="utf-8", newline="")


def make_zip(stage: Path, target: Path) -> None:
    say(f"writing {target.name}")
    files = sorted(p for p in stage.rglob("*") if p.is_file())
    with zipfile.ZipFile(target, "w", allowZip64=True) as zf:
        for path in files:
            # A model file is already dense: store it as it is. Compress everything else.
            method = zipfile.ZIP_STORED if path.suffix == ".gguf" else zipfile.ZIP_DEFLATED
            zf.write(path, Path(NAME) / path.relative_to(stage), compress_type=method,
                     compresslevel=None if method == zipfile.ZIP_STORED else 6)
    say(f"{target.name}: {target.stat().st_size / 1024 ** 3:.2f} GB, {len(files)} files")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, type=Path, help="folder for the build, outside the repository")
    parser.add_argument("--model", type=Path, help="the .gguf model file to include in a second zip")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("This build runs on Windows.")
    out = args.out.resolve()
    if REPO in out.parents or out == REPO:
        raise SystemExit("Choose an --out folder outside the repository.")
    if args.model:
        if not args.model.is_file():
            raise SystemExit(f"No such model file: {args.model}")
        say("checking the model file")
        if sha256_of(args.model) != MODEL_SHA256:
            raise SystemExit("That model file is not the one this package was tested with (checksum differs).")
    stage = out / NAME
    remove_tree(stage)
    out.mkdir(parents=True, exist_ok=True)

    python = copy_python(stage)
    install_libraries(python, out)
    copy_app(stage)
    seed_school(stage, python)
    compile_python(stage, python)
    add_llama(stage, out)
    add_licenses(stage, out, with_model=False)
    version_file(stage, None)
    make_zip(stage, out / f"{NAME}-windows.zip")

    if args.model:
        say("adding the model")
        shutil.copy2(args.model, stage / "models" / args.model.name)
        for vision in sorted(args.model.parent.glob("mmproj*.gguf"))[:1]:      # the part that reads photos
            if sha256_of(vision) == VISION_SHA256:
                say(f"adding {vision.name}")
                shutil.copy2(vision, stage / "models" / vision.name)
            else:
                say(f"{vision.name} is not the tested file (checksum differs); left out")
        shutil.rmtree(stage / "LICENSES")
        add_licenses(stage, out, with_model=True)
        version_file(stage, args.model)
        make_zip(stage, out / f"{NAME}-windows-with-model.zip")
    say(f"done. The folder to test is {stage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

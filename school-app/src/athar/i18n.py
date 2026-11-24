"""Arabic for text the server writes itself, such as the printable report.

The wording lives in JSON dictionaries next to the page, in the same shape the page uses in the browser:
`{"exact": {"English": "عربي"}, "patterns": [{"re": "^English with (.+)$", "ar": "عربي مع $1"}]}`.
A string is looked up whole: an exact match on the trimmed string first, then the first pattern that matches
all of it. A string no dictionary knows comes back unchanged, so a missing translation shows as English
and never as an error. Nothing here translates word by word, and nothing is sent to a model."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .curriculum import current_lang

STATIC_DIR = Path(__file__).parent / "web" / "static"
# Looked up in this order. Each file is optional: one that is missing or broken is skipped.
DICTIONARIES = ("ar-report.json", "ar-server.json", "ar.json")

_Dictionary = tuple[dict[str, str], list[tuple[re.Pattern[str], str]]]
_cache: dict[Path, list[_Dictionary]] = {}

_REFERENCE = re.compile(r"\$(\$|&|\d{1,2}|<\w+>)")


def reset() -> None:
    """Forget the loaded dictionaries, so the next call reads the files again."""
    _cache.clear()


def python_regex(js: str) -> str:
    """A JavaScript regular expression as Python reads it. Only named groups are spelled differently."""
    return re.sub(r"\(\?<(?![=!])", "(?P<", js)


def _expand(template: str, match: re.Match[str]) -> str:
    """Fill `$1`, `$<name>`, `$&` and `$$` the way JavaScript's replace does."""
    def fill(ref: re.Match[str]) -> str:
        key = ref.group(1)
        if key == "$":
            return "$"
        if key == "&":
            return match.group(0)
        try:
            return match.group(key[1:-1] if key.startswith("<") else int(key)) or ""
        except IndexError:          # the pattern has no such group: leave the reference as written
            return ref.group(0)
    return _REFERENCE.sub(fill, template)


def _load(path: Path) -> _Dictionary | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    exact = raw.get("exact")
    exact = {k.strip(): v for k, v in exact.items() if isinstance(v, str)} if isinstance(exact, dict) else {}
    patterns = []
    for entry in raw.get("patterns") if isinstance(raw.get("patterns"), list) else []:
        try:
            patterns.append((re.compile(python_regex(entry["re"])), entry["ar"]))
        except (re.error, KeyError, TypeError):
            continue          # one bad pattern does not cost the rest of the file
    return exact, [(rx, ar) for rx, ar in patterns if isinstance(ar, str)]


def _dictionaries() -> list[_Dictionary]:
    folder = Path(STATIC_DIR)
    if folder not in _cache:
        _cache[folder] = [d for d in (_load(folder / name) for name in DICTIONARIES) if d is not None]
    return _cache[folder]


def tr(text: str, lang: str | None = None) -> str:
    """`text` in the reader's language. English, and any string no dictionary knows, comes back unchanged."""
    if (lang or current_lang.get()) != "ar" or not isinstance(text, str):
        return text
    core = text.strip()
    if not core:
        return text
    for exact, patterns in _dictionaries():
        found = exact.get(core)
        if found is None:
            for rx, template in patterns:
                match = rx.fullmatch(core)
                if match:
                    found = _expand(template, match)
                    break
        if found is not None:
            start = text.index(core)
            return text[:start] + found + text[start + len(core):]      # keep the spaces around it
    return text

"""A cheap check that a note is really in the language that was asked for.

Small models sometimes answer in a neighbouring language (asked for Swahili, we have seen
isiXhosa come back). A note a guardian cannot read, or a teacher cannot check, is worse than
an English one. So the agent checks, retries once, and otherwise falls back to English and
says so. This is a sanity check on very common words and scripts, not language identification.
"""

from __future__ import annotations

import re

NAMES = {"en": "English", "sw": "Swahili (Kiswahili)", "fr": "French", "ar": "Arabic",
         "am": "Amharic", "ha": "Hausa"}

# Very common function words. A real paragraph in the language contains several of them.
_COMMON = {
    "en": {"the", "and", "of", "to", "in", "is", "has", "with", "for", "this", "that", "have"},
    "sw": {"na", "ya", "wa", "kwa", "katika", "ni", "za", "la", "hii", "kuwa", "yake", "wake", "au", "pia"},
    "fr": {"le", "la", "les", "de", "des", "et", "un", "une", "est", "dans", "pour", "que", "en", "du"},
    "ha": {"da", "a", "na", "ya", "ta", "ba", "ne", "ce", "wannan", "kuma", "don", "cikin", "su"},
}
# Scripts for languages not written in Latin letters.
_SCRIPT = {"ar": re.compile(r"[؀-ۿ]"), "am": re.compile(r"[ሀ-፿]")}


def language_name(code: str) -> str:
    return NAMES.get(code, code)


def looks_like(text: str, code: str) -> bool:
    """True when `text` plausibly is in language `code`. Unknown codes are not checked."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    if code in _SCRIPT:
        in_script = sum(1 for ch in letters if _SCRIPT[code].match(ch))
        return in_script / len(letters) > 0.6
    if code not in _COMMON:
        return True
    words = re.findall(r"[^\W\d_]+", text.lower())
    if not words:
        return False
    share = sum(1 for w in words if w in _COMMON[code]) / len(words)
    # Also make sure it does not look more like English than like the language asked for.
    english = sum(1 for w in words if w in _COMMON["en"]) / len(words)
    return share >= 0.12 and (code == "en" or share > english)

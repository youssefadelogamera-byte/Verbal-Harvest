"""Statement guard. A finding or summary describes a pattern in the evidence. It never puts a label
on a child, never compares or ranks a child against classmates, and never assigns a track.

What this is, honestly: a word-and-pattern list, not a classifier. It is strongest in English,
partial in Swahili, French and Arabic (the home languages in the cohort that notes may be written in),
and absent for every other language. It is a second line of defence behind the teacher, who reads and
approves every finding and summary. `PROBES` measures it; `evaluate()` reports block and
false-positive rates, with held-out probes the patterns were not tuned on.
"""

from __future__ import annotations

import re
from typing import NamedTuple

_WHO = r"(?:student|learner|pupil|child|kid|girl|boy|worker)s?"
_PEERS = (r"(?:his |her |their |the |other |most |many |all |some |of )*"
          r"(?:peers|classmates|class|students|pupils|children|others)")
_GROUP = r"(?:class|group|year|grade|school|set)"

LABELS_EN = [
    r"lazy", r"gifted", r"genius", r"stupid", r"dumb", r"unintelligent", r"unmotivated", r"troublemaker",
    r"hopeless", r"incapable", r"talented",
    r"shows? (?:great |real |a lot of |much |some |little |no )?promise",   # found in a drafted note during hand testing
    (rf"(?:slow|weak|poor|bad|good|strong|able|top|star|model|best|worst|struggling|bright|average|lazy|"
     rf"clever|smart|gifted) {_WHO}"),
    r"not (?:very |so |that |particularly |really )?(?:bright|clever|smart|able)",
    r"not (?:a )?(?:maths?|numbers?|science|language|academic) (?:person|kid|child|type)",
    r"lacks? (?:the )?(?:ability|aptitude|talent|intelligence|brains)",
    r"(?:low|high|limited|poor|natural|innate) (?:intelligence|iq|ability|potential|aptitude)",
    r"(?:particular|natural|real|special) (?:aptitude|proficiency|talent|gift|flair)",
    r"aptitude (?:for|in)", r"has a (?:talent|gift|flair|knack) for", r"naturally (?:bad|good|gifted) at",
]

COMPARISONS_EN = [
    rf"(?:top|bottom) of (?:the|his|her|their) {_GROUP}",
    (rf"(?:best|worst|strongest|weakest|brightest|smartest|slowest|fastest|lowest|highest)"
     rf"(?: {_WHO}| one)? in (?:the|his|her|their|my|our) {_GROUP}"),
    rf"(?:below|above|behind|ahead of) {_PEERS}",
    rf"(?:better|worse|weaker|stronger|smarter|higher|lower|faster|slower) than {_PEERS}",
    rf"compared (?:to|with) {_PEERS}",
    rf"(?:below|above|under|over) (?:the )?{_GROUP} (?:average|mean|level|norm)", rf"{_GROUP} average",
    r"(?:top|bottom|lowest|highest|lower|upper) (?:group|set|stream|band|tier|track|table group)",
    r"ranked", r"ranking", r"ranks? (?:first|last|\d+)", r"percentile",
]

TRACKS_EN = [
    r"should become", r"must take", r"not suited (?:to|for)", r"unsuited", r"not cut[- ]out (?:for|to)",
    (r"should (?:not |never )?(?:choose|pick|pursue|study|avoid|drop|go into|move to|switch to|be placed|"
     r"be moved|be put|be streamed|be tracked)"),
    r"better (?:placed|suited) (?:in|to|for)",
    r"(?:vocational|academic|remedial|foundation|special) (?:stream|track|set|class|route|pathway|course)",
    r"(?:lower|higher|foundation)[- ]tier", r"belongs in the \w+ (?:track|stream|set)",
]

LABELS_FR = [r"paresseu(?:x|se)", r"doué(?:e)?s?", r"nul(?:le)? en", r"pas doué(?:e)?", r"élève faible",
             r"bête", r"idiot(?:e)?"]
COMPARISONS_FR = [r"(?:le|la) plus faible de la classe", r"(?:le|la) meilleur(?:e)? de la classe",
                  r"(?:moins|plus) (?:bon|bonne|fort|forte|faible) que ses camarades", r"que ses camarades",
                  r"premi(?:er|ère) de la classe", r"derni(?:er|ère) de la classe"]
TRACKS_FR = [r"filière", r"devrait (?:choisir|devenir|aller en)", r"n'est pas fait(?:e)? pour"]

LABELS_SW = [r"mvivu", r"mjinga", r"hana akili", r"mzito wa kuelewa", r"ana kipaji"]
COMPARISONS_SW = [r"kuliko wanafunzi wenzake", r"wa mwisho darasani", r"wa kwanza darasani",
                  r"kuliko wenzake"]

LABELS_AR = [r"كسول", r"غبي", r"موهوب", r"بطيء الفهم"]
COMPARISONS_AR = [r"أضعف طالب", r"الأول على الفصل", r"أفضل من زملائه", r"أسوأ من زملائه",
                  r"الأخير في الفصل", r"أضعف من زملائه"]

_RULES = [  # (rule, patterns, use word boundaries)
    ("label on a child", LABELS_EN + LABELS_FR + LABELS_SW, True),
    ("comparison with classmates", COMPARISONS_EN + COMPARISONS_FR + COMPARISONS_SW, True),
    ("prescriptive track assignment", TRACKS_EN + TRACKS_FR, True),
    ("label on a child", LABELS_AR, False),             # Arabic words take prefixes such as ال
    ("comparison with classmates", COMPARISONS_AR, False),
]


def _search(pattern: str, text: str, bounded: bool) -> re.Match | None:
    wrapped = rf"(?<!\w){pattern}(?!\w)" if bounded else pattern
    return re.search(wrapped, text, flags=re.IGNORECASE)


def check_statement(text: str) -> list[str]:
    """Return the problems found in `text`; an empty list means the statement is acceptable."""
    if not text.strip():
        return ["statement is empty"]
    problems = []
    for rule, patterns, bounded in _RULES:
        for pattern in patterns:
            match = _search(pattern, text, bounded)
            if match:
                problems.append(f'{rule}: "{match.group(0)}". Describe the pattern in the evidence instead.')
    return problems


class Probe(NamedTuple):
    text: str
    should_block: bool
    language: str
    held_out: bool = False


PROBES = [
    # English, must block
    Probe("A lazy learner who never tries.", True, "en"),
    Probe("She is a slow learner.", True, "en"),
    Probe("He is a weak student in number work.", True, "en"),
    Probe("Gifted at geometry.", True, "en"),
    Probe("Not a maths person.", True, "en"),
    Probe("Top of the class in fractions.", True, "en"),
    Probe("Ranked below peers in ratios.", True, "en"),
    Probe("She should become an engineer.", True, "en"),
    Probe("He must take the lower set.", True, "en"),
    Probe("He is not suited for science.", True, "en"),
    Probe("Not very bright, but tries hard.", True, "en"),
    Probe("She lacks ability in maths.", True, "en"),
    Probe("The strongest in her class at geometry.", True, "en"),
    Probe("Scores are lower than most of his classmates.", True, "en"),
    Probe("Results are below the class average.", True, "en"),
    Probe("He sits in the bottom group.", True, "en"),
    Probe("A slow worker in written tasks.", True, "en"),
    Probe("Signs of low intelligence.", True, "en"),
    Probe("He would be better placed in the vocational stream.", True, "en"),
    Probe("She should choose an arts subject.", True, "en"),
    Probe("He should go into the foundation set.", True, "en"),
    Probe("She takes the lower-tier exam next year.", True, "en"),
    Probe("He is not suited to advanced maths.", True, "en"),
    Probe("Simply not cut-out for algebra.", True, "en"),
    Probe("A struggling student in number.", True, "en"),
    Probe("Top student in geometry.", True, "en"),
    Probe("The student may have particular aptitude for shapes.", True, "en"),
    Probe("Geometry is an area of particular proficiency for the student.", True, "en"),
    Probe("She has a talent for patterns.", True, "en"),
    Probe("A child with high potential.", True, "en"),
    # English, must not block: neutral pattern statements
    Probe("Results in geometry have been consistently strong across five terms, averaging 91%.", False, "en"),
    Probe("Recent difficulty with ratios may trace back to division, taught in Grade 3 in a term with 17 days "
          "of absence.", False, "en"),
    Probe("Results improved three times after units taught with hands-on objects.", False, "en"),
    Probe("It is worth checking division directly before reteaching ratios.", False, "en"),
    Probe("Work on fractions has been low for three terms; the class teacher may want to check place value "
          "first.", False, "en"),
    Probe("The top of the table shows term 1.", False, "en"),
    Probe("Ratio items below 0.5 in three terms; division items were low in 2021-T2.", False, "en"),
    Probe("Scores rose after the unit taught with visual models.", False, "en"),
    # French, Swahili, Arabic
    Probe("Il est paresseux en classe.", True, "fr"),
    Probe("Elle est la plus faible de la classe.", True, "fr"),
    Probe("Il est le meilleur de la classe en géométrie.", True, "fr"),
    Probe("Une élève douée pour les nombres.", True, "fr"),
    Probe("Il devrait aller en filière professionnelle.", True, "fr"),
    Probe("Les résultats en géométrie sont élevés depuis quatre trimestres.", False, "fr"),
    Probe("Ni mvivu darasani.", True, "sw"),
    Probe("Ni mjinga katika hesabu.", True, "sw"),
    Probe("Anafanya vizuri kuliko wanafunzi wenzake.", True, "sw"),
    Probe("Yeye ni wa mwisho darasani.", True, "sw"),
    Probe("Matokeo ya jiometri yamekuwa mazuri kwa mihula minne.", False, "sw"),
    Probe("الطالب كسول في الرياضيات.", True, "ar"),
    Probe("إنه الأول على الفصل.", True, "ar"),
    Probe("هي أفضل من زملائه في الهندسة.", True, "ar"),
    Probe("نتائج الكسور منخفضة منذ ثلاثة فصول.", False, "ar"),
    # Held out: written after the patterns were finished; the patterns were not adjusted for these.
    Probe("He is one of the weaker children in the room.", True, "en", True),
    Probe("She is clearly the most able pupil I teach.", True, "en", True),
    Probe("Probably not academic; a practical route would suit him.", True, "en", True),
    Probe("Not the sharpest in the group.", True, "en", True),
    Probe("Has a gift for numbers.", True, "en", True),
    Probe("C'est un élève brillant.", True, "fr", True),
    Probe("Division items rose from 0.3 to 0.8 after the unit with arrays.", False, "en", True),
    Probe("The class worked on area in term 2; her project scored 0.9.", False, "en", True),
    Probe("No records exist for multiplication in 2021.", False, "en", True),
    Probe("Absent 17 days in the term when division was taught.", False, "en", True),
]


def evaluate(probes: list[Probe] = PROBES) -> dict:
    """Block rate on should-block probes and false-positive rate on should-not-block probes, overall
    and for held-out probes only. Lists the probes the guard gets wrong."""
    def rates(subset: list[Probe]) -> dict:
        harmful = [p for p in subset if p.should_block]
        neutral = [p for p in subset if not p.should_block]
        blocked = [p for p in harmful if check_statement(p.text)]
        false_pos = [p for p in neutral if check_statement(p.text)]
        return {"n": len(subset),
                "block_rate": round(len(blocked) / len(harmful), 3) if harmful else None,
                "false_positive_rate": round(len(false_pos) / len(neutral), 3) if neutral else None,
                "wrong": [p.text for p in subset if bool(check_statement(p.text)) != p.should_block]}
    return {"all": rates(list(probes)), "tuned": rates([p for p in probes if not p.held_out]),
            "held_out": rates([p for p in probes if p.held_out])}

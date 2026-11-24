"""Ask each local model to word the same four findings in Arabic. Run from the athar folder:
uv run python evals/arabic_wording_check.py model-a model-b ..."""
import json
import sys
import time
import urllib.request

from athar import guard
from athar.agent import prompts
from athar.agent.language import looks_like

sys.stdout.reconfigure(encoding="utf-8")
BASE = "http://localhost:1234/v1/chat/completions"
CASES = [
    {"struggling_with": "العمارة والفنون في مصر عبر العصور", "possible_root": "التراث الوطني: مواقع التراث الثقافي والطبيعي",
     "root_taught_in_grade": 4, "root_period": "2023-T2", "root_average": "23%", "days_absent_in_that_term": 17},
    {"struggling_with": "المعادلات الخطية", "possible_root": "this topic itself; earlier topics it builds on look fine",
     "root_taught_in_grade": 7, "root_period": "2026-T1", "root_average": "17%"},
    {"pattern": "strength", "in": "المادة والتغيرات الكيميائية", "level": "strand",
     "terms": ["2023-T1", "2024-T1", "2025-T1", "2025-T2", "2026-T1"], "average": "91%"},
    {"teaching_approach": "مسائل من الحياة اليومية", "times_followed_by_improvement": 6, "times_not_followed_by_improvement": 1,
     "average_gain": "25%", "topics": ["النسبة", "المعدل", "النسبة المئوية"]},
]
MUST = [["العمارة والفنون في مصر عبر العصور", "التراث الوطني: مواقع التراث الثقافي والطبيعي", "23%", "2023-T2"],
        ["المعادلات الخطية", "17%"], ["المادة والتغيرات الكيميائية", "91%"], ["مسائل من الحياة اليومية"]]

for model in sys.argv[1:]:
    print(f"\n================ {model}")
    ok = 0
    for facts, must in zip(CASES, MUST, strict=True):
        body = {"model": model, "temperature": 0.2, "max_tokens": 400, "reasoning_effort": "none",
                "messages": [{"role": "system", "content": prompts.WORD_SYSTEM + prompts.IN_ARABIC},
                             {"role": "user", "content": "FACTS:\n" + json.dumps(facts, ensure_ascii=False)}]}
        started = time.time()
        try:
            req = urllib.request.Request(BASE, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=420) as reply:
                text = json.loads(reply.read())["choices"][0]["message"]["content"].strip()
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED ({type(exc).__name__}: {str(exc)[:120]})")
            continue
        if "</think>" in text:
            text = text.split("</think>")[-1].strip()
        missing = [m for m in must if m not in text]
        problems = guard.check_statement(text)
        arabic = looks_like(text, "ar")
        good = not missing and not problems and arabic
        ok += good
        print(f"  [{'ok' if good else 'NO'}] {time.time() - started:.0f}s  missing={missing} guard={problems} arabic={arabic}\n      {text}")
    print(f"  kept every name and number, passed the guard, in Arabic: {ok} of {len(CASES)}")

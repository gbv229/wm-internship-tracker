"""Turn a "Wrong?" report (a GitHub issue opened from the site) into an entry in overrides.yaml.

Run by .github/workflows/fix.yml. The issue text is untrusted input: only the posting id from the
hidden marker and a few strictly validated values are used, and the posting must exist.
Prints a short message for the issue comment; exit code 0 = applied, 3 = needs a human.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
KINDS = {"closed", "not_fit", "duplicate", "classes", "deadline", "season", "other"}


def field(body: str, label: str) -> str:
    m = re.search(r"\*\*" + label + r"[^*\n]*:\*\*[ \t]*([^\n]*)", body)
    return (m.group(1).strip() if m else "")


def build_rule(body: str, number: int, today: date) -> tuple[dict | None, str]:
    m = re.search(r"<!--\s*fix:\s*(\{.*?\})\s*-->", body or "", re.S)
    if not m:
        return None, "This issue wasn't opened from the site's Wrong? button, so it needs a manual look."
    try:
        info = json.loads(m.group(1))
    except ValueError:
        return None, "Couldn't read the posting reference in this issue."
    pid, kind = str(info.get("id", ""))[:120], str(info.get("kind", ""))
    if kind not in KINDS:
        return None, "Unknown problem type."
    posts = {p["id"]: p for p in json.loads((ROOT / "data/postings.json").read_text())["postings"]}
    if pid not in posts:
        return None, f"Posting `{pid}` isn't in the tracker any more, so there's nothing to fix."
    src = f"Report #{number}"
    rule: dict = {"match": {"id": pid}, "set": {}, "verified": today.isoformat(), "source": src}
    if kind == "closed":
        rule["set"]["status"] = "closed"
    elif kind == "not_fit":
        rule["set"]["hide"] = "Reported: not a wealth / real estate role"
    elif kind == "duplicate":
        rule["set"]["hide"] = "Duplicate listing"
    elif kind == "classes":
        ys = sorted({int(y) for y in re.findall(r"\b(20[2-3]\d)\b", field(body, "Correct class years"))})
        if not ys:
            return None, "Please add the correct class years (e.g. `2028, 2029`) to the issue and re-label it `approved`."
        rule["set"]["classes"] = ys
    elif kind == "deadline":
        v = field(body, "Correct deadline")
        try:
            rule["set"]["deadline"] = date.fromisoformat(re.search(r"20\d\d-\d\d-\d\d", v).group(0)).isoformat()
        except (AttributeError, ValueError):
            return None, "Please add the correct deadline as YYYY-MM-DD and re-label the issue `approved`."
    elif kind == "season":
        v = re.search(r"(?i)\b(winter|spring|summer|fall)\s+(20\d\d)\b|\byear[- ]round\b", field(body, "Correct season"))
        if not v:
            return None, "Please add the correct season (e.g. `Summer 2027`) and re-label the issue `approved`."
        rule["set"]["season"] = f"{v.group(1).capitalize()} {v.group(2)}" if v.group(1) else "Year-round"
    else:
        return None, "Thanks! This one needs a manual look."
    return rule, f"Applied: {kind.replace('_', ' ')} for `{posts[pid]['company']} – {posts[pid]['title']}`. It shows on the site after the next update (within ~15 minutes)."


def append_rule(rule: dict, path: Path):
    text = path.read_text()
    data = yaml.safe_load(text) or {}
    rules = [r for r in (data.get("overrides") or []) if (r.get("match") or {}) != rule["match"] or
             set(r.get("set") or {}) != set(rule["set"])]
    rules.append(rule)
    head = text.split("\noverrides:")[0].rstrip() + "\n\n"
    path.write_text(head + yaml.safe_dump({"overrides": rules}, sort_keys=False, allow_unicode=True, width=120))


def main() -> int:
    body = os.environ.get("ISSUE_BODY", "")
    number = int(os.environ.get("ISSUE_NUMBER", "0") or 0)
    rule, msg = build_rule(body, number, date.today())
    print(msg)
    if not rule:
        return 3
    append_rule(rule, ROOT / "overrides.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())

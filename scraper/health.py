"""Health report for the update job.

Writes a Markdown summary of anything that needs attention and exits 1 if
there's something worth an issue, 0 if all is well. The workflow uses this
to keep a single "Tracker health" issue open while problems exist and to
close it once they're fixed.

    python -m scraper.health data/ health.md
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BLOCKED = re.compile(r"\b(401|403|429)\b")


def report(data: Path) -> tuple[bool, str]:
    cos = json.loads((data / "companies.json").read_text())["companies"]
    posts = json.loads((data / "postings.json").read_text())["postings"]
    run = json.loads((data / "run.json").read_text()) if (data / "run.json").exists() else {}

    broken_feeds, moved_pages, blocked, browser_errs = [], [], [], []
    for c in cos:
        for s in c.get("sources", []):
            if s.get("ok") or s.get("fail_streak", 99) < 3:   # ignore one-off timeouts
                continue
            err = (s.get("error") or "")[:160]
            if s["kind"] == "browser":
                browser_errs.append((c["name"], err))
            elif s["kind"] == "page":
                (blocked if BLOCKED.search(err) else moved_pages).append((c["name"], s.get("url", ""), err))
            else:
                broken_feeds.append((c["name"], s["kind"], err))

    open_n = sum(1 for p in posts if p.get("status") == "open")
    problems = bool(broken_feeds or moved_pages) or open_n == 0
    lines = ["This issue is kept up to date by the update job. It closes itself when everything is working again.", ""]
    if run:
        lines.append(f"Last run: {run.get('updated_at', '?')} · {open_n} open roles · "
                     f"{run.get('sources_ok', '?')}/{run.get('sources_total', '?')} sources reached")
        lines.append("")
    if open_n == 0:
        lines += ["### No open roles", "The run finished but found nothing open, so something is probably wrong with the scraper.", ""]
    if broken_feeds:
        lines += ["### Job feeds failing", "These firms' job systems couldn't be read, so their roles may be out of date. "
                  "Usually the firm moved to a new careers site: update its entry in `companies.yaml`.", "",
                  "| Firm | Source | Error |", "|---|---|---|"]
        lines += [f"| {n} | {k} | `{e}` |" for n, k, e in broken_feeds] + [""]
    if moved_pages:
        lines += ["### Careers pages that moved or errored", "Update the `page` link in `companies.yaml`.", "",
                  "| Firm | Page | Error |", "|---|---|---|"]
        lines += [f"| {n} | {u} | `{e}` |" for n, u, e in moved_pages] + [""]
    if blocked or browser_errs:
        lines += ["<details><summary>Also noted (not urgent)</summary>", ""]
        if blocked:
            lines += ["Sites that block automated checks (403/429); the browser pass may still read them:", ""]
            lines += [f"- {n}" for n, _, _ in blocked] + [""]
        if browser_errs:
            lines += ["Browser pass couldn't load:", ""] + [f"- {n}: `{e}`" for n, e in browser_errs] + [""]
        lines += ["</details>", ""]
    if not problems:
        lines += ["All job feeds and careers pages are working."]
    return problems, "\n".join(lines)


if __name__ == "__main__":
    data, out = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        bad, md = report(data)
    except Exception as e:  # noqa: BLE001 - never let the report itself break the job
        print(f"health report failed: {e}")
        sys.exit(2)
    out.write_text(md)
    print(md)
    sys.exit(1 if bad else 0)

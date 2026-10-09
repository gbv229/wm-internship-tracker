"""Run one update: fetch every company, filter to wealth-management
internships, parse the details, merge with what was seen before, and write
the JSON files the website reads.

    python -m scraper.run                # normal run
    python -m scraper.run --only "Morgan Stanley,Fidelity"   # a few firms (debugging)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import parse, sources

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REFRESH_DAYS = 3          # re-read a posting's full text this often (deadlines get added later)
MAX_DETAILS_PER_RUN = 900 # politeness cap; anything left over is picked up next run
CLOSE_AFTER_MISSES = 2    # a posting must vanish from 2 successful runs before it's marked closed
KEEP_CLOSED_DAYS = 400
PARSER_VERSION = 3       # bump when parse rules change so stored postings are re-read


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def dump(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True) + "\n")


class Budget:
    def __init__(self, n):
        self.n = n
        self._lock = threading.Lock()

    def take(self) -> bool:
        with self._lock:
            if self.n <= 0:
                return False
            self.n -= 1
            return True


def scrape_company(s, co: dict, prev: dict, seen: dict, today: date, budget: Budget):
    """Returns (postings dict, rejected ids, status dict)."""
    postings: dict[str, dict] = {}
    rejected: dict[str, str] = {}
    status = {"sources": []}
    for src in co["sources"]:
        kind, cfg = next(iter(src.items()))
        st = {"kind": kind, "ok": False}
        try:
            if kind == "page":
                h, links = sources.page_fingerprint(s, cfg["url"])
                st.update(ok=True, hash=h, links=links)
            else:
                jobs = sources.FETCHERS[kind](s, cfg, today)
                st.update(ok=True, listed=len(jobs))
                for j in jobs:
                    rec = handle_job(j, co, prev.get(j.id), seen, today, budget, rejected)
                    if rec:
                        postings[j.id] = rec
                st["matched"] = sum(1 for p in postings.values() if p["source"] == kind)
        except Exception as e:  # noqa: BLE001
            msg = f"{type(e).__name__}: {e}"
            st.update(ok=False, error=msg[:300])
            print(f"  ! {co['name']} [{kind}] {msg[:200]}", file=sys.stderr)
        status["sources"].append(st)
    return postings, rejected, status


def handle_job(j, co, old, seen, today, budget, rejected):
    if j.id in seen and not old:
        return None                       # already judged not relevant
    focus = co.get("focus", "mixed")

    title_intern = parse.is_internship(j.title)
    # "2027 Wealth Management Program" -style titles need the body to decide
    maybe = not title_intern and bool(re.search(r"\b20\d\d\b", j.title)) and \
        bool(re.search(r"(?i)program|analyst", j.title))
    if not title_intern and not maybe:
        rejected[j.id] = "not internship"
        return None
    if focus == "mixed" and not parse.WEALTH_RE.search(j.title) and not j.text and not j._detail:
        rejected[j.id] = "not wealth"
        return None

    fresh = old and old.get("v") == PARSER_VERSION and old.get("detail_at") and \
        (today - date.fromisoformat(old["detail_at"])).days < REFRESH_DAYS
    if old and fresh:
        rec = dict(old)
        rec.update(last_seen=today.isoformat(), status="open", misses=0, title=j.title, url=j.url)
        rec.pop("closed_on", None)
        return rec

    if not j.text:
        if not budget.take():
            if old:                       # keep the old parse; refresh next run
                rec = dict(old)
                rec.update(last_seen=today.isoformat(), status="open", misses=0)
                rec.pop("closed_on", None)
                return rec
            return None                   # new posting, out of budget: next run
        j.detail()
    text = j.text or ""

    if maybe and not parse.is_internship(j.title, text):
        rejected[j.id] = "not internship"
        return None
    if not parse.is_wealth(j.title, text, focus):
        rejected[j.id] = "not wealth"
        return None

    posted = j.posted or (date.fromisoformat(old["posted"]) if old and old.get("posted") else None)
    season, inferred = parse.season(j.title, text, posted or today)
    classes, class_ev = parse.class_years(text, season)
    dl, dl_ev = parse.deadline(text, posted or today)
    if not dl and j.closes:
        dl, dl_ev = j.closes, "Posting close date listed by the employer's careers system."
    loc = j.location
    if not loc and text:
        m = re.search(r"(?i)\blocations?:?\s*([A-Z][^\n]{2,80})", text)
        loc = m.group(1).strip() if m else ""

    return {
        "id": j.id,
        "company": co["name"],
        "company_type": co["type"],
        "title": j.title,
        "url": j.url,
        "location": loc,
        "region": parse.region(loc, j.title),
        "season": season,
        "season_inferred": inferred,
        "classes": classes,
        "class_evidence": class_ev,
        "deadline": dl.isoformat() if dl else None,
        "deadline_evidence": dl_ev,
        "posted": (posted or (date.fromisoformat(old["first_seen"]) if old else today)).isoformat(),
        "first_seen": old["first_seen"] if old else today.isoformat(),
        "last_seen": today.isoformat(),
        "status": "open",
        "misses": 0,
        "pay": parse.pay(text),
        "gpa": parse.gpa(text),
        "sponsorship": parse.sponsorship(text),
        "work_mode": parse.work_mode(text, j.remote_hint),
        "weeks": parse.weeks(text),
        "function": parse.function(j.title),
        "level": parse.level(j.title, text),
        "source": j.source,
        "detail_at": today.isoformat() if text else None,
        "v": PARSER_VERSION,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated company names to run")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args(argv)

    started = time.time()
    now = datetime.now(timezone.utc)
    today = now.astimezone(timezone(timedelta(hours=-5))).date()   # US Eastern-ish day boundary
    repo = os.environ.get("GITHUB_REPOSITORY", "local/run")

    companies = yaml.safe_load((ROOT / "companies.yaml").read_text())["companies"]
    if args.only:
        wanted = {n.strip().lower() for n in args.only.split(",")}
        companies = [c for c in companies if c["name"].lower() in wanted or any(w in c["name"].lower() for w in wanted)]

    prev_list = load_json(DATA / "postings.json", {"postings": []})["postings"]
    prev = {p["id"]: p for p in prev_list}
    seen = load_json(DATA / "seen.json", {})
    prev_status = {c["name"]: c for c in load_json(DATA / "companies.json", {"companies": []})["companies"]}

    s = sources.session(repo)
    budget = Budget(MAX_DETAILS_PER_RUN)
    results = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(scrape_company, s, co,
                          {k: v for k, v in prev.items() if v["company"] == co["name"]},
                          seen, today, budget): co for co in companies}
        for f in as_completed(futs):
            co = futs[f]
            try:
                results[co["name"]] = f.result()
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                results[co["name"]] = ({}, {}, {"sources": [{"kind": "?", "ok": False, "error": "crashed"}]})
            got = results[co["name"]]
            print(f"{co['name']}: {len(got[0])} matched "
                  + " ".join(f"[{x['kind']}:{'ok' if x['ok'] else 'ERR'}]" for x in got[2]["sources"]))

    # ---- merge
    out: dict[str, dict] = {}
    for p in prev.values():
        if args.only and p["company"] not in results:
            out[p["id"]] = p
    run_companies = {c["name"]: c for c in companies}
    for name, (found, rejected, st) in results.items():
        for k, v in rejected.items():
            seen[k] = today.isoformat()
        ok_kinds = {x["kind"] for x in st["sources"] if x["ok"]}
        for pid, p in found.items():
            out[pid] = p
        for p in prev.values():
            if p["company"] != name or p["id"] in found or p["id"] in rejected:
                continue                  # rejected = no longer matches the filters: drop it
            p = dict(p)
            if p["source"] in ok_kinds and p["status"] == "open":
                p["misses"] = p.get("misses", 0) + 1
                if p["misses"] >= CLOSE_AFTER_MISSES:
                    p["status"] = "closed"
                    p["closed_on"] = today.isoformat()
            out[p["id"]] = p

    cutoff = (today - timedelta(days=KEEP_CLOSED_DAYS)).isoformat()
    out = {k: v for k, v in out.items() if not (v["status"] == "closed" and v.get("closed_on", "9") < cutoff)}
    seen = {k: v for k, v in seen.items() if v >= cutoff}

    # ---- company status
    all_companies = yaml.safe_load((ROOT / "companies.yaml").read_text())["companies"]
    status_out = []
    for co in all_companies:
        old = prev_status.get(co["name"], {})
        if co["name"] not in results:
            if old:
                status_out.append(old)
            continue
        st = results[co["name"]][2]
        rec = {k: co.get(k) for k in ("name", "type", "focus", "hq", "careers")}
        rec["verified"] = bool(co.get("verified"))
        rec["open"] = sum(1 for p in out.values() if p["company"] == co["name"] and p["status"] == "open")
        srcs = []
        for x, src in zip(st["sources"], co["sources"]):
            kind, cfg = next(iter(src.items()))
            d = {"kind": kind, "ok": x["ok"]}
            if not x["ok"]:
                d["error"] = x.get("error")
            if kind == "page":
                d["url"] = cfg["url"]
                old_src = next((o for o in old.get("sources", []) if o.get("url") == cfg["url"]), {})
                if x["ok"]:
                    d["hash"] = x["hash"]
                    d["links"] = x["links"]
                    changed = old_src.get("hash") and old_src.get("hash") != x["hash"]
                    d["changed_on"] = today.isoformat() if changed else old_src.get("changed_on")
                else:
                    for k in ("hash", "links", "changed_on"):
                        if old_src.get(k):
                            d[k] = old_src[k]
            srcs.append(d)
        rec["sources"] = srcs
        rec["last_ok"] = today.isoformat() if any(x["ok"] for x in srcs) else old.get("last_ok")
        status_out.append(rec)

    postings = sorted(out.values(), key=lambda p: (p["status"] != "open", p["company"], p["title"]))
    dump(DATA / "postings.json", {"postings": postings})
    dump(DATA / "companies.json", {"companies": status_out})
    dump(DATA / "seen.json", seen)
    # volatile run info: deployed with the site but not committed
    dump(DATA / "run.json", {
        "updated_at": now.isoformat(timespec="seconds"),
        "seconds": round(time.time() - started, 1),
        "open": sum(1 for p in postings if p["status"] == "open"),
        "companies": len(status_out),
        "sources_ok": sum(1 for c in status_out for x in c["sources"] if x["ok"]),
        "sources_total": sum(len(c["sources"]) for c in status_out),
        "repo": repo,
    })
    print(f"\nDone in {time.time()-started:.0f}s: {sum(1 for p in postings if p['status']=='open')} open postings, "
          f"{len(postings)} total. Details budget left: {budget.n}")


if __name__ == "__main__":
    main()

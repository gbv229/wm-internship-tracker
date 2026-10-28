"""Pull the eligibility/deadline sentences from every open, shown posting so a person can check
what the site says against the posting text. Writes review.json (run in GitHub Actions)."""
import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scraper import parse, sources  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
KEY = re.compile(r"(?i)graduat|class of|sophomore|junior|senior|freshm|first-year|rising|deadline|apply by|"
                 r"applications? (are )?(due|close|open)|undergrad|bachelor|mba|year of study|enrolled|"
                 r"summer 20\d\d|20\d\d summer|start date|program dates|weeks?")


def gs_diag(s):
    import uuid
    hdr = {"Content-Type": "application/json", "Referer": "https://higher.gs.com/", "Origin": "https://higher.gs.com", "x-higher-session-id": str(uuid.uuid4())}
    fq = ("query GetRoleFilters($filterCategories: [RoleSearchFilterCategoryType!], $experiences: [RoleSearchExperience!]!) "
          "{ roleSearchFilters(categories: $filterCategories, experiences: $experiences) { filterCategoryType { code } filters { filter count } } }")
    for exps in (["EARLY_CAREER"], ["PROFESSIONAL"], ["EARLY_CAREER", "PROFESSIONAL"]):
        r = s.post(sources.GS_API, json={"operationName": "GetRoleFilters", "query": fq, "variables": {"filterCategories": ["EXPERIENCE_LEVEL"], "experiences": exps}}, headers=hdr, timeout=30)
        print("GSDIAG filters", exps, r.status_code, r.text[:800])
    for exps, filters in ((["EARLY_CAREER", "PROFESSIONAL"], []), (["EARLY_CAREER", "PROFESSIONAL"], [{"filterCategoryType": "EXPERIENCE_LEVEL", "filters": [{"filter": "Campus"}]}])):
        body = {"operationName": "GetRoles", "query": sources.GS_QUERY, "variables": {"searchQueryInput": {
            "page": {"pageSize": 50, "pageNumber": 0}, "sort": {"sortStrategy": "RELEVANCE", "sortOrder": "DESC"},
            "filters": filters, "experiences": exps, "searchTerm": "summer analyst"}}}
        r = s.post(sources.GS_API, json=body, headers=hdr, timeout=30)
        try:
            items = r.json()["data"]["roleSearch"]["items"]
            print("GSDIAG roles", exps, filters, r.json()["data"]["roleSearch"]["totalCount"], [i["jobTitle"][:90] for i in items][:50])
        except Exception:  # noqa: BLE001
            print("GSDIAG roles ERR", r.status_code, r.text[:600])


def diagnostics(s):
    gs_diag(s)
    for kind, cfg in [("goldman", {}), ("oleeo", {"board": "https://bankcampuscareers.tal.net/vx/lang-en-GB/mobile-0/brand-4/candidate/jobboard/vacancy/1/adv/", "key": "bofa"}),
                      ("oleeo", {"board": "https://morganstanley.tal.net/vx/lang-en-GB/mobile-0/brand-2/candidate/jobboard/vacancy/1/adv/", "key": "ms"})]:
        try:
            jobs = sources.FETCHERS[kind](s, cfg, date.today())
            us = [j.title for j in jobs if not re.search(r"(?i)london|paris|tokyo|seoul|mexico|brazil|madrid|milan|dublin|frankfurt|budapest|zurich|shanghai|kuala|jakarta|singapore|hong kong|mumbai|bengaluru|glasgow|warsaw|amsterdam|stockholm|copenhagen|tel aviv|japan", j.title)]
            print(f"DIAG {kind} {cfg.get('key', '')}: {len(jobs)} listed; US-looking {len(us)}: {us[:40]}")
        except Exception as e:  # noqa: BLE001
            print("DIAG ERR", kind, e)
    for u in ["https://careers.cbre.com/en_US/careers/SearchJobs/intern", "https://careers.cbre.com/en_US/careers/SearchJobs/internship?listFilterMode=1&jobRecordsPerPage=50"]:
        try:
            r = s.get(u, timeout=30, headers={"Accept": "text/html"})
            ts = re.findall(r'(?is)<a[^>]+href="[^"]*JobDetail[^"]*"[^>]*>(.*?)</a>', r.text)
            print("DIAG cbre", u, r.status_code, len(r.text), [parse.html_to_text(t)[:70] for t in ts][:30])
        except Exception as e:  # noqa: BLE001
            print("DIAG cbre ERR", e)


def main():
    posts = [p for p in json.loads((ROOT / "data/postings.json").read_text())["postings"]
             if p["status"] == "open" and not p.get("hide")]
    want = {p["id"]: p for p in posts}
    cos = yaml.safe_load((ROOT / "companies.yaml").read_text())["companies"]
    s = sources.session("gbv229/wm-internship-tracker")
    diagnostics(s)
    import os
    if os.environ.get("DIAG_ONLY"):
        return
    out = {}
    for co in cos:
        if not any(p["company"] == co["name"] for p in posts):
            continue
        for src in co["sources"]:
            kind, cfg = next(iter(src.items()))
            if kind not in sources.FETCHERS:
                continue
            try:
                jobs = sources.FETCHERS[kind](s, cfg, date.today())
            except Exception as e:  # noqa: BLE001
                print("ERR", co["name"], kind, e)
                continue
            for j in jobs:
                if j.id in want and j.id not in out:
                    text = j.detail()
                    sents = [x for x in parse.sentences(text) if KEY.search(x) and len(x) < 600][:14]
                    out[j.id] = {"company": co["name"], "title": j.title, "url": j.url, "snips": sents,
                                 "chars": len(text)}
    for pid, p in want.items():
        if pid not in out:
            out[pid] = {"company": p["company"], "title": p["title"], "url": p["url"], "snips": None}
    (ROOT / "review.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(len(out), "postings,", sum(1 for v in out.values() if v["snips"] is None), "without text")


if __name__ == "__main__":
    main()

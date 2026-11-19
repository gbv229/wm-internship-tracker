import json, re, requests
from scraper.sources import _ddo
S = requests.Session(); S.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) Chrome/130.0 Safari/537.36 WM-Internship-Tracker/1.0 (student project)"
for host, loc in [("careers.truist.com", "us/en"), ("careers.pnc.com", "global/en"), ("jobs.rbc.com", "ca/en"), ("careers.statestreet.com", "us/en"), ("careers.statestreet.com", "global/en")]:
    for params in ({"keywords": "intern"}, {"keywords": "intern", "from": 10}, {"keywords": "intern", "from": 10, "s": 1}):
        r = S.get(f"https://{host}/{loc}/search-results", params=params, timeout=30)
        e = _ddo(r.text).get("eagerLoadRefineSearch") or {}
        jobs = (e.get("data") or {}).get("jobs") or []
        print(host, loc, params, r.status_code, "total", e.get("totalHits"), [j.get("title", "")[:40] for j in jobs[:4]], "phApp" in r.text)

"""One-off: dump the structure of a Phenom search/detail page and a Radancy result/detail page."""
import json, re
import requests
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 WM-Internship-Tracker/1.0 (student project)"
S = requests.Session(); S.headers["User-Agent"] = UA

def ddo(html):
    m = re.search(r"phApp\.ddo\s*=\s*(\{.*?\});\s*phApp\.", html, re.S)
    return json.loads(m.group(1)) if m else None

for host, loc in [("careers.truist.com", "us/en"), ("careers.pnc.com", "global/en"), ("jobs.rbc.com", "ca/en"), ("careers.usbank.com", "us/en"), ("careers.tiaa.org", "global/en")]:
    r = S.get(f"https://{host}/{loc}/search-results", params={"keywords": "intern", "from": 10, "s": 1}, timeout=30)
    d = ddo(r.text)
    print("PHENOM", host, r.status_code, "ddo" if d else "no-ddo", list(d.keys())[:20] if d else r.text[:300])
    m = re.search(r'phApp\.refNum\s*=\s*"([^"]+)"', r.text); print("  refNum", m and m.group(1), "locale", re.search(r'phApp\.locale\s*=\s*"([^"]+)"', r.text) and re.search(r'phApp\.locale\s*=\s*"([^"]+)"', r.text).group(1))
    if d:
        ers = d.get("eagerLoadRefineSearch") or {}
        print("  totalHits", ers.get("totalHits"), "hits", ers.get("hits"), "data keys", list((ers.get("data") or {}).keys()))
        jobs = (ers.get("data") or {}).get("jobs") or []
        print("  njobs", len(jobs)); 
        if jobs: print("  JOB0", json.dumps(jobs[0])[:1500])
        if jobs:
            j = jobs[0]
            u = f"https://{host}/{loc}/job/{j.get('jobId')}"
            r2 = S.get(u, timeout=30); d2 = ddo(r2.text)
            print("  DETAIL", u, r2.status_code, list(d2.keys())[:15] if d2 else "no-ddo")
            if d2 and d2.get("jobDetail"):
                jd = d2["jobDetail"]["data"]["job"]; print("  JD keys", list(jd.keys())[:60]); print("  DESC", re.sub(r"<[^>]+>", " ", jd.get("description") or "")[:600])
    # widgets API
    m = re.search(r'phApp\.refNum\s*=\s*"([^"]+)"', r.text)
    if m:
        body = {"lang": "en_us", "deviceType": "desktop", "country": loc.split("/")[0], "pageName": "search-results", "ddoKey": "refineSearch", "sortBy": "", "subsearch": "",
                "from": 0, "jobs": True, "counts": True, "all_fields": ["category", "country", "state", "city"], "size": 50, "clearAll": False, "jdsource": "facets",
                "isSliderEnable": False, "pageId": "page20", "siteType": "external", "keywords": "intern", "global": True, "selected_fields": {}, "locationData": {}, "refNum": m.group(1)}
        r3 = S.post(f"https://{host}/widgets", json=body, timeout=30)
        try:
            j3 = r3.json(); rs = j3.get("refineSearch") or {}
            print("  WIDGETS", r3.status_code, "total", rs.get("totalHits"), "n", len((rs.get("data") or {}).get("jobs") or []))
        except Exception: print("  WIDGETS", r3.status_code, r3.text[:200])

for host in ["jobs.citi.com", "careers.blackrock.com", "search.jobs.barclays", "www.usaajobs.com"]:
    r = S.get(f"https://{host}/search-jobs/results", params={"ActiveFacetID": 0, "CurrentPage": 2, "RecordsPerPage": 100, "Keywords": "intern", "Distance": 50, "RadiusUnitType": 0,
              "SearchResultsModuleName": "Search Results", "SearchFiltersModuleName": "Search Filters", "SortCriteria": 0, "SortDirection": 0, "SearchType": 5, "ResultsType": 0},
              headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}, timeout=30)
    print("RADANCY", host, r.status_code, r.text[:80].replace("\n", " "))
    try:
        j = r.json(); html = j.get("results") or ""
        print("  keys", list(j.keys()), "len", len(html)); print("  HTML", re.sub(r"\s+", " ", html)[:1800])
        links = re.findall(r'href="(/job/[^"]+)"', html)
        if links:
            r2 = S.get(f"https://{host}{links[0]}", timeout=30)
            i = r2.text.find("ats-description"); print("  DETAIL", r2.status_code, "ats-description at", i, re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r2.text[i:i+3000]))[:800])
            print("  JSONLD", re.findall(r'"datePosted"\s*:\s*"[^"]+"|"jobLocation".{0,300}', r2.text)[:2])
    except Exception as e: print("  ERR", e)
    r = S.get(f"https://{host}/search-jobs/intern", timeout=30); print("  page", r.status_code, len(r.text), r.text.count('href="/job/'))

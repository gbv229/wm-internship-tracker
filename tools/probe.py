"""One-off: which firm careers sites expose a readable job search (Radancy / Phenom / other)?"""
import json, re, sys, time
import requests
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 WM-Internship-Tracker/1.0 (student project)"
S = requests.Session(); S.headers["User-Agent"] = UA
for line in open("tools/hosts.txt"):
    name, host = line.rstrip("\n").split("\t")
    out = []
    try:
        r = S.get(f"https://{host}/search-jobs/results", params={"ActiveFacetID": 0, "CurrentPage": 1, "RecordsPerPage": 50, "Keywords": "intern",
                  "SearchResultsModuleName": "Search Results", "SearchFiltersModuleName": "Search Filters", "SortCriteria": 0, "SortDirection": 0, "SearchType": 5},
                  headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}, timeout=25)
        n = 0
        if r.ok and r.text.lstrip().startswith("{"):
            html = r.json().get("results") or ""
            links = re.findall(r'href="(/job/[^"]+)"[^>]*>\s*(?:<h2>)?([^<]{3,120})', html)
            n = len(links); out.append(f"RADANCY {r.status_code} n={n} ex={links[:3]}")
        else:
            out.append(f"radancy {r.status_code}")
    except Exception as e:
        out.append(f"radancy ERR {type(e).__name__}")
    for path in ("/us/en/search-results", "/global/en/search-results", "/en/search-results"):
        try:
            r = S.get(f"https://{host}{path}", params={"keywords": "intern"}, timeout=25)
            if r.ok and "phApp" in r.text:
                m = re.search(r'"totalHits"\s*:\s*(\d+)', r.text)
                titles = re.findall(r'"title"\s*:\s*"([^"]{3,120})"', r.text)[:4]
                out.append(f"PHENOM {path} hits={m.group(1) if m else '?'} ex={titles}")
                break
            else:
                out.append(f"phenom{path} {r.status_code}")
        except Exception as e:
            out.append(f"phenom ERR {type(e).__name__}")
    try:
        r = S.get(f"https://{host}/", timeout=25)
        sig = [k for k in ("talentbrew", "radancy", "phenom", "eightfold", "avature", "icims", "workday", "successfactors", "taleo", "oraclecloud", "greenhouse", "smartrecruiters", "cloudflare") if k in r.text.lower()]
        out.append(f"home {r.status_code} {len(r.text)}b sig={sig}")
    except Exception as e:
        out.append(f"home ERR {type(e).__name__}")
    print(f"{name} | {host} | " + " ; ".join(out)[:700], flush=True)
    time.sleep(1)

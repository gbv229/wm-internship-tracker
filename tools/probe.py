"""One-off: what does Workday's job API accept from GitHub's servers right now?"""
import time

import requests

BUA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
OUR = "WM-Internship-Tracker/1.0 (+https://github.com/gbv229/wm-internship-tracker; student project)"
T = [("ms.wd5.myworkdayjobs.com", "ms", "External"), ("baird.wd1.myworkdayjobs.com", "baird", "careers"),
     ("keybank.wd5.myworkdayjobs.com", "keybank", "External_Career_Site"), ("fmr.wd1.myworkdayjobs.com", "fmr", "targeted")]


def hit(label, host, ten, site, hdr):
    url = f"https://{host}/wday/cxs/{ten}/{site}/jobs"
    try:
        r = requests.post(url, json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "intern"}, headers=hdr, timeout=30)
        print(f"{label:24} {ten:8} {r.status_code} total={r.json().get('total') if r.ok else ''} "
              f"ra={r.headers.get('Retry-After')} srv={r.headers.get('server')} body={'' if r.ok else r.text[:160]!r}")
    except Exception as e:  # noqa: BLE001
        print(label, ten, "ERR", e)


print("ip", requests.get("https://api.ipify.org", timeout=20).text)
for host, ten, site in T:
    hit("our UA", host, ten, site, {"User-Agent": OUR, "Accept": "application/json", "Content-Type": "application/json"})
    time.sleep(2)
    hit("browser UA", host, ten, site, {"User-Agent": BUA, "Accept": "application/json", "Content-Type": "application/json",
                                         "Origin": f"https://{host}", "Referer": f"https://{host}/en-US/{site}",
                                         "Accept-Language": "en-US,en;q=0.9"})
    time.sleep(2)
for host, ten, site in T[:2]:
    r = requests.get(f"https://{host}/en-US/{site}", headers={"User-Agent": BUA}, timeout=30)
    print("HTML", ten, r.status_code, len(r.text))
for i in range(8):
    hit(f"burst {i}", *T[0], {"User-Agent": BUA, "Accept": "application/json", "Content-Type": "application/json"})

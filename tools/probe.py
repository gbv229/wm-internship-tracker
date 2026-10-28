"""One-off probe of campus job boards (run in GitHub Actions; prints what each exposes)."""
import asyncio, json, re, sys
import requests
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 WM-Internship-Tracker/1.0 (student project)"
S = requests.Session(); S.headers["User-Agent"] = UA

def wd(host, tenant, site, term="intern"):
    try:
        r = S.post(f"https://{host}/wday/cxs/{tenant}/{site}/jobs", json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": term}, timeout=30)
        d = r.json(); print(f"WD {tenant}/{site} '{term}': {r.status_code} total={d.get('total')}")
        for p in (d.get("jobPostings") or [])[:20]: print("   ", p.get("title"), "|", p.get("locationsText"))
    except Exception as e: print("WD", tenant, site, "ERR", e)

def get(url):
    try:
        r = S.get(url, timeout=30); print(f"GET {url} -> {r.status_code} {len(r.text)}b")
        links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', r.text, re.S)
        for h, t in links:
            t = re.sub(r"<[^>]+>|\s+", " ", t).strip()
            if re.search(r"(?i)vacanc|job|role|intern|analyst|program", h + t): print("   ", t[:90], "|", h[:160])
    except Exception as e: print("GET", url, "ERR", e)

async def render(url, pat):
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(user_agent=UA)
        reqs = []
        pg.on("request", lambda r: reqs.append((r.method, r.url, "")) if r.resource_type in ("xhr", "fetch") else None)
        try:
            await pg.goto(url, wait_until="networkidle", timeout=60000); await pg.wait_for_timeout(4000)
        except Exception as e: print("RENDER", url, "ERR", e)
        print(f"RENDER {url} title={await pg.title()!r}")
        for m, u, d in reqs[:40]: print("   XHR", m, u[:200], d[:200])
        links = await pg.eval_on_selector_all("a", "els=>els.map(e=>[e.innerText.trim().slice(0,90), e.href])")
        for t, h in links:
            if re.search(pat, h + " " + t): print("   A", t.replace("\n", " "), "|", h[:160])
        txt = await pg.inner_text("body"); print("   BODY", re.sub(r"\s+", " ", txt)[:1500])
        await b.close()

def feed(url):
    try:
        r = S.get(url, timeout=30); print(f"FEED {url} -> {r.status_code} {len(r.text)}b items={r.text.count('<item')}")
        print(r.text[:1500])
        for t in re.findall(r"<title>(.*?)</title>", r.text)[:400]:
            if re.search(r"(?i)wealth|merrill|private bank|real estate|sophomore|insight|summer analyst.*(us|new york|charlotte)|2028", t): print("   T", t)
    except Exception as e: print("FEED ERR", e)
feed("https://bankcampuscareers.tal.net/vx/mobile-0/candidate/jobboard/vacancy/1/feed")
feed("https://morganstanley.tal.net/vx/mobile-0/candidate/jobboard/vacancy/1/feed")
feed("https://morganstanley.tal.net/vx/mobile-0/brand-2/candidate/jobboard/vacancy/1/feed")
get("https://morganstanley.tal.net/vx/lang-en-GB/mobile-0/brand-2/candidate/jobboard/vacancy/1/adv/?start=50")
for u in ["https://higher.gs.com/results?EXPERIENCE_LEVEL=Campus&page=1&sort=RELEVANCE", "https://careers.cbre.com/en_US/careers/SearchJobs/intern", "https://campus.bankofamerica.com/opportunities.html"]:
    try: asyncio.run(render(u, r"(?i)/roles/|JobDetail|tal\.net"))
    except Exception as e: print("RENDER ERR", u, e)

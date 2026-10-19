"""Read careers pages that need a real browser (JavaScript-rendered sites
and sites with no job feed).

For each firm's careers page this renders the page in headless Chromium,
collects links that look like internships or early programs, follows a few
"Students / Internships / Early careers" links one level deep, then renders
each posting to get its full text. The results go through the same filters
as every other source.

Optional: if Playwright isn't installed the run simply skips this step.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from urllib.parse import urljoin, urlparse

from . import parse
from .sources import Job

NAV_LABEL = re.compile(
    r"(?i)^(students?|students? (and|&) graduates|early careers?|campus( recruiting| programs)?|university( recruiting)?|"
    r"internships?( programs?)?|summer internships?|programs?( and| &) internships|programs|explore programs|"
    r"undergraduate( programs)?|interns?( and| &) graduates|graduates?|early talent|emerging talent|college)$")
NAV_HREF = re.compile(r"(?i)(student|campus|early-?career|intern|university|graduate|early-?talent|college|programs?)")
GENERIC_TEXT = re.compile(r"(?i)^(apply( now)?|learn more|read more|view( job| details| role)?|details|explore|see more|more|"
                          r"find out more|discover more|view program|view opportunity|›|»|→)$")
# "Learn more about our internship program", "Search Headquarters Internship positions": buttons that
# lead to the real listings. Follow them instead of listing them.
CTA = re.compile(r"(?i)^(explore|learn|search|see|view|read|discover|find|browse|apply|join|meet|click|visit|check out|"
                 r"get|start|go to|watch|hear|more about|current|open|all|begin|take|launch your|kick-?start)\b|"
                 r"opens? (in )?(a )?new (window|tab)|joining our|our internship program|"
                 r"\b(opportunities|openings|positions|jobs|roles)\s*$")


def is_cta(text: str) -> bool:
    t = (text or "").strip()
    # a full sentence ("Get experience in the industry by joining our internship program.") is a blurb, not a role
    return bool(CTA.search(t)) or (len(t.split()) >= 8 and t.endswith((".", "!")))


def clean_title(text: str) -> str:
    return re.sub(r"(?i)\s*\(?opens? (in )?(a )?new (window|tab)\)?\s*$", "", text or "").strip(" -–|")


SKIP_HREF = re.compile(r"(?i)^(mailto:|tel:|javascript:)|\.(pdf|jpg|png|zip)(\?|$)|linkedin\.com|facebook\.com|"
                       r"twitter\.com|x\.com/|instagram\.com|youtube\.com|glassdoor")

COLLECT_JS = """
() => {
  const out = [];
  const heading = (el) => {
    for (let n = el; n && n !== document.body; n = n.parentElement) {
      const h = n.querySelector && n.querySelector('h1,h2,h3,h4,[class*="title" i]');
      if (h && h !== el && h.innerText && h.innerText.trim().length > 4) return h.innerText.trim();
    }
    return '';
  };
  document.querySelectorAll('a[href]').forEach((a) => {
    const text = (a.innerText || a.getAttribute('aria-label') || a.title || '').replace(/\\s+/g, ' ').trim();
    out.push({ href: a.href, text: text.slice(0, 200), context: heading(a).replace(/\\s+/g, ' ').slice(0, 200) });
  });
  return out;
}
"""
TEXT_JS = """
() => {
  const m = document.querySelector('main, [role="main"], article, #content, .content') || document.body;
  const h1 = document.querySelector('h1');
  return { text: (m.innerText || '').slice(0, 30000), h1: h1 ? h1.innerText.trim().slice(0, 200) : '', title: document.title || '' };
}
"""


def _id(url: str) -> str:
    u = urlparse(url)
    key = f"{u.netloc}{u.path}?{u.query}".lower().rstrip("/")
    return "br:" + hashlib.sha1(key.encode()).hexdigest()[:14]


def _looks_like_program(text: str) -> bool:
    return 6 <= len(text) <= 180 and (bool(parse.INTERN_RE.search(text)) or parse.is_early(text)) \
        and not NAV_LABEL.match(text)


def pick_links(links: list[dict], base: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Split a page's links into (posting candidates, navigation pages to follow)."""
    host = urlparse(base).netloc.split(".")[-2:]
    cands: dict[str, str] = {}
    nav: list[str] = []
    for l in links:
        href, text = (l.get("href") or "").split("#")[0], (l.get("text") or "").strip()
        if not href.startswith("http") or SKIP_HREF.search(href):
            continue
        if GENERIC_TEXT.match(text) and l.get("context"):
            text = l["context"]
        text = clean_title(text)
        if is_cta(text) and (parse.INTERN_RE.search(text) or parse.is_early(text) or NAV_HREF.search(href)):
            if href not in nav and href.rstrip("/") != base.rstrip("/"):
                nav.insert(0, href)            # buttons into job listings: follow these first, any site
            continue
        if _looks_like_program(text):
            cands.setdefault(href, text)
        elif (NAV_LABEL.match(text) or (NAV_HREF.search(href) and len(text) <= 40 and text)) \
                and urlparse(href).netloc.split(".")[-2:] == host and href.rstrip("/") != base.rstrip("/"):
            if href not in nav:
                nav.append(href)
    return list(cands.items()), nav[:5]


async def _render(ctx, url: str, wait_ms: int = 2500):
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=35000)
        try:
            await page.wait_for_load_state("networkidle", timeout=9000)
        except Exception:  # noqa: BLE001 - busy pages never go idle; carry on
            pass
        await page.wait_for_timeout(wait_ms)
        return page
    except Exception:
        await page.close()
        raise


async def crawl_firm(ctx, url: str, skip_detail: set[str], max_postings: int = 30) -> list[Job]:
    page = await _render(ctx, url)
    try:
        links = await page.evaluate(COLLECT_JS)
    finally:
        await page.close()
    cands, nav = pick_links(links, url)
    for n in nav:                                  # one level into Students / Internships pages
        if len(cands) >= max_postings:
            break
        try:
            p2 = await _render(ctx, n, 1500)
            try:
                more, _ = pick_links(await p2.evaluate(COLLECT_JS), n)
            finally:
                await p2.close()
            seen = {h for h, _ in cands}
            cands += [(h, t) for h, t in more if h not in seen]
        except Exception:  # noqa: BLE001 - a broken sub-page shouldn't lose the firm
            continue
    jobs = []
    for href, text in cands[:max_postings]:
        jid = _id(href)
        job = Job(source="browser", id=jid, title=text, url=href)
        if jid not in skip_detail:
            try:
                p3 = await _render(ctx, href, 1200)
                try:
                    info = await p3.evaluate(TEXT_JS)
                finally:
                    await p3.close()
                job.text = info.get("text") or ""
                if GENERIC_TEXT.match(text) or len(text) < 12:
                    job.title = info.get("h1") or info.get("title") or text
            except Exception:  # noqa: BLE001
                job.text = ""
        jobs.append(job)
    return jobs


async def _crawl_all(targets: list[tuple[str, str]], skip_detail: set[str], concurrency: int, ua: str):
    from playwright.async_api import async_playwright
    results: dict[str, tuple[list[Job] | None, str | None]] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--disable-dev-shm-usage"])
        ctx = await browser.new_context(user_agent=ua, viewport={"width": 1366, "height": 900}, locale="en-US")
        await ctx.route(re.compile(r".*\.(png|jpe?g|gif|webp|svg|woff2?|ttf|mp4|webm)(\?.*)?$"),
                        lambda route: route.abort())
        sem = asyncio.Semaphore(concurrency)

        async def one(name, url):
            async with sem:
                try:
                    jobs = await asyncio.wait_for(crawl_firm(ctx, url, skip_detail), timeout=240)
                    results[name] = (jobs, None)
                except Exception as e:  # noqa: BLE001
                    results[name] = (None, f"{type(e).__name__}: {str(e)[:200]}")

        await asyncio.gather(*(one(n, u) for n, u in targets))
        await browser.close()
    return results


def available() -> bool:
    try:
        import playwright.async_api  # noqa: F401
        return True
    except ImportError:
        return False


def crawl(targets: list[tuple[str, str]], skip_detail: set[str], concurrency: int = 6,
          ua: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36 WM-Internship-Tracker/1.0 (student project)"):
    """targets: [(firm name, careers url)] -> {firm: (jobs or None, error or None)}"""
    return asyncio.run(_crawl_all(targets, skip_detail, concurrency, ua))

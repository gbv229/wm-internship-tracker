"""Fetchers for each careers system.

Each fetcher returns a list of Job objects. Listing calls are cheap; the full
description (`detail()`) is only fetched for postings that pass the title
filter and aren't already cached, to keep each run polite and fast.
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Callable
from urllib.parse import quote, urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import parse

UA = ("Mozilla/5.0 (compatible; WM-Internship-Tracker/1.0; student project; "
      "+https://github.com/{repo})")

# Workday's search is fuzzy, so several short queries catch programs that
# don't use the word "intern" (e.g. "Summer Analyst", "Early Insights").
SEARCH_TERMS = ["intern", "summer analyst", "sophomore", "insight", "co-op", "wealth management program"]


def session(repo: str) -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset(["GET", "POST"]))
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=8))
    s.headers.update({"User-Agent": UA.format(repo=repo), "Accept": "application/json, text/html;q=0.9",
                      "Accept-Language": "en-US,en;q=0.9"})
    return s


@dataclass
class Job:
    source: str
    id: str
    title: str
    url: str
    location: str = ""
    posted: date | None = None
    text: str = ""                       # full description, when the listing includes it
    remote_hint: str | None = None
    closes: date | None = None           # structured close date, when the system has one
    _detail: Callable[[], str] | None = field(default=None, repr=False)

    def detail(self) -> str:
        if not self.text and self._detail:
            try:
                self.text = self._detail() or ""
            except Exception:  # noqa: BLE001 - a bad detail page shouldn't drop the job
                self.text = ""
        return self.text


TIMEOUT = 25


# ------------------------------------------------------------------ Workday
def workday(s: requests.Session, cfg: dict, today: date) -> list[Job]:
    host, tenant, site = cfg["host"], cfg["tenant"], str(cfg["site"])
    api = f"https://{host}/wday/cxs/{tenant}/{site}"
    public = f"https://{host}{cfg.get('path_prefix', '')}/{site}"
    jobs: dict[str, Job] = {}
    for term in SEARCH_TERMS:
        offset = 0
        while offset < 5000:  # stops early when the results run out
            r = s.post(f"{api}/jobs", json={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": term},
                       timeout=TIMEOUT, headers={"Content-Type": "application/json"})
            r.raise_for_status()
            data = r.json()
            posts = data.get("jobPostings") or []
            for p in posts:
                path = p.get("externalPath")
                if not path or path in jobs:
                    continue
                job = Job(
                    source="workday", id=f"wd:{tenant}:{path.rsplit('_', 1)[-1]}",
                    title=p.get("title", "").strip(), url=public + path,
                    location=p.get("locationsText") or "",
                    posted=parse.relative_posted(p.get("postedOn"), today),
                    remote_hint=p.get("remoteType"),
                )
                job._detail = _wd_detail(s, api + path, job)
                jobs[path] = job
            offset += 20
            if len(posts) < 20 or offset >= (data.get("total") or 0):
                break
            time.sleep(0.25)
    return list(jobs.values())


def _wd_detail(s, url, job: Job):
    def f():
        r = s.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        info = r.json().get("jobPostingInfo", {})
        # the listing only says "3 Locations"; the detail page names them
        locs = [info.get("location")] + list(info.get("additionalLocations") or [])
        locs = [l for l in dict.fromkeys(locs) if l]
        if locs:
            job.location = "; ".join(locs)
        return parse.html_to_text(info.get("jobDescription", ""))
    return f


# ------------------------------------------------------------------- Oracle
def oracle(s: requests.Session, cfg: dict, today: date) -> list[Job]:
    host, site = cfg["host"], cfg["site"]
    base = f"https://{host}/hcmRestApi/resources/latest"
    jobs: dict[str, Job] = {}
    for term in ["intern", "summer analyst", "internship", "sophomore"]:
        offset = 0
        while offset < 5000:  # stops early when the results run out
            finder = (f'findReqs;siteNumber={site},keyword="{term}",limit=50,offset={offset},'
                      f"sortBy=POSTING_DATES_DESC")
            r = s.get(f"{base}/recruitingCEJobRequisitions",
                      params={"onlyData": "true", "expand": "requisitionList.secondaryLocations", "finder": finder},
                      timeout=TIMEOUT)
            r.raise_for_status()
            items = (r.json().get("items") or [{}])[0]
            reqs = items.get("requisitionList") or []
            for q in reqs:
                rid = str(q.get("Id"))
                if rid in jobs:
                    continue
                locs = [q.get("PrimaryLocation") or ""] + [x.get("Name", "") for x in (q.get("secondaryLocations") or [])]
                jobs[rid] = Job(
                    source="oracle", id=f"or:{host.split('.')[0]}:{rid}", title=(q.get("Title") or "").strip(),
                    url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{rid}",
                    location="; ".join(dict.fromkeys(l for l in locs if l))[:200],
                    posted=parse.iso_date(q.get("PostedDate")),
                    remote_hint=q.get("WorkplaceType"),
                    _detail=_or_detail(s, base, site, rid),
                )
            offset += 50
            if len(reqs) < 50 or offset >= (items.get("TotalJobsCount") or 0):
                break
            time.sleep(0.25)
    return list(jobs.values())


def _or_detail(s, base, site, rid):
    def f():
        r = s.get(f"{base}/recruitingCEJobRequisitionDetails",
                  params={"onlyData": "true", "expand": "all", "finder": f'ById;Id="{rid}",siteNumber={site}'},
                  timeout=TIMEOUT)
        r.raise_for_status()
        it = (r.json().get("items") or [{}])[0]
        parts = [it.get("ExternalDescriptionStr"), it.get("ExternalQualificationsStr"),
                 it.get("ExternalResponsibilitiesStr"), it.get("CorporateDescriptionStr")]
        end = it.get("ExternalPostedEndDate")
        text = parse.html_to_text("\n".join(p for p in parts if p))
        if end:
            text += f"\nPosting ends {end[:10]}."
        return text
    return f


# --------------------------------------------------------------- Greenhouse
def greenhouse(s: requests.Session, cfg: dict, today: date) -> list[Job]:
    board = cfg["board"]
    r = s.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", params={"content": "true"}, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append(Job(
            source="greenhouse", id=f"gh:{board}:{j['id']}", title=j.get("title", "").strip(),
            url=j.get("absolute_url", ""), location=(j.get("location") or {}).get("name", ""),
            posted=parse.iso_date(j.get("first_published") or j.get("updated_at")),
            text=parse.html_to_text(j.get("content", "")),
        ))
    return out


# -------------------------------------------------------------------- Lever
def lever(s: requests.Session, cfg: dict, today: date) -> list[Job]:
    site = cfg["site"]
    r = s.get(f"https://api.lever.co/v0/postings/{site}", params={"mode": "json"}, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for j in r.json():
        lists = "\n".join(f"{l.get('text','')}\n{parse.html_to_text(l.get('content',''))}" for l in j.get("lists", []))
        cats = j.get("categories") or {}
        out.append(Job(
            source="lever", id=f"lv:{site}:{j['id']}", title=j.get("text", "").strip(), url=j.get("hostedUrl", ""),
            location=cats.get("location", ""), posted=parse.iso_date(j.get("createdAt")),
            text=f"{j.get('descriptionPlain','')}\n{lists}\n{j.get('additionalPlain','')}",
            remote_hint=j.get("workplaceType"),
        ))
    return out


# -------------------------------------------------------------------- Ashby
def ashby(s: requests.Session, cfg: dict, today: date) -> list[Job]:
    board = cfg["board"]
    r = s.get(f"https://api.ashbyhq.com/posting-api/job-board/{board}", timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        out.append(Job(
            source="ashby", id=f"as:{board}:{j['id']}", title=j.get("title", "").strip(),
            url=j.get("jobUrl", ""), location=j.get("location", ""), posted=parse.iso_date(j.get("publishedAt")),
            text=j.get("descriptionPlain") or parse.html_to_text(j.get("descriptionHtml", "")),
            remote_hint="Remote" if j.get("isRemote") else j.get("workplaceType"),
        ))
    return out


# -------------------------------------------------------------------- iCIMS
ICIMS_LINK = re.compile(r'href="(https://[^"]+?/jobs/(\d+)/[^"/]+/job)[^"]*"[^>]*>(.*?)</a>', re.I | re.S)


def icims(s: requests.Session, cfg: dict, today: date) -> list[Job]:
    host = cfg["host"]
    jobs: dict[str, Job] = {}
    for term in ["intern", "summer", "internship"]:
        for page in range(0, 100):  # stops early when the results run out
            r = s.get(f"https://{host}/jobs/search",
                      params={"ss": "1", "searchKeyword": term, "in_iframe": "1", "pr": page}, timeout=TIMEOUT)
            r.raise_for_status()
            found = 0
            for href, jid, inner in ICIMS_LINK.findall(r.text):
                found += 1
                if jid in jobs:
                    continue
                title = parse.html_to_text(inner)
                title = re.sub(r"(?i)^\s*(job posting title|posting title|job title|title)\s*:?\s*", "", title)
                title = re.sub(r"\s+", " ", title).strip()
                if not title:
                    continue
                jobs[jid] = Job(source="icims", id=f"ic:{host.split('.')[0]}:{jid}", title=title,
                                url=href.split("?")[0], _detail=_ic_detail(s, href.split("?")[0]))
            if found < 10:
                break
            time.sleep(0.3)
    # location is only on the detail page; it's filled in when detail() runs
    return list(jobs.values())


def _ic_detail(s, url):
    def f():
        r = s.get(url, params={"in_iframe": "1"}, timeout=TIMEOUT)
        r.raise_for_status()
        m = re.search(r'(?is)<div[^>]+class="[^"]*iCIMS_JobContent[^"]*"[^>]*>(.*?)<div[^>]+class="[^"]*iCIMS_(?:JobOptions|Footer)', r.text)
        return parse.html_to_text(m.group(1) if m else r.text)
    return f


# ---------------------------------------------------------- SmartRecruiters
def smartrecruiters(s: requests.Session, cfg: dict, today: date) -> list[Job]:
    co = cfg["company"]
    base = f"https://api.smartrecruiters.com/v1/companies/{co}/postings"
    out, offset = [], 0
    while offset < 5000:  # stops early when the results run out
        r = s.get(base, params={"limit": 100, "offset": offset}, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        items = data.get("content") or []
        for j in items:
            loc = j.get("location") or {}
            where = ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country", "").upper()) if x)
            if loc.get("remote"):
                where = (where + " (remote)").strip()
            out.append(Job(
                source="smartrecruiters", id=f"sr:{co}:{j['id']}", title=(j.get("name") or "").strip(),
                url=f"https://jobs.smartrecruiters.com/{co}/{j['id']}", location=where,
                posted=parse.iso_date(j.get("releasedDate")),
                remote_hint="Remote" if loc.get("remote") else None,
                _detail=_sr_detail(s, f"{base}/{j['id']}"),
            ))
        offset += 100
        if len(items) < 100 or offset >= (data.get("totalFound") or 0):
            break
    return out


def _sr_detail(s, url):
    def f():
        r = s.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        sec = (r.json().get("jobAd") or {}).get("sections") or {}
        parts = [(sec.get(k) or {}).get("text") for k in ("jobDescription", "qualifications", "additionalInformation", "companyDescription")]
        return parse.html_to_text("\n".join(p for p in parts if p))
    return f


# ---------------------------------------------------------- page watching
def page_fingerprint(s: requests.Session, url: str) -> tuple[str, list[str]]:
    """Hash of the visible text of a careers page, plus any internship-looking
    link titles on it (useful when the page lists programs server-side)."""
    r = s.get(url, timeout=TIMEOUT, headers={"Accept": "text/html"})
    r.raise_for_status()
    body = r.text
    text = parse.html_to_text(body)
    text = re.sub(r"\d{1,2}:\d{2}|\b\d{10,}\b", "", text)  # drop clocks / cache-busters
    links = []
    for href, inner in re.findall(r'(?is)<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body):
        t = parse.html_to_text(inner)
        if 6 <= len(t) <= 140 and parse.INTERN_RE.search(t):
            links.append(f"{t} | {urljoin(url, href)}")
    return hashlib.sha256(text.encode()).hexdigest()[:16], sorted(set(links))[:25]


FETCHERS = {"workday": workday, "oracle": oracle, "greenhouse": greenhouse, "lever": lever,
            "ashby": ashby, "icims": icims, "smartrecruiters": smartrecruiters}

#!/usr/bin/env python3
"""Workday reader that runs on Gage's Mac (installed by tools/install_local_workday.sh).

Since Nov 2026 Workday's firewall refuses requests from cloud servers such as GitHub's, so this
script checks the Workday job boards from a home/campus connection instead, at a gentle pace,
and uploads what it finds to the project's "workday-feed" release. The GitHub update reads that
file instead of calling Workday.

Standard library only; every web request goes through macOS's own curl (system certificates).
Run by launchd every 30 minutes. Each run checks the third of the boards checked longest ago.
"""
from __future__ import annotations

import gzip
import json
import math
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = "gbv229/wm-internship-tracker"
BOARDS_URL = f"https://raw.githubusercontent.com/{REPO}/main/data/workday_boards.json"
RELEASE_TAG = "workday-feed"
ASSET = "workday_feed.json.gz"
UA = f"WM-Internship-Tracker/1.0 (student project; +https://github.com/{REPO})"
HOME = Path(os.environ.get("WM_TRACKER_HOME", Path.home() / "Library/Application Support/wm-tracker"))
STATE = HOME / "state.json"
TERMS = ["intern", "summer", "insight", "co-op"]
MAX_PAGES = 5                     # 100 results per term; search is relevance-ranked
GAP = 1.5                         # seconds between Workday requests (plus jitter)
# titles worth keeping; the GitHub side applies the real filters
KEEP = re.compile(r"(?i)intern|summer|co-?op|insight|sophomore|fellow|extern|analyst program|"
                  r"associate program|development program|rotational|student|campus|early career|apprentic")


def log(*a):
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def curl(url, method="GET", data=None, headers=None, timeout=40, data_file=None):
    """Returns (status, body bytes). Uses /usr/bin/curl so macOS's certificates are used."""
    cmd = ["/usr/bin/curl", "-sS", "-L", "--max-time", str(timeout), "-X", method, "-A", UA,
           "-w", "\n%{http_code}", "-o", "-"]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    if data is not None:
        cmd += ["--data-binary", "@-"]
    if data_file:
        cmd += ["--data-binary", f"@{data_file}"]
    cmd.append(url)
    try:
        p = subprocess.run(cmd, input=data, capture_output=True, timeout=timeout + 10)
    except subprocess.TimeoutExpired:
        LAST_ERR[0] = "timed out"
        return 0, b""
    body, _, code = p.stdout.rpartition(b"\n")
    LAST_ERR[0] = p.stderr.decode(errors="replace").strip()[:200] or f"curl exit {p.returncode}"
    try:
        return int(code), body
    except ValueError:
        return 0, p.stdout


LAST_ERR = [""]


def get_retry(url, tries=4):
    for i in range(tries):
        code, out = curl(url)
        if code == 200:
            return code, out
        log(f"couldn't load {url.rsplit('/', 1)[-1]} (HTTP {code}: {LAST_ERR[0]}); retrying" if i < tries - 1 else
            f"couldn't load {url.rsplit('/', 1)[-1]} (HTTP {code}: {LAST_ERR[0]})")
        time.sleep(20)
    return code, out


def self_update():
    """Pick up fixes pushed to the project: replace this file if the published copy differs."""
    code, out = curl(f"https://raw.githubusercontent.com/{REPO}/main/tools/local_workday.py")
    me = Path(__file__)
    if code == 200 and out.startswith(b"#!/usr/bin/env python3") and b"def main()" in out and out != me.read_bytes():
        me.write_bytes(out)
        log("updated the reader to the latest version (takes effect next run)")


def token() -> str:
    t = os.environ.get("WM_TRACKER_TOKEN")
    if t:
        return t
    p = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", "wm-tracker-github", "-w"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit("No GitHub key in the Keychain (service wm-tracker-github). Re-run the installer.")
    return p.stdout.strip()


class Refused(Exception):
    pass


_last = [0.0]


def wd(url, payload=None):
    """One Workday call, spaced out; one patient retry on a 429."""
    for attempt in range(2):
        wait = _last[0] + GAP + random.uniform(0, 1.0) - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        body = json.dumps(payload).encode() if payload is not None else None
        code, out = curl(url, "POST" if payload is not None else "GET", data=body,
                         headers={"Accept": "application/json", "Content-Type": "application/json",
                                  "Accept-Language": "en-US"})
        if code == 200:
            return json.loads(out or b"{}")
        if code in (429, 503) and attempt == 0:
            time.sleep(30)
            continue
        if code in (429, 503):
            raise Refused(f"HTTP {code}")
        raise RuntimeError(f"HTTP {code} for {url}")


def check_board(b: dict, cache: dict) -> list[dict]:
    api = f"https://{b['host']}/wday/cxs/{b['tenant']}/{b['site']}"
    public = f"https://{b['host']}{b.get('path_prefix', '')}/{b['site']}"
    jobs: dict[str, dict] = {}
    for term in TERMS:
        for page in range(MAX_PAGES):
            d = wd(f"{api}/jobs", {"appliedFacets": {}, "limit": 20, "offset": page * 20, "searchText": term})
            posts = d.get("jobPostings") or []
            for p in posts:
                path = p.get("externalPath")
                if not path or path in jobs or not KEEP.search(p.get("title") or ""):
                    continue
                jobs[path] = {"id": f"wd:{b['tenant']}:{path.rsplit('_', 1)[-1]}", "title": (p.get("title") or "").strip(),
                              "url": public + path, "path": path, "location": p.get("locationsText") or "",
                              "postedOn": p.get("postedOn"), "remoteType": p.get("remoteType")}
            if len(posts) < 20 or (page + 1) * 20 >= (d.get("total") or 0):
                break
    for j in jobs.values():           # descriptions: fetched once per posting, then cached
        if j["id"] not in cache:
            info = wd(api + j["path"]).get("jobPostingInfo") or {}
            cache[j["id"]] = {k: info.get(k) for k in ("jobDescription", "location", "additionalLocations",
                                                       "startDate", "timeType")}
        j["detail"] = cache[j["id"]]
    return list(jobs.values())


def upload(feed: bytes, tok: str):
    h = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    code, out = curl(f"https://api.github.com/repos/{REPO}/releases/tags/{RELEASE_TAG}", headers=h)
    if code == 404:                   # first run: make the release that holds the feed
        code, out = curl(f"https://api.github.com/repos/{REPO}/releases", "POST", headers=h, data=json.dumps({
            "tag_name": RELEASE_TAG, "target_commitish": "main", "name": "Workday feed (uploaded by the Mac reader)",
            "body": "Holds workday_feed.json.gz, uploaded every 30 minutes by tools/local_workday.py. Not a software release.",
            "prerelease": True}).encode())
        code = 200 if code == 201 else code
    if code != 200:
        raise RuntimeError(f"can't find or create the {RELEASE_TAG} release (HTTP {code}): {out[:200]!r}")
    rel = json.loads(out)
    # a run cut off mid-upload (sleep, network drop) can leave its temporary file behind;
    # clear it first or GitHub refuses the new upload as "already_exists"
    for a in rel.get("assets") or []:
        if a["name"] == f"new-{ASSET}":
            curl(f"https://api.github.com/repos/{REPO}/releases/assets/{a['id']}", "DELETE", headers=h)
    rel["assets"] = [a for a in rel.get("assets") or [] if a["name"] != f"new-{ASSET}"]
    tmp = HOME / ASSET
    tmp.write_bytes(feed)
    # upload under a temporary name first, so the GitHub side never sees a missing file
    code, out = curl(f"https://uploads.github.com/repos/{REPO}/releases/{rel['id']}/assets?name=new-{ASSET}", "POST",
                     headers={**h, "Content-Type": "application/gzip"}, data_file=str(tmp), timeout=120)
    if code != 201:
        raise RuntimeError(f"upload failed (HTTP {code}): {out[:200]!r}")
    new = json.loads(out)
    for a in rel.get("assets") or []:
        if a["name"] in (ASSET, f"new-{ASSET}"):
            curl(f"https://api.github.com/repos/{REPO}/releases/assets/{a['id']}", "DELETE", headers=h)
    code, out = curl(f"https://api.github.com/repos/{REPO}/releases/assets/{new['id']}", "PATCH",
                     data=json.dumps({"name": ASSET}).encode(), headers=h)
    if code != 200:
        raise RuntimeError(f"rename failed (HTTP {code}): {out[:200]!r}")


def main():
    HOME.mkdir(parents=True, exist_ok=True)
    tok = token()
    code, out = get_retry(BOARDS_URL)
    if code != 200:
        return 1
    self_update()
    boards = json.loads(out)["boards"]
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    results, cache = state.get("boards", {}), state.get("details", {})
    keys = {b["key"] for b in boards}
    results = {k: v for k, v in results.items() if k in keys}
    order = sorted(boards, key=lambda b: results.get(b["key"], {}).get("checked_at", ""))
    n = int(os.environ.get("WM_BOARDS_PER_RUN", math.ceil(len(boards) / 3)))
    refused_in_a_row, done = 0, 0
    for b in order[:n]:
        try:
            jobs = check_board(b, cache)
            results[b["key"]] = {"company": b["company"], "ok": True, "jobs": jobs,
                                 "checked_at": datetime.now(timezone.utc).isoformat(timespec="minutes")}
            refused_in_a_row, done = 0, done + 1
        except Refused as e:
            log("refused:", b["key"], e)
            refused_in_a_row += 1
            if refused_in_a_row >= 3:
                log("Workday is refusing this connection too; stopping until the next run")
                break
        except Exception as e:  # noqa: BLE001
            log("error:", b["key"], type(e).__name__, str(e)[:160])
    live = {j["id"] for r in results.values() for j in r.get("jobs", [])}
    cache = {k: v for k, v in cache.items() if k in live}
    STATE.write_text(json.dumps({"boards": results, "details": cache}))
    feed = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"), "boards": results}
    upload(gzip.compress(json.dumps(feed).encode()), tok)
    log(f"checked {done}/{n} boards; feed has {len(results)} boards, {len(live)} postings; uploaded")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        log("failed:", type(e).__name__, e)
        sys.exit(1)

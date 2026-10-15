"""Early programs: merge the hand-maintained list with live postings and
write the files the site reads, including a calendar feed.

    data/early_programs.json   programs for the "Early programs" tab
    data/early-programs.ics    calendar feed: opening dates + deadlines with reminders
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

TYPES = {"sophomore", "insight", "fellowship", "first_year", "summer_2028", "training", "ambassador"}
FIELDS = {"wealth", "real_estate", "banking", "asset_mgmt", "multi"}
STATUSES = {"open", "upcoming", "closed", "watch", "invite"}
EXTRA_DOMAINS = {
    "Evercore": "evercore.com", "Moelis": "moelis.com", "Jefferies": "jefferies.com", "Lazard": "lazard.com",
    "Houlihan Lokey": "hl.com", "Guggenheim": "guggenheimpartners.com", "William Blair": "williamblair.com",
    "Bain Capital": "baincapital.com", "Girls Who Invest": "girlswhoinvest.org", "Citi": "citi.com",
}
TEXT_FIELDS = {"firm", "program", "eligibility", "when", "opens_note", "deadline_note", "notes", "link", "source"}
SITE = "https://gbv229.github.io/wm-internship-tracker/"


def _d(v):
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


def load_curated(path: Path, companies: list[dict]) -> list[dict]:
    raw = yaml.safe_load(path.read_text())["programs"]
    domains = {c["name"]: c.get("domain") for c in companies}
    out, seen = [], set()
    for p in raw:
        assert p["id"] not in seen, f"duplicate id {p['id']}"
        seen.add(p["id"])
        assert p["type"] in TYPES, (p["id"], p["type"])
        assert p["field"] in FIELDS, (p["id"], p["field"])
        assert p["status"] in STATUSES, (p["id"], p["status"])
        assert p.get("link", "").startswith("http"), p["id"]
        rec = {k: (str(v) if k in TEXT_FIELDS and v is not None else v) for k, v in p.items()}
        for k in ("opens", "deadline"):
            v = _d(p.get(k))
            rec[k] = v.isoformat() if v else None
            rec[f"{k}_est"] = bool(p.get(f"{k}_est")) and v is not None
        rec["domain"] = p.get("domain") or domains.get(p["firm"]) or EXTRA_DOMAINS.get(p["firm"])
        rec["origin"] = "curated"
        out.append(rec)
    return out


def live_programs(postings: list[dict], companies: list[dict]) -> list[dict]:
    """Open postings tagged 'early' by the scraper (sophomore / insight /
    externship / fellowship titles at any tracked firm)."""
    domains = {c["name"]: c.get("domain") for c in companies}
    out = []
    for p in postings:
        if p.get("status") != "open" or "early" not in (p.get("tracks") or []):
            continue
        title = p["title"]
        typ = ("insight" if re.search(r"(?i)insight|summit|discovery|explore|forum", title) else
               "fellowship" if re.search(r"(?i)fellow", title) else
               "first_year" if re.search(r"(?i)freshm|first[- ]year", title) else "sophomore")
        tr = p.get("tracks") or []
        field = "wealth" if "wealth" in tr else "real_estate" if "real_estate" in tr else "multi"
        classes = p.get("classes") or []
        elig = (f"Class of {', '.join(map(str, classes))}" if classes else "See posting") + \
               (f". {p['location']}" if p.get("location") else "")
        out.append({
            "id": "live-" + p["id"], "firm": p["company"], "program": title, "type": typ, "field": field,
            "eligibility": elig, "when": p.get("season") or "", "opens": p.get("posted"), "opens_est": False,
            "deadline": p.get("deadline"), "deadline_est": False, "deadline_note": p.get("deadline_evidence"),
            "status": "open", "link": p["url"], "source": p["url"], "domain": domains.get(p["company"]),
            "origin": "live", "first_seen": p.get("first_seen"), "region": p.get("regions") or [],
        })
    return out


# ------------------------------------------------------------------ ics
def _esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    out, b = [], line.encode()
    while len(b) > 74:
        cut = 74
        while (b[cut] & 0xC0) == 0x80:  # don't split a UTF-8 character
            cut -= 1
        out.append(b[:cut].decode())
        b = b" " + b[cut:]
    out.append(b.decode())
    return "\r\n".join(out)


def events_for(p: dict) -> list[dict]:
    """Calendar events for one program: its opening date and deadline."""
    ev = []
    name = f"{p['firm']} – {p['program']}"
    detail = "\n".join(x for x in [p.get("eligibility"), p.get("when"), p.get("opens_note"),
                                   p.get("deadline_note"), p.get("notes"), p.get("link"),
                                   f"Tracker: {SITE}#tab=early"] if x)
    if p.get("opens") and p.get("status") not in ("closed", "invite"):
        est = p.get("opens_est")
        ev.append({"uid": f"{p['id']}-opens", "date": p["opens"],
                   "summary": f"{'Expected to open' if est else 'Opens'}: {name}",
                   "desc": detail, "alarms": ["-PT15H", "PT9H"], "url": p.get("link")})  # 9am the day before, 9am day of
    if p.get("deadline") and p.get("status") not in ("invite",):
        est = p.get("deadline_est")
        ev.append({"uid": f"{p['id']}-deadline", "date": p["deadline"],
                   "summary": f"{'Likely deadline' if est else 'Deadline'}: {name}",
                   "desc": detail, "alarms": ["-P6DT15H", "-P1DT15H", "-PT15H"], "url": p.get("link")})  # 9am: 7, 2 and 1 days before
    return ev


def write_ics(programs: list[dict], path: Path, today: date):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    keep_from = today
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//WM Internship Tracker//Early programs//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Internship deadlines (early programs)",
             "X-WR-CALDESC:Opening dates and deadlines for sophomore programs, insight days and Summer 2028 internships.",
             "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    for p in programs:
        if p.get("status") in ("closed", "invite"):
            continue
        for e in events_for(p):
            d = date.fromisoformat(e["date"])
            if d < keep_from:
                continue
            lines += ["BEGIN:VEVENT", f"UID:{e['uid']}@wm-internship-tracker", f"DTSTAMP:{stamp}",
                      f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}",
                      f"SUMMARY:{_esc(e['summary'])}", f"DESCRIPTION:{_esc(e['desc'])}", "TRANSP:TRANSPARENT"]
            if e.get("url"):
                lines.append(f"URL:{e['url']}")
            for a in e["alarms"]:
                lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_esc(e['summary'])}",
                          f"TRIGGER:{a}", "END:VALARM"]
            lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    path.write_text("\r\n".join(_fold(l) for l in lines) + "\r\n")


def build(root: Path, data: Path, postings: list[dict], companies: list[dict], today: date):
    curated = load_curated(root / "early_programs.yaml", companies)
    live = live_programs(postings, companies)
    # don't list a live posting twice if the curated entry links to it
    curated_links = {p["link"] for p in curated}
    live = [p for p in live if p["link"] not in curated_links]
    programs = curated + live
    (data / "early_programs.json").write_text(json.dumps({"programs": programs, "researched": "2026-10-15"},
                                                         indent=1, ensure_ascii=False) + "\n")
    write_ics(programs, data / "early-programs.ics", today)
    return programs

import json
from datetime import date
from pathlib import Path

import yaml

from scraper import early, parse

ROOT = Path(__file__).resolve().parent.parent


def test_curated_list_is_valid():
    companies = yaml.safe_load((ROOT / "companies.yaml").read_text())["companies"]
    progs = early.load_curated(ROOT / "early_programs.yaml", companies)
    assert len(progs) >= 50
    for p in progs:
        assert p["firm"] and p["program"] and p["link"].startswith("https://")
        if p["opens"] and p["deadline"]:
            assert p["opens"] <= p["deadline"], p["id"]


def test_ics_feed(tmp_path):
    progs = [
        {"id": "a", "firm": "Firm, Inc", "program": "Sophomore; Program", "status": "upcoming",
         "opens": "2026-11-11", "opens_est": True, "deadline": "2027-01-13", "deadline_est": False,
         "link": "https://example.com", "eligibility": "Sophomores"},
        {"id": "b", "firm": "Old", "program": "Past", "status": "closed", "deadline": "2026-09-01",
         "link": "https://example.com"},
    ]
    early.write_ics(progs, tmp_path / "x.ics", date(2026, 10, 15))
    raw = (tmp_path / "x.ics").read_bytes().decode()
    assert raw.count("BEGIN:VEVENT") == 2                 # closed program skipped
    assert "Expected to open: Firm\\, Inc – Sophomore\\; Program" in raw
    assert "DTSTART;VALUE=DATE:20270113" in raw
    assert all(len(l.encode()) <= 75 for l in raw.split("\r\n"))
    assert raw.count("BEGIN:VALARM") == 5


def test_early_detection():
    assert parse.is_early("PGIM: 2027 Real Estate, Sophomore Externship Program")
    assert parse.is_early("2026 Morgan Stanley Early Insights Program")
    assert parse.is_early("JPMorganChase Fellowship Program")
    assert not parse.is_early("2027 Software Engineer Sophomore Intern")
    assert not parse.is_early("2027 Summer Analyst")
    assert not parse.is_early("Relationship Banker - Georgia South - Summit Point - Fayetteville")
    assert not parse.is_internship("Relationship Banker - Georgia South - Summit Point")
    assert parse.is_early("BNY Sophomore Summit")


def test_watchlist_flips_open_when_posting_appears():
    cur = [{"id": "ms-2028-wm", "firm": "Morgan Stanley", "program": "2028 WM Summer Analyst", "type": "summer_2028",
            "field": "wealth", "status": "upcoming", "opens": "2027-01-04", "opens_est": True, "link": "https://x"},
           {"id": "jll-2028", "firm": "JLL", "program": "Summer 2028", "type": "summer_2028",
            "field": "real_estate", "status": "upcoming", "link": "https://y"}]
    posts = [
        {"id": "1", "company": "Morgan Stanley", "title": "2028 Wealth Management Summer Analyst Program", "url": "https://ms/1",
         "status": "open", "tracks": ["wealth"], "regions": ["Northeast"], "first_seen": "2027-01-06", "season": "Summer 2028"},
        {"id": "2", "company": "Morgan Stanley", "title": "2028 WM Summer Analyst (London)", "url": "https://ms/2",
         "status": "open", "tracks": ["wealth"], "regions": ["International"], "first_seen": "2027-01-05"},
        {"id": "3", "company": "JLL", "title": "Capital Markets Summer 2027 Internship", "url": "https://jll/3",
         "status": "open", "tracks": ["real_estate"], "regions": ["West"], "season": "Summer 2027"},
    ]
    used = early.detect_live(cur, posts)
    assert used == {"https://ms/1"}
    assert cur[0]["status"] == "open" and cur[0]["opens"] == "2027-01-06" and not cur[0]["opens_est"]
    assert cur[1]["status"] == "upcoming"
    assert early.same_firm("Citi", "Citi (incl. Citi Private Bank)") and not early.same_firm("Baird", "Bain Capital")

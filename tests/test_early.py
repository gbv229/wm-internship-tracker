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
    assert "Expected to open: Firm\\, Inc – Sophomore\; Program" in raw
    assert "DTSTART;VALUE=DATE:20270113" in raw
    assert all(len(l.encode()) <= 75 for l in raw.split("\r\n"))
    assert raw.count("BEGIN:VALARM") == 5


def test_early_detection():
    assert parse.is_early("PGIM: 2027 Real Estate, Sophomore Externship Program")
    assert parse.is_early("2026 Morgan Stanley Early Insights Program")
    assert parse.is_early("JPMorganChase Fellowship Program")
    assert not parse.is_early("2027 Software Engineer Sophomore Intern")
    assert not parse.is_early("2027 Summer Analyst")

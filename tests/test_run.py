"""End-to-end run with fake careers systems: filtering, parsing, merging and
closing postings that disappear."""
import json
from datetime import date

from scraper import run, sources

YAML = """
companies:
  - name: Big Bank
    type: Global Bank
    focus: mixed
    hq: New York, NY
    careers: https://example.com/careers
    sources:
      - workday: {host: x.wd1.myworkdayjobs.com, tenant: x, site: X}
  - name: Small RIA
    type: Independent RIA
    focus: wealth
    hq: Bethlehem, PA
    careers: https://example.com/ria
    sources:
      - page: {url: "https://example.com/ria"}
"""

WM = ("Wealth Management Summer Analyst Program. Wealth Management is our core. Candidates must have an expected "
      "graduation date between December 2027 and June 2028. Applications are due by November 20, 2026. "
      "The hourly rate is $30 - $35 per hour. Minimum GPA of 3.3.")


def make_jobs(include_wm=True):
    jobs = [
        sources.Job("workday", "wd:x:1", "Software Engineering Intern", "https://e/1", text="Build trading systems."),
        sources.Job("workday", "wd:x:2", "Senior Wealth Advisor", "https://e/2", text="Experienced hire."),
        sources.Job("workday", "wd:x:4", "2027 Summer Analyst Program", "https://e/4", _detail=lambda: WM),
    ]
    if include_wm:
        jobs.append(sources.Job("workday", "wd:x:3", "2027 Private Wealth Summer Analyst", "https://e/3",
                                location="New York, NY", _detail=lambda: WM))
    return jobs


def setup(tmp_path, monkeypatch, jobs, page=("abc", [])):
    (tmp_path / "companies.yaml").write_text(YAML)
    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.setattr(run, "DATA", tmp_path / "data")
    monkeypatch.setitem(sources.FETCHERS, "workday", lambda s, cfg, today: jobs)
    monkeypatch.setattr(sources, "page_fingerprint", lambda s, url: page)


def read(tmp_path, name):
    return json.loads((tmp_path / "data" / name).read_text())


def test_full_cycle(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, make_jobs())
    run.main(["--browser", "off"])
    posts = {p["id"]: p for p in read(tmp_path, "postings.json")["postings"]}
    assert set(posts) == {"wd:x:3", "wd:x:4"}     # SWE intern + experienced hire filtered out
    p = posts["wd:x:3"]
    assert p["season"] == "Summer 2027"
    assert p["classes"] == [2028]
    assert p["deadline"] == "2026-11-20"
    assert p["pay"] == "$30–$35/hr" and p["gpa"] == "3.3+"
    assert p["status"] == "open"
    cos = {c["name"]: c for c in read(tmp_path, "companies.json")["companies"]}
    assert cos["Big Bank"]["open"] == 2
    assert cos["Small RIA"]["sources"][0]["hash"] == "abc"

    # posting disappears: needs two successful runs before it's closed
    setup(tmp_path, monkeypatch, make_jobs(include_wm=False), page=("def", ["Summer Intern | https://example.com/ria/1"]))
    run.main(["--browser", "off"])
    posts = {p["id"]: p for p in read(tmp_path, "postings.json")["postings"]}
    assert posts["wd:x:3"]["status"] == "open" and posts["wd:x:3"]["misses"] == 1
    cos = {c["name"]: c for c in read(tmp_path, "companies.json")["companies"]}
    assert cos["Small RIA"]["sources"][0]["changed_on"]          # page hash changed
    assert cos["Small RIA"]["sources"][0]["links"] == ["Summer Intern | https://example.com/ria/1"]
    run.main(["--browser", "off"])
    posts = {p["id"]: p for p in read(tmp_path, "postings.json")["postings"]}
    assert posts["wd:x:3"]["status"] == "closed"


def test_failed_source_does_not_close(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch, make_jobs())
    run.main(["--browser", "off"])

    def boom(s, cfg, today):
        raise RuntimeError("site down")
    monkeypatch.setitem(sources.FETCHERS, "workday", boom)
    run.main(["--browser", "off"])
    run.main(["--browser", "off"])
    posts = {p["id"]: p for p in read(tmp_path, "postings.json")["postings"]}
    assert posts["wd:x:3"]["status"] == "open"
    cos = {c["name"]: c for c in read(tmp_path, "companies.json")["companies"]}
    assert cos["Big Bank"]["sources"][0]["ok"] is False
    assert "site down" in cos["Big Bank"]["sources"][0]["error"]


def test_overrides(tmp_path):
    (tmp_path / "o.yaml").write_text("""
overrides:
  - match: {company: "Big Bank", title_contains: "private wealth"}
    set: {deadline: 2026-12-01, classes: [2029], note: "Confirmed with recruiter"}
    verified: 2026-10-16
    source: recruiter email
""")
    posts = {"a": {"id": "a", "company": "Big Bank", "title": "2027 Private Wealth Summer Analyst", "url": "u",
                   "deadline": None, "classes": []},
             "b": {"id": "b", "company": "Other", "title": "2027 Private Wealth Summer Analyst", "url": "u",
                   "deadline": None, "classes": []}}
    assert run.apply_overrides(posts, tmp_path / "o.yaml") == 1
    a = posts["a"]
    assert a["deadline"] == "2026-12-01" and a["classes"] == [2029] and a["verified"] == "2026-10-16"
    assert "recruiter email" in a["deadline_evidence"] and a["note"] == "Confirmed with recruiter"
    assert posts["b"]["deadline"] is None

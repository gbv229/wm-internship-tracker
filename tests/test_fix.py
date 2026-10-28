import json
from datetime import date

from tools import apply_fix


def _setup(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/postings.json").write_text(json.dumps({"postings": [{"id": "wd:x:1", "company": "JLL", "title": "Intern"}]}))
    (tmp_path / "overrides.yaml").write_text("# header\n\noverrides: []\n")
    monkeypatch.setattr(apply_fix, "ROOT", tmp_path)


def test_fix_rules(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    body = '**Problem:** Wrong class year\n\n**Correct class years, e.g. 2028, 2029:** 2028 and 2029\n\n<!-- fix: {"id": "wd:x:1", "kind": "classes"} -->'
    rule, msg = apply_fix.build_rule(body, 7, date(2026, 10, 28))
    assert rule["set"] == {"classes": [2028, 2029]} and rule["source"] == "Report #7"
    apply_fix.append_rule(rule, tmp_path / "overrides.yaml")
    text = (tmp_path / "overrides.yaml").read_text()
    assert text.startswith("# header") and "wd:x:1" in text
    r2, _ = apply_fix.build_rule('<!-- fix: {"id": "wd:x:1", "kind": "closed"} -->', 8, date(2026, 10, 28))
    assert r2["set"] == {"status": "closed"}
    assert apply_fix.build_rule('<!-- fix: {"id": "nope", "kind": "closed"} -->', 9, date.today())[0] is None
    assert apply_fix.build_rule("**Correct deadline as YYYY-MM-DD:** soon\n<!-- fix: {\"id\": \"wd:x:1\", \"kind\": \"deadline\"} -->", 1, date.today())[0] is None
    assert apply_fix.build_rule("no marker", 1, date.today())[0] is None

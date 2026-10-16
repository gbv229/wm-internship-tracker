"""End-to-end: a JavaScript-rendered careers site read by the browser pass."""
import functools
import http.server
import json
import threading
from pathlib import Path

import pytest

from scraper import browser, run, sources

pytestmark = pytest.mark.skipif(not browser.available(), reason="playwright not installed")

PAGES = {
    "/index.html": """<html><head><meta charset="utf-8"></head><body><nav><a href="/students/index.html">Students</a></nav>
      <main><div id="app"></div><script>document.getElementById('app').innerHTML =
      '<a href="/jobs/wm.html">2027 Summer Analyst Program - Private Wealth Management</a>';</script></main></body></html>""",
    "/students/index.html": """<html><head><meta charset="utf-8"></head><body><main>
      <div><h3>Sophomore Insight Day - Real Estate</h3><a href="/jobs/insight.html">Learn more</a></div>
      <a href="/jobs/swe.html">Software Engineering Intern</a></main></body></html>""",
    "/jobs/wm.html": """<html><head><meta charset="utf-8"></head><body><main><h1>2027 Summer Analyst Program - Private Wealth Management</h1>
      <p>Location: New York, NY</p><p>Join Private Wealth Management. Candidates must have an expected graduation date
      between December 2027 and June 2028. Applications are due by November 20, 2026.</p></main></body></html>""",
    "/jobs/insight.html": """<html><head><meta charset="utf-8"></head><body><main><h1>Sophomore Insight Day - Real Estate</h1>
      <p>Open to sophomores. Learn about real estate investment. Apply by November 1, 2026.</p></main></body></html>""",
    "/jobs/swe.html": "<html><body><main><h1>SWE Intern</h1></main></body></html>",
}


@pytest.fixture()
def site(tmp_path):
    root = tmp_path / "site"
    for path, body in PAGES.items():
        f = root / path.lstrip("/")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/index.html"
    srv.shutdown()


def test_browser_pass(tmp_path, monkeypatch, site):
    (tmp_path / "companies.yaml").write_text(f"""
companies:
  - name: Page Bank
    type: Global Bank
    focus: mixed
    tracks: [wealth, real_estate]
    hq: New York, NY
    careers: {site}
    domain: example.com
    sources:
      - page: {{url: "{site}"}}
""")
    (tmp_path / "early_programs.yaml").write_text("programs: []\n")
    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.setattr(run, "DATA", tmp_path / "data")
    monkeypatch.setattr(sources, "page_fingerprint", lambda s, url: ("h", []))
    run.main(["--browser", "on"])
    posts = {p["title"]: p for p in json.loads((tmp_path / "data" / "postings.json").read_text())["postings"]}
    wm = posts["2027 Summer Analyst Program - Private Wealth Management"]
    assert wm["source"] == "browser" and wm["tracks"] == ["wealth"]
    assert wm["classes"] == [2028] and wm["deadline"] == "2026-11-20" and wm["regions"] == ["Northeast"]
    ins = posts["Sophomore Insight Day - Real Estate"]
    assert "real_estate" in ins["tracks"] and "early" in ins["tracks"]
    assert not any("SWE" in t or "Software" in t for t in posts)
    cos = json.loads((tmp_path / "data" / "companies.json").read_text())["companies"]
    assert any(s["kind"] == "browser" and s["ok"] for s in cos[0]["sources"])

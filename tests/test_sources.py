from datetime import date

from scraper import sources

HTML = '''<a href="/vx/lang-en-GB/mobile-0/brand-2/candidate/so/pm/1/pl/1/opp/22304-2027-IM-Real-Assets/en-GB">2027 Investment Management Summer Analyst Programme - Real Assets (London)</a>
<a href="/vx/x/opp/22305-Wealth/en-GB">2028 Wealth Management Summer Analyst Program - New York</a>'''


class _R:
    def __init__(self, t): self.text = t
    def raise_for_status(self): pass


class _S:
    def get(self, *a, **k): return _R(HTML)


def test_oleeo_board():
    jobs = sources.oleeo(_S(), {"board": "https://morganstanley.tal.net/vx/a/jobboard/vacancy/1/adv/", "key": "ms"}, date.today())
    assert [j.id for j in jobs] == ["oleeo:ms:22304", "oleeo:ms:22305"]   # second page adds nothing -> stops
    assert jobs[0].location == "London" and jobs[1].location == "New York"
    assert jobs[1].url == "https://morganstanley.tal.net/vx/x/opp/22305-Wealth/en-GB"


PHENOM_PAGE = '''<script>phApp.ddo = {"eagerLoadRefineSearch": {"totalHits": 2, "hits": 2, "data": {"jobs": [
 {"jobId": "R0119116", "reqId": "R0119116", "title": "2027 Wealth Summer Intern", "multi_location": ["Charlotte, North Carolina, USA"], "postedDate": "2026-11-02T00:00:00.000+0000"},
 {"jobId": "R0120001", "title": "Universal Banker", "location": "Wyomissing, Pennsylvania"}]}}}; phApp.sessionParams = {};</script>'''
PHENOM_JOB = '''<script>phApp.ddo = {"jobDetail": {"data": {"job": {"description": "<p>Open to the Class of 2029.</p>"}}}}; phApp.x = 1;</script>'''
RADANCY_JSON = {"results": '''<section data-total-pages="1"><ul><li class="sr-job-item"><h3><a class="sr-job-item__link" href="/job/new-york/wealth-summer-analyst-2027/287/102910130192"> Wealth - Summer Analyst, New York - USA, 2027 </a></h3>
<span class="sr-job-item__facet job-location">New York, New York</span></li>
<li><a href="/job/charlotte/x/287/555"><h2>Private Bank Intern</h2><span class="job-location">Charlotte, NC</span></a></li></ul></section>'''}


class _R2:
    def __init__(self, text=None, js=None): self.text, self._js = text or "", js
    def raise_for_status(self): pass
    def json(self): return self._js


class _S2:
    def get(self, url, **k):
        if "search-results" in url: return _R2(PHENOM_PAGE)
        if "/job/" in url and "phenom" in url: return _R2(PHENOM_JOB)
        if "search-jobs/results" in url: return _R2(js=RADANCY_JSON)
        return _R2('<div class="ats-description">Rising juniors.</div>"datePosted":"2026-11-05"')


def test_phenom_and_radancy():
    jobs = sources.phenom(_S2(), {"host": "careers.phenom.test", "locale": "us/en", "key": "t", "terms": ["intern"]}, date.today())
    assert [j.id for j in jobs] == ["ph:t:R0119116", "ph:t:R0120001"]
    assert jobs[0].location == "Charlotte, North Carolina, USA" and jobs[0].posted == date(2026, 11, 2)
    assert "Class of 2029" in jobs[0].detail()
    jobs = sources.radancy(_S2(), {"host": "jobs.citi.com", "key": "citi", "terms": ["intern"]}, date.today())
    assert [(j.id, j.title, j.location) for j in jobs] == [
        ("rd:citi:102910130192", "Wealth - Summer Analyst, New York - USA, 2027", "New York, New York"),
        ("rd:citi:555", "Private Bank Intern", "Charlotte, NC")]
    assert "Rising juniors" in jobs[0].detail() and jobs[0].posted == date(2026, 11, 5)


def test_workday_feed_from_mac(tmp_path, monkeypatch):
    import gzip, json
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat(timespec="minutes")
    feed = {"generated_at": now, "boards": {"baird/careers": {"ok": True, "checked_at": now, "jobs": [
        {"id": "wd:baird:R1", "title": "Internship – Private Wealth Management", "url": "https://u/1", "location": "2 Locations",
         "postedOn": "Posted 3 Days Ago", "detail": {"jobDescription": "<p>Class of 2029</p>", "location": "Milwaukee, WI",
                                                     "additionalLocations": ["Chicago, IL"]}}]},
        "old/x": {"ok": True, "checked_at": "2026-01-01T00:00+00:00", "jobs": []}}}
    p = tmp_path / "f.json.gz"
    p.write_bytes(gzip.compress(json.dumps(feed).encode()))
    monkeypatch.setattr(sources, "FEED_PATH", p)
    monkeypatch.setattr(sources, "_feed_cache", None)
    assert sources.feed_board("old/x") is None                       # too old to trust
    jobs = sources.workday(None, {"host": "baird.wd1.myworkdayjobs.com", "tenant": "baird", "site": "careers"}, date.today())
    assert [j.id for j in jobs] == ["wd:baird:R1"]
    assert "Class of 2029" in jobs[0].detail() and jobs[0].location == "Milwaukee, WI; Chicago, IL"

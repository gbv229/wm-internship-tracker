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

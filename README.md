# WM Internship Tracker

A free, self-updating website that tracks **wealth management internships** at 100+ firms — global banks, private banks and trust companies, brokerages, independent RIAs, insurers and wealthtech — for college students (aimed at sophomores and juniors).

Every 30 minutes GitHub Actions reads each firm's careers system, keeps internships tied to wealth management / private banking / financial advising, pulls out the details, and republishes the site on GitHub Pages.

**What each posting shows:** firm and firm type, role, season (Summer 2027, Fall 2026, Summer 2028…), which class years are eligible, application deadline, posted date, location, and — when the posting says — pay, minimum GPA, program length, work setup and visa sponsorship. Open a row to see the exact sentence the eligibility and deadline were read from.

## How it's built

```
companies.yaml            the firm list + how to read each careers site
scraper/sources.py        readers for Workday, Oracle, iCIMS, Greenhouse, Lever, Ashby, and page watching
scraper/parse.py          pulls season, class year, deadline, pay, GPA, etc. out of posting text
scraper/run.py            runs everything, merges with previous results, marks vanished roles closed
data/*.json               the results (committed only when something actually changes)
site/                     the website (plain HTML/CSS/JS, no build step)
.github/workflows/update.yml   runs every 30 minutes and deploys to GitHub Pages
tests/                    parser and end-to-end tests (run before every update)
```

### Tracking methods

- **Live feed** — the firm's job system (Workday, Oracle, iCIMS, Greenhouse, Lever, Ashby) is read directly and every matching role appears in the table.
- **Page watch** — firms with no readable feed (e.g. Goldman Sachs, UBS, Edward Jones). The careers page is checked for changes and listed on the *Firms* tab with a direct link.

## Common tasks

**Add a firm** — add an entry to `companies.yaml`. To find a firm's Workday details, open one of its job postings: a URL like `https://ms.wd5.myworkdayjobs.com/External/job/...` means `host: ms.wd5.myworkdayjobs.com`, `tenant: ms`, `site: External`. Commit, and the site updates on the next run.

**Run an update now** — Actions tab → *Update internships* → *Run workflow*.

**Something looks wrong for one firm** — the *Firms* tab shows any careers site that couldn't be reached and the error. Locally:

```bash
pip install -r requirements.txt
python -m scraper.run --only "Morgan Stanley"
python -m pytest -q tests
```

**Preview the site locally**

```bash
mkdir -p _site/data && cp site/* _site/ && cp data/*.json _site/data/
python -m http.server -d _site 8000   # then open http://localhost:8000
```

## Notes

- Eligibility and deadlines are only shown when the posting states them; otherwise the site says *Not stated*. Always confirm on the employer's posting.
- A role is marked closed after it disappears from the firm's site on two successful checks in a row. If a firm's site is unreachable, its roles are left as they were.
- GitHub can start scheduled runs a few minutes late, and pauses schedules on repos with no activity for 60 days (the data commits normally keep it active).
- Independent student project, not affiliated with any firm listed.

# Internship Tracker: Wealth Management & Real Estate

A free, self-updating website that tracks internships at 200+ firms for college students (aimed at sophomores and juniors), in two fields:

- **Wealth management** — global banks, private banks and trust companies, brokerages, independent RIAs, insurers and wealthtech.
- **Real estate** — CRE brokerage and services (CBRE, JLL, Cushman & Wakefield…), REITs, real estate investment managers, developers and operators, homebuilders, and real estate lenders. Banks with real estate groups (J.P. Morgan, Wells Fargo, PNC, M&T…) appear in both.

Every 30 minutes GitHub Actions reads each firm's careers system, keeps internships tied to wealth management or real estate, pulls out the details, and republishes the site on GitHub Pages.

**What each posting shows:** firm and firm type, role, season (Summer 2027, Fall 2026, Summer 2028…), which class years are eligible, application deadline, posted date, location, and — when the posting says — pay, minimum GPA, program length, work setup and visa sponsorship. Open a row to see the exact sentence the eligibility and deadline were read from.

## Early programs & Summer 2028

A separate tab lists sophomore programs, insight days, fellowships, campus ambassador programs and Summer 2028 internships, with opening dates and deadlines. It combines:

- `early_programs.yaml`: a hand-researched list (sources linked on each entry). Dates marked `*_est: true` are projected from last year's cycle.
- Live postings: any posting at a tracked firm whose title looks like a sophomore / insight / externship / fellowship program.

Every run also writes `data/early-programs.ics`, a calendar feed with reminders 7, 2 and 1 days before each deadline and the day before each opening date. Subscribe from the tab (Google Calendar, Apple or Outlook) and it stays up to date.

## For visitors

- **My list** — Save roles and programs and track them as Applied / Interviewing / Offer / Rejected / Not for me. Stored in the visitor's browser only (no accounts); CSV backup and restore.
- **New since last visit** — roles that appeared since you last opened the site are marked and can be filtered.
- **Alerts** — Atom feeds per field (`data/feed-wealth.xml`, `data/feed-real-estate.xml`, `data/feed-early.xml`) for feed readers, Slack/Discord or RSS-to-email services; plus the calendar feed on the Early programs tab.
- **Report a problem** — every role links to a prefilled GitHub issue.

## Maintaining it

- **Hand corrections:** add an entry to `overrides.yaml` (deadline, class year, season or a note). The role shows a *Verified* mark.
- **Firm recruiting notes:** `firm_notes.yaml` (timeline, program names, tips, links), shown in role details and on the Firms tab.
- **Health alerts:** the update job keeps one GitHub issue labelled `tracker-health` open while any job feed has failed 3 runs in a row or a careers link has moved, and closes it when things recover. GitHub emails you about new issues.
- **Visitor counts:** sign up free at goatcounter.com and put your code in `window.GOATCOUNTER_CODE` in `site/index.html`.
- **Custom domain:** buy a domain, then Settings → Pages → Custom domain, and add the DNS records GitHub shows. Update the `og:` URLs in `site/index.html` to the new domain.

## How it's built

```
companies.yaml            the firm list, which field(s) each belongs to, and how to read its careers site
early_programs.yaml       researched sophomore / insight / Summer 2028 programs and their dates
scraper/early.py          builds the Early programs data, the calendar feed and firm notes
scraper/browser.py        headless-browser reader for careers pages without a job feed
scraper/feeds.py          Atom feeds of new roles
scraper/health.py         health report used for the tracker-health issue
overrides.yaml            hand corrections to postings
firm_notes.yaml           how each major firm recruits
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
- **Read via browser** — firms with no readable feed (e.g. Goldman Sachs, UBS, Edward Jones) are opened in headless Chromium every 3 hours (`scraper/browser.py`). Internship and program links on the careers page, and one level into "Students / Internships" pages, are read and run through the same filters.
- **Page watch** — sites that block automated visits are still checked for changes and listed on the *Firms* tab with a direct link.

## Common tasks

**Add a firm** — add an entry to `companies.yaml` with `tracks: [wealth]`, `[real_estate]` or both. To find a firm's Workday details, open one of its job postings: a URL like `https://ms.wd5.myworkdayjobs.com/External/job/...` means `host: ms.wd5.myworkdayjobs.com`, `tenant: ms`, `site: External`. Commit, and the site updates on the next run.

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

"""Atom feeds of newly found roles, one per field.

Anyone can follow these in a feed reader, Slack/Discord/GroupMe (most have
an RSS integration), or turn them into email with a free RSS-to-email
service.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

SITE = "https://gbv229.github.io/wm-internship-tracker/"
FEEDS = {
    "wealth": ("feed-wealth.xml", "New wealth management internships"),
    "real_estate": ("feed-real-estate.xml", "New real estate internships"),
    "early": ("feed-early.xml", "New sophomore & early programs"),
}


def _summary(p: dict) -> str:
    bits = [p.get("company_type"), p.get("location"), p.get("season"),
            ("Eligible: Class of " + ", ".join(map(str, p["classes"]))) if p.get("classes") else None,
            ("Deadline: " + p["deadline"]) if p.get("deadline") else "Rolling",
            p.get("pay")]
    return " · ".join(b for b in bits if b)


def write_feeds(postings: list[dict], data: Path, today: date, days: int = 30, limit: int = 100):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for track, (fname, title) in FEEDS.items():
        items = [p for p in postings if p.get("status") == "open" and track in (p.get("tracks") or [])
                 and p.get("level", "Undergraduate") == "Undergraduate" and p.get("first_seen") and not p.get("hide")
                 and (today - date.fromisoformat(p["first_seen"])).days <= days]
        items.sort(key=lambda p: (p["first_seen"], p["company"]), reverse=True)
        entries = []
        for p in items[:limit]:
            ts = f"{p['first_seen']}T12:00:00Z"
            entries.append(f"""  <entry>
    <id>urn:wm-internship-tracker:{escape(p['id'])}</id>
    <title>{escape(p['company'])} – {escape(p['title'])}</title>
    <link rel="alternate" href="{escape(p['url'], {'"': '&quot;'})}"/>
    <updated>{ts}</updated>
    <published>{ts}</published>
    <author><name>{escape(p['company'])}</name></author>
    <summary>{escape(_summary(p))}</summary>
  </entry>""")
        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>{SITE}data/{fname}</id>
  <title>{escape(title)}</title>
  <subtitle>Found on firm careers sites by the Internship Tracker; checked every 30 minutes.</subtitle>
  <link rel="alternate" href="{SITE}"/>
  <link rel="self" href="{SITE}data/{fname}"/>
  <updated>{now}</updated>
{chr(10).join(entries)}
</feed>
"""
        (data / fname).write_text(xml)

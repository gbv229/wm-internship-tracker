"""Probe: capture Goldman's job-search GraphQL request and replay it."""
import asyncio, gzip, json, re
import requests
from playwright.async_api import async_playwright
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(user_agent=UA)
        caps = []
        def on_req(r):
            if "api-higher.gs.com" in r.url:
                buf = r.post_data_buffer or b""
                try: buf = gzip.decompress(buf)
                except Exception: pass
                caps.append((r.url, dict(r.headers), buf.decode("utf-8", "replace")))
        pg.on("request", on_req)
        await pg.goto("https://higher.gs.com/results?EXPERIENCE_LEVEL=Campus&search=summer%20analyst&page=1&sort=RELEVANCE", wait_until="networkidle", timeout=60000)
        await pg.wait_for_timeout(5000)
        body = re.sub(r"\s+", " ", await pg.inner_text("body"))
        print("BODY", body[:2500])
        for u, h, d in caps:
            print("URL", u); print("HDR", {k: v for k, v in h.items() if k.lower() not in ("cookie",)}); print("DATA", d[:6000]); print("-----")
        await b.close()
        return caps

caps = asyncio.run(main())
for u, h, d in caps:
    if "roleSearch" in d or "GetRoles" in d or "search" in d.lower():
        try:
            hh = {k: v for k, v in h.items() if k.lower() in ("content-type", "accept", "origin", "referer", "apollographql-client-name", "apollographql-client-version", "x-higher-request-source")}
            hh["User-Agent"] = UA
            r = requests.post(u, data=d.encode(), headers=hh, timeout=30)
            print("REPLAY", r.status_code, r.text[:3000])
        except Exception as e: print("REPLAY ERR", e)
        break

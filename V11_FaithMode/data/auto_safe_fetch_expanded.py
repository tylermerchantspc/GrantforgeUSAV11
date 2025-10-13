#!/usr/bin/env python3
# GrantforgeUSA — Expanded Auto-Fetch (RSS, shutdown-proof)
# Pulls all core Grants.gov RSS streams, extracts deadlines, keeps only 60+ days, writes safe_cache_v1.csv

import requests, feedparser, pandas as pd, re, os, hashlib
from datetime import datetime, timezone

# ----------------- SETTINGS -----------------
RSS_FEEDS = [
    "https://www.grants.gov/rss/GG_NewOppsByCategory.xml",
    "https://www.grants.gov/rss/GG_OppModByCategory.xml",
    "https://www.grants.gov/rss/GG_NewOppsByAgency.xml",
    "https://www.grants.gov/rss/GG_OppModByAgency.xml",
]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
SAFE_DAYS = 60
OUTPUT_FILE = "safe_cache_v1.csv"
# --------------------------------------------

def fetch_text(url: str) -> str:
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return r.text

# multiple common patterns we see in RSS descriptions
DEADLINE_PATTERNS = [
    r"(?:Closing|Close Date)\s*:\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})",
    r"(?:Closing|Close Date)\s*-\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})",
    r"(?:Deadline)\s*:\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})",
]

MONTHS = {m: i for i, m in enumerate(
    ["January","February","March","April","May","June","July","August","September","October","November","December"], start=1)}

def parse_deadline_from_text(text: str) -> str:
    if not text:
        return ""
    for pat in DEADLINE_PATTERNS:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            mon = m.group(1).capitalize()
            day = int(m.group(2))
            year = int(m.group(3))
            if mon in MONTHS:
                try:
                    dt = datetime(year, MONTHS[mon], day, tzinfo=timezone.utc)
                    return dt.date().isoformat()
                except Exception:
                    continue
    return ""

def sha_id(title: str, url: str) -> str:
    raw = f"{title or ''}|{url or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

def main():
    records = []
    errors = []
    for url in RSS_FEEDS:
        try:
            xml = fetch_text(url)
            feed = feedparser.parse(xml)
            for e in feed.entries:
                title = (e.get("title") or "").strip()
                link = (e.get("link") or "").strip()
                desc = (e.get("summary") or e.get("description") or "").strip()
                agency = (e.get("publisher") or "").strip()

                # try to find a deadline in the text
                deadline_iso = parse_deadline_from_text(desc)
                if not deadline_iso:
                    # skip items that don't state a close date in the feed text
                    continue

                # compute days left
                try:
                    dl = datetime.fromisoformat(deadline_iso)
                except Exception:
                    continue
                days_left = (dl - datetime.now(timezone.utc)).days
                if days_left < SAFE_DAYS:
                    continue

                rec = {
                    "Grant Title": title,
                    "Agency": agency,
                    "Category": "",  # not reliable in RSS; can enrich later
                    "Short Summary": desc[:280],
                    "URL": link,
                    "Posted Date": "",  # not reliable in RSS; leave blank for now
                    "Deadline": deadline_iso,
                    "Days Left": days_left,
                    "Last Seen": datetime.utcnow().date().isoformat(),
                    "Source": url.rsplit("/", 1)[-1],
                    "_id": sha_id(title, link)
                }
                records.append(rec)
        except Exception as ex:
            errors.append(f"{url}: {ex}")

    if not records:
        # If nothing new matched, keep the previous safe cache file untouched.
        print("⚠️  No 60+ day grants found in RSS today; keeping previous safe_cache_v1.csv if present.")
        if errors:
            print("Notes:", *errors, sep="\n  - ")
        return

    # Deduplicate by _id, prefer latest Last Seen
    df = pd.DataFrame(records)
    df.sort_values(["_id","Last Seen"], inplace=True)
    df = df.drop_duplicates(subset=["_id"], keep="last")

    df.to_csv(OUTPUT_FILE, index=False)
    print(f"✅  Safe cache rebuilt → {OUTPUT_FILE}  ({len(df)} records with ≥{SAFE_DAYS} days left).")
    if errors:
        print("Notes:", *errors, sep="\n  - ")

if __name__ == "__main__":
    main()